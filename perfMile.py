from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import unquote, parse_qs, urlparse
from datetime import datetime, timedelta
from collections import defaultdict
import json
import csv
import os


PERFECTMILE_URL = "https://perfectmile.a2z.com/?visualization=table&breakdown=default&layout=sddonat&periodicity=WEEKLY&startDate=2026-03-15&endDate=2026-04-25&timeAggregationConfig=%7B%22value%22%3A%22SIX_WEEKS%22%2C%22type%22%3A%22TimePeriod%22%7D&drilldowns=%5B%7B%22technicalName%22%3A%22parent_country%22%2C%22limit%22%3A0%2C%22performanceRating%22%3Anull%7D%2C%7B%22technicalName%22%3A%22location%22%2C%22limit%22%3A0%2C%22performanceRating%22%3Anull%7D%5D&scopeType=subRegion&scopeValue=UK+%2B+IE&pageFilters=%7B%22filters%22%3A%7B%22dashboard%22%3A%7B%22location_type%22%3A%5B%223P%22%2C%22DS%22%2C%22SC%22%2C%22XP%22%2C%22HQ%22%2C%22WW%22%5D%7D%7D%7D&business=AMZL&profileRegion=EU&profileCountry=UK&analyzeDrilldowns=%5B%5D&metrics=%5B%5D&metricList=%5B%5D"

GRAPHQL_URL = "https://prod.caravan.perfectmile.a2z.com/graphql"
OUTPUT_FILE = "perfectmile_output.csv"


def date_to_week(date_str):
    """
    Convert '2026-03-15' into 'W12'.
    """
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return f"W{date_obj.isocalendar().week}"


def build_weeks_from_dates(start_date, end_date):
    """
    Build the week headers based on the selected date range.
    Example:
        start_date = 2026-03-15
        end_date   = 2026-04-25

    Output:
        ['W11', 'W12', 'W13', ...]
    """
    weeks = []

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    current = start

    while current <= end:
        weeks.append(f"W{current.isocalendar().week}")
        current += timedelta(days=7)

    return weeks


def calculate_wow(previous_value, current_value):
    """
    Calculate WoW percentage.

    PerfectMile displays this as positive percentage in your screenshot,
    so we use abs().
    """
    if previous_value in [None, 0, "-"] or current_value in [None, "-"]:
        return "-"

    wow = abs((current_value - previous_value) / previous_value) * 100
    return f"{wow:.2f}%"


def extract_url_config(url_web):
    """
    Extract the selected filters from the current PerfectMile URL.

    This is important because after you manually select metrics/date range,
    page.url contains the real selected config.
    """
    decoded_url = unquote(url_web)
    parsed_url = urlparse(decoded_url)
    params = parse_qs(parsed_url.query)

    country = params.get("profileCountry", [""])[0]
    start_date = params.get("startDate", [""])[0]
    end_date = params.get("endDate", [""])[0]
    periodicity = params.get("periodicity", [""])[0]
    primary_region = params.get("profileRegion", [""])[0]
    scope = params.get("scopeValue", [""])[0]

    page_filters_raw = params.get("pageFilters", ["{}"])[0]
    page_filters = json.loads(page_filters_raw)

    location_types = page_filters["filters"]["dashboard"]["location_type"]

    dimensionality = {
        "location_sub_region": [scope],
        "location_type": location_types
    }

    return {
        "country": country,
        "start_date": start_date,
        "end_date": end_date,
        "periodicity": periodicity,
        "primary_region": primary_region,
        "scope": scope,
        "dimensionality": dimensionality
    }


def capture_json_response(page, partial_url, data_name, action, timeout_ms=60000):
    """
    Capture one JSON response from the page.

    Used here to capture:
        data["data"]["getDetailedLayout"]

    Why:
        getDetailedLayout tells us which metrics are selected/available.
    """
    captured_data = None

    def handle_response(response):
        nonlocal captured_data

        if partial_url in response.url and response.status == 200 and captured_data is None:
            try:
                data = response.json()
                result = data.get("data", {}).get(data_name)

                if result:
                    captured_data = result
                    print(f"✅ {data_name} captured")

            except Exception:
                pass

    page.on("response", handle_response)

    action()

    waited = 0
    step = 500

    while captured_data is None and waited < timeout_ms:
        page.wait_for_timeout(step)
        waited += step

    try:
        page.remove_listener("response", handle_response)
    except Exception:
        pass

    return captured_data


