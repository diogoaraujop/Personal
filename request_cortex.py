import json
from datetime import date, timedelta, datetime
from playwright.sync_api import sync_playwright

SERVICE_AREA_ID = "a8e09b16-a31b-45b9-91ff-01a5e8607a1f"
COMPANY_ID = "3e4737fa-fa94-476f-8087-405378a8b2ee"
BASE_URL = "https://logistics.amazon.co.uk"
yesterday = (date.today() - timedelta(days=1)).isoformat()
start_time = datetime.now()
start_time_str = start_time.strftime("%H:%M:%S")

ITINERARIES_PAGE = (
    f"{BASE_URL}/internal/operations/execution/itineraries"
    f"?provider={COMPANY_ID}&selectedDay={yesterday}&serviceAreaId={SERVICE_AREA_ID}"
)

def capture_response(page, url_fragment, action):
    captured = {}

    def on_response(response):
        if url_fragment in response.url and response.status == 200:
            try:
                captured["data"] = response.json()
            except Exception:
                pass

    page.on("response", on_response)
    action()
    page.wait_for_load_state("networkidle")
    page.remove_listener("response", on_response)
    return captured.get("data")

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=r"C:\Users\diogpere\OneDrive - amazon.com\Documents\playwright_profiles\request_cortex",
        headless=False,
        )
    page = browser.pages[0]

    page.goto(ITINERARIES_PAGE)
    input("Log in if needed, wait for page to fully load, then press Enter...")

    print(f"Fetching summaries for {yesterday}...")
    summaries_data = capture_response(page, "/api/summaries", page.reload)
    all_summaries = summaries_data.get("itinerarySummaries", []) if summaries_data else []

    summaries = [s for s in all_summaries if s.get("companyId") == COMPANY_ID]
    print(f"Found {len(all_summaries)} total, {len(summaries)} for company {COMPANY_ID}")

    all_data = []
    data_file = []
    headers = ["transport_id", "route_number", "stop_number", "tracking_id", "timestamp", "message"]
    data_file.append(headers)
    for i, s in enumerate(summaries):
        itinerary_id = s.get("itineraryId")
        service_area_id = s.get("serviceAreaId", SERVICE_AREA_ID)
        print(f"[{i+1}/{len(summaries)}] Fetching itinerary: {itinerary_id}")

        itinerary_url = (
            f"{BASE_URL}/internal/operations/execution/itineraries/{itinerary_id}"
            f"/documentType/Itinerary?provider={COMPANY_ID}"
            f"&selectedDay={yesterday}&serviceAreaId={service_area_id}"
        )

        data = capture_response(page, f"/api/itineraries/{itinerary_id}", lambda: page.goto(itinerary_url))
        if data:
            all_data.append(data)
            transporters = data.get("transporters", [])
            itinenary_details = data.get("itineraryDetails", [])
            stops = itinenary_details["stops"]
            stops_count = len(stops)
            for i in range(stops_count):
                stop = stops[i]
                itinerary_stop_type = stop["itineraryStopType"]
                transport_id = itinenary_details["transporterId"]
                route_number = stop["routeCode"] if stop["routeCode"] != None else "None"
                stop_number = stop["sequenceNumber"]
                if "_" in route_number:
                    tasks = stop["tasks"]
                    if itinerary_stop_type == "PICK_UP":
                        if stop_number == 1:
                            message = "Pickup at Amazon (start of route)"
                        else:
                            message = "Pickup"
                        for task in tasks:
                            actual_time = task["actualExecutionTime"]
                            if actual_time != None:
                                dt = datetime.fromtimestamp(actual_time)
                                timestamp = dt.strftime("%H:%M:%S")
                            else:
                                timestamp = "None"
                            if timestamp:
                                break
                        print(f"{transport_id}, {route_number}, {stop_number}, {timestamp}, {message}")
                        data_file.append([f"{transport_id}, {route_number}, {stop_number}, {timestamp}, {message}"])
                    elif itinerary_stop_type == "DROP_OFF":
                        for task in tasks:     
                            actual_time = task["actualExecutionTime"]
                            if actual_time != None:
                                dt = datetime.fromtimestamp(actual_time)
                                timestamp = dt.strftime("%H:%M:%S")
                            else:
                                timestamp = "None"
                            message = task["taskStateContext"]
                            if message == None or message.lower() == "none":
                                message = "Returned to Station"
                            tracking_id = task["domainMap"]["scannableId"]
                            print(f"{transport_id}, {route_number}, {stop_number}, {tracking_id}, {timestamp}, {message}")
                            data_file.append([f"{transport_id}, {route_number}, {stop_number}, {tracking_id}, {timestamp}, {message}"])
                
    # print(json.dumps(all_data, indent=2))
    with open("output.csv", "w") as f:
        for row in data_file:
            f.write(",".join(row) + "\n")
    end_time = datetime.now()
    end_time_str = end_time.strftime("%H:%M:%S")
    print(f"Start time: {start_time}")
    print(f"End time: {end_time}")
    print(f"Duration: {end_time - start_time}")
    browser.close()
