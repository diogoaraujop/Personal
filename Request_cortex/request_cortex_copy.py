import csv
import os
from datetime import date, timedelta, datetime
from playwright.sync_api import sync_playwright
import time
import schedule


def my_task():
    SERVICE_AREA_ID = {"DIG1": "a8e09b16-a31b-45b9-91ff-01a5e8607a1f", "DXE1": "a49a9699-9f38-4259-b486-5fc6bb58edf4"}
    COMPANY_ID = "3e4737fa-fa94-476f-8087-405378a8b2ee"
    BASE_URL = "https://logistics.amazon.co.uk"

    file_dig1_path = r"G:\.shortcut-targets-by-id\1l_jtO0h5BOheQ7m_0l7HlhgppB1yZyPk\Data_Diogo\DIG1"
    file_dxe1_path = r"G:\.shortcut-targets-by-id\1l_jtO0h5BOheQ7m_0l7HlhgppB1yZyPk\Data_Diogo\DXE1"
    days_to_process = 90

    def get_nested_value(container, key):
        if isinstance(container, dict):
            if key in container and container[key] is not None:
                return container[key]
            for value in container.values():
                if isinstance(value, dict):
                    found = get_nested_value(value, key)
                    if found is not None:
                        return found
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            found = get_nested_value(item, key)
                            if found is not None:
                                return found
        return None

    def format_timestamp(raw_value):
        if raw_value in (None, ""):
            return ""
        try:
            timestamp = float(raw_value)
            if timestamp > 100000000000:
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        except (TypeError, ValueError, OverflowError, OSError):
            return ""

    for i_day in range(days_to_process, 0, -1):
        print(f"Processing day {days_to_process - i_day + 1} of {days_to_process}")
        for station, service_area in SERVICE_AREA_ID.items():
            csv_file_name = f"data_{station}_{(date.today() - timedelta(days=i_day)).strftime('%d.%m.%Y')}.csv"
            print(f"Processing station: {station}, service area: {service_area}")
            yesterday = (date.today() - timedelta(days=i_day)).isoformat()
            collection_date_from = (date.today() - timedelta(days=i_day)).strftime('%d/%m/%Y')
            start_time = datetime.now()
            start_time_str = start_time.strftime("%H:%M:%S")
            
            if station == "DIG1":
                csv_file_path = os.path.join(file_dig1_path, csv_file_name)
            else:
                csv_file_path = os.path.join(file_dxe1_path, csv_file_name)
                
            if os.path.exists(csv_file_path):
                print(f"Data for {yesterday} already exists. Skipping...")
                continue

            ITINERARIES_PAGE = (
                f"{BASE_URL}/internal/operations/execution/itineraries"
                f"?provider={COMPANY_ID}&selectedDay={yesterday}&serviceAreaId={SERVICE_AREA_ID[station]}"
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
                    no_viewport=True,
                    args=["--start-maximized"]
                    )
                page = browser.pages[0]

                page.goto(ITINERARIES_PAGE)
                
                if "/internal/operations/execution" not in page.url:
                    print("Not logged in, please log in and press Enter...")
                    input()

                print(f"Fetching summaries for {yesterday}...")
                summaries_data = capture_response(page, "/api/summaries", page.reload)
                all_summaries = summaries_data.get("itinerarySummaries", []) if summaries_data else []

                summaries = [s for s in all_summaries if s.get("companyId") == COMPANY_ID]
                print(f"Found {len(all_summaries)} total, {len(summaries)} for company {COMPANY_ID}")

                all_data = []
                data_file = []
                headers = [
                    "transport_id",
                    "route_number",
                    "stop_number",
                    "tracking_id",
                    "timestamp",
                    "event_type",
                    "message",
                    "itinerary_start_time",
                    "session_end_time",
                    "collection_date_from"
                ]
                data_file.append(headers)
                for i, s in enumerate(summaries):
                    itinerary_id = s.get("itineraryId")
                    service_area_id = s.get("serviceAreaId", SERVICE_AREA_ID[station])
                    print(f"[{i+1}/{len(summaries)}] Fetching itinerary: {itinerary_id}")

                    itinerary_url = (
                        f"{BASE_URL}/internal/operations/execution/itineraries/{itinerary_id}"
                        f"/documentType/Itinerary?provider={COMPANY_ID}"
                        f"&selectedDay={yesterday}&serviceAreaId={service_area_id}"
                    )

                    data = capture_response(page, f"/api/itineraries/{itinerary_id}", lambda: page.goto(itinerary_url))
                    if data:
                        all_data.append(data)
                        itinerary_details = data.get("itineraryDetails") or {}
                        if not isinstance(itinerary_details, dict):
                            itinerary_details = {}

                        itinerary_start_raw = get_nested_value(itinerary_details, "itineraryStartTime")
                        session_end_raw = get_nested_value(itinerary_details, "sessionEndTime")

                        itinerary_start_time = format_timestamp(itinerary_start_raw)
                        session_end_time = format_timestamp(session_end_raw)

                        stops = itinerary_details.get("stops", [])
                        stops_count = len(stops)
                        for i in range(stops_count):
                            stop = stops[i]
                            itinerary_stop_type = stop.get("itineraryStopType")
                            transport_id = itinerary_details.get("transporterId", "")
                            route_number = stop.get("routeCode") if stop.get("routeCode") is not None else "None"
                            stop_number = stop.get("sequenceNumber", "")
                            tasks = stop.get("tasks", [])
                            if itinerary_stop_type == "PICK_UP":
                                if stop_number == 1:
                                    message = "Pickup at Amazon (start of route)"
                                else:
                                    message = "Pickup"
                                event_type = ""
                                for task in tasks:
                                    event_type = task.get("taskType", "") or ""
                                    actual_time = task.get("actualExecutionTime")
                                    if actual_time is not None:
                                        dt = datetime.fromtimestamp(actual_time)
                                        timestamp = dt.strftime("%H:%M:%S")
                                    else:
                                        timestamp = ""
                                    if timestamp:
                                        break
                                data_file.append([
                                    transport_id,
                                    route_number,
                                    stop_number,
                                    "",
                                    timestamp,
                                    event_type,
                                    message,
                                    itinerary_start_time,
                                    session_end_time,
                                    collection_date_from
                                ])
                            elif itinerary_stop_type == "DROP_OFF":
                                event_type = ""
                                for task in tasks:
                                    event_type = task.get("taskType", "") or ""
                                    actual_time = task.get("actualExecutionTime")
                                    if actual_time is not None:
                                        dt = datetime.fromtimestamp(actual_time)
                                        timestamp = dt.strftime("%H:%M:%S")
                                    else:
                                        timestamp = ""
                                    if event_type == "RETURN":
                                        message = "Returned to Station"
                                        tracking_id = ""
                                    else:
                                        message = task.get("taskStateContext")
                                        if message is None or message.lower() == "none":
                                            message = "Returned to Station"
                                        tracking_id = task.get("domainMap", {}).get("scannableId", "") or ""
                                    data_file.append([
                                        transport_id,
                                        route_number,
                                        stop_number,
                                        tracking_id,
                                        timestamp,
                                        event_type,
                                        message,
                                        itinerary_start_time,
                                        session_end_time,
                                        collection_date_from
                                    ])
                            
                with open(csv_file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerows(data_file)
                end_time = datetime.now()
                end_time_str = end_time.strftime("%H:%M:%S")
                print(f"Start time: {start_time}")
                print(f"End time: {end_time}")
                print(f"Duration: {end_time - start_time}")
                browser.close()
        print(f"Completed processing for day {days_to_process - i_day + 1} of {days_to_process} \n\n")        

my_task()
# schedule.every().day.at("11:00").do(my_task)

# while True:
#     schedule.run_pending()
#     time.sleep(1)