def capture_graphql_headers(page):
    """
    Capture headers from a real browser GraphQL request.

    We need this because page.request.post() must use similar auth/session headers
    as the real browser.
    """
    captured_headers = None

    def handle_request(request):
        nonlocal captured_headers

        if "/graphql" in request.url and captured_headers is None:
            captured_headers = request.headers
            print("✅ GraphQL headers captured")

    page.on("request", handle_request)

    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(7000)

    try:
        page.remove_listener("request", handle_request)
    except Exception:
        pass

    return captured_headers


def fetch_expanded_table_data(page, headers, metric_name, config):
    """
    Fetch PerfectMile data using TWO requests inside the same GraphQL payload.

    Request 1:
        parent_country
        This gives the top row, like UK + IE.

    Request 2:
        location
        This gives the expanded station rows, like BHX8, DAB1, DIG1, etc.

    This is the important part that was missing before.
    """

    scope = config["scope"]

    payload = {
        "operationName": "getBatchExpandedTableViewData",
        "variables": {
            "requests": [
                {
                    "country": config["country"],
                    "metricName": metric_name,
                    "detailDimensions": ["parent_country"],
                    "startDate": config["start_date"],
                    "endDate": config["end_date"],
                    "periodicity": config["periodicity"],
                    "dimensionality": json.dumps(config["dimensionality"]),
                    "primaryRegion": config["primary_region"]
                },
                {
                    "country": config["country"],
                    "metricName": metric_name,
                    "detailDimensions": ["location"],
                    "startDate": config["start_date"],
                    "endDate": config["end_date"],
                    "periodicity": config["periodicity"],
                    "dimensionality": json.dumps(config["dimensionality"]),
                    "secondaryFilterIn": json.dumps({
                        "parent_country": [scope]
                    }),
                    "primaryRegion": config["primary_region"],
                    "fallbackDimensions": json.dumps([
                        {
                            "type": "parent_country",
                            "values": [scope]
                        },
                        {
                            "type": "location_sub_region",
                            "values": [scope]
                        }
                    ]),
                    "metricTargetsV2Flag": True
                }
            ]
        },
        "query": """
        query getBatchExpandedTableViewData($requests: [ExpandedTableViewRequest]!) {
            getBatchExpandedTableViewData(requests: $requests) {
                responses {
                    dimensionValue
                    date
                    dimensionType
                    hour
                    dimensionality
                    periodicity
                    metricData {
                        metricValue {
                            ponderation
                            quantity
                            value
                            updatedAt
                        }
                        metricTarget {
                            type
                            value
                            secondTargetValue
                            padding
                        }
                    }
                }
            }
        }
        """
    }

    response = page.request.post(
        GRAPHQL_URL,
        headers=headers,
        data=payload
    )

    if response.status != 200:
        print(f"❌ Request failed for {metric_name}: {response.status}")
        try:
            print(response.text())
        except Exception:
            pass
        return [], []

    data = response.json()

    responses = (
        data
        .get("data", {})
        .get("getBatchExpandedTableViewData", {})
        .get("responses", [])
    )

    if not responses:
        return [], []

    parent_records = responses[0] if len(responses) > 0 else []
    location_records = responses[1] if len(responses) > 1 else []

    return parent_records, location_records


def convert_metric_value(metric_value):
    """
    Convert PerfectMile metric value into the number shown in the table.

    For DPMO metrics:
        PerfectMile stores 0.0003395
        Table shows 340

    So:
        0.0003395 * 1_000_000 = 339.5
    """
    value = metric_value.get("value")

    if value is None:
        return "-"

    return value * 1_000_000


def build_row_from_records(row_name, records, weeks):
    """
    Create one CSV row.

    Example:
        ['DIG1', 436, 336, 346, 402, 375, 340, '9.37%']
    """
    values_by_week = {}

    for item in records:
        week = date_to_week(item["date"])
        metric_value = item["metricData"]["metricValue"]

        values_by_week[week] = convert_metric_value(metric_value)

    row = [row_name]

    for week in weeks:
        value = values_by_week.get(week, "-")

        if value == "-":
            row.append("-")
        else:
            row.append(round(value))

    if len(weeks) >= 2:
        previous_value = values_by_week.get(weeks[-2], "-")
        current_value = values_by_week.get(weeks[-1], "-")
        row.append(calculate_wow(previous_value, current_value))
    else:
        row.append("-")

    return row


def build_location_rows(location_records, weeks):
    """
    Group the location response by station.

    Input records are mixed:
        DIG1 W12
        DAB1 W12
        DIG1 W13
        DAB1 W13

    We transform this into:
        DIG1 | W12 | W13 | ...
        DAB1 | W12 | W13 | ...
    """
    location_data = defaultdict(list)

    for item in location_records:
        location = item["dimensionValue"]
        location_data[location].append(item)

    rows = []

    for location in sorted(location_data.keys()):
        row = build_row_from_records(location, location_data[location], weeks)
        rows.append(row)

    return rows


def save_rows_to_csv(rows, output_file):
    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print(f"\n✅ CSV saved: {os.path.abspath(output_file)}")


def get_metric_display_name(metric):
    """
    Try to get a clean metric display name from layout.

    Different PerfectMile layouts may use slightly different keys.
    """
    return (
        metric.get("name")
        or metric.get("displayName")
        or metric.get("label")
        or metric.get("title")
        or metric.get("technicalName")
    )


def main():
    all_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=r"C:\Users\diogpere\OneDrive - amazon.com\Documents\playwright_profiles\test",
            headless=False,
            no_viewport=True,
            args=["--start-maximized"]
        )

        page = browser.pages[0] if browser.pages else browser.new_page()

        page.goto(PERFECTMILE_URL, wait_until="domcontentloaded", timeout=60000)

        if "midway-auth.amazon.com" in page.url:
            print("Redirected to Midway login. Please complete login manually...")

            try:
                page.wait_for_function(
                    """() => !window.location.href.includes('midway-auth.amazon.com')""",
                    timeout=600000
                )
                print("Midway login finished.")

            except PlaywrightTimeoutError:
                print("Login timeout.")
                print("Current URL:", page.url)
                return

            page.goto(PERFECTMILE_URL, wait_until="domcontentloaded", timeout=60000)

        page.bring_to_front()

        input(
            "\nSelect the metrics, change the date range, "
            "confirm the table has values, then press Enter here..."
        )

        config = extract_url_config(page.url)
        weeks = build_weeks_from_dates(config["start_date"], config["end_date"])

        print("\nCurrent config:")
        print(json.dumps(config, indent=4))
        print("Weeks:", weeks)

        header = [""] + weeks + ["WoW%"]
        all_rows.append(header)

        layout = capture_json_response(
            page=page,
            partial_url="/graphql",
            data_name="getDetailedLayout",
            action=lambda: page.reload(wait_until="domcontentloaded"),
            timeout_ms=60000
        )

        if not layout:
            print("❌ Could not capture getDetailedLayout.")
            input("\nPress Enter to close browser...")
            browser.close()
            return

        graphql_headers = capture_graphql_headers(page)

        if not graphql_headers:
            print("❌ Could not capture GraphQL headers.")
            input("\nPress Enter to close browser...")
            browser.close()
            return

        buckets = layout.get("buckets", [])

        print(f"\nBuckets found: {len(buckets)}")

        for bucket in buckets:
            bucket_name = bucket.get("name", "unknown_bucket")
            metrics = bucket.get("metrics", [])

            print(f"\n📦 Bucket: {bucket_name}")
            print(f"Metrics found: {len(metrics)}")

            for metric in metrics:
                metric_name = metric.get("technicalName")
                metric_display_name = get_metric_display_name(metric)

                if not metric_name:
                    continue

                print(f"\nProcessing metric: {metric_display_name} / {metric_name}")

                parent_records, location_records = fetch_expanded_table_data(
                    page=page,
                    headers=graphql_headers,
                    metric_name=metric_name,
                    config=config
                )

                print(f"Parent records: {len(parent_records)}")
                print(f"Location records: {len(location_records)}")

                if not parent_records and not location_records:
                    print(f"⚠️ No data for metric: {metric_name}")
                    continue

                metric_title = metric_display_name

                if parent_records:
                    metric_row = build_row_from_records(metric_title, parent_records, weeks)
                    uk_row = build_row_from_records(config["scope"], parent_records, weeks)
                else:
                    metric_row = [metric_title] + ["-"] * len(weeks) + ["-"]
                    uk_row = [config["scope"]] + ["-"] * len(weeks) + ["-"]

                all_rows.append(metric_row)
                all_rows.append(uk_row)

                location_rows = build_location_rows(location_records, weeks)
                all_rows.extend(location_rows)

                all_rows.append([])

        save_rows_to_csv(all_rows, OUTPUT_FILE)

        input("\nPress Enter to close browser...")
        browser.close()


if __name__ == "__main__":
    main()