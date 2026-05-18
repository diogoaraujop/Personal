from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, date
import csv, json, os
from getpass import getuser

username = getuser()

today = datetime.today()
today_str = today.strftime("%Y-%m-%d")
start_time_overall = datetime.now()

stationArea = {
    "DHW1": "9174d6fd-c2c8-4c79-885f-153fbb70195a",
    # "DIG1": "a8e09b16-a31b-45b9-91ff-01a5e8607a1f",
}

data_to_file = []
data_to_file.append(["Date", "Route", "Stop", "Tracking ID", "Full Address"])

firstDayOfTheMonth = today.replace(day=1)
dayDiff = (today - firstDayOfTheMonth).days + 1

with sync_playwright() as p:
    broswer = p.chromium.launch_persistent_context(
        user_data_dir=rf"C:\Users\{username}\Documents\playwright_profile\imprecise",
        headless=False,
        no_viewport=True,
        args=["--start-maximized"]
    )
    
    cortex_page = broswer.pages[0]
    
    
    for d in range(1):
        try:
            for area in stationArea:
                areaId = stationArea[area]
                
                today = datetime.today() - timedelta(days=d)
                today_str = today.strftime("%Y-%m-%d")
                
                csv_file = f"imprecise_map_{today_str}_{area}.csv"
                json_file = f"routesChecked_{today_str}_{area}.json"
                
                routesChecked_dict = set()
                
                if os.path.exists(json_file):
                    with open(json_file, mode="r") as file:
                        routesChecked_dict = set(json.load(file))
            
                url = f"https://logistics.amazon.co.uk/internal/operations/execution/itineraries?provider=ALL_DRIVERS&selectedDay={today_str}&serviceAreaId={areaId}"
                def capture_data(page, partial_url, url):
                    data = None
                    headers = None
                        
                    def handle_response(response):
                        nonlocal data
                        if partial_url in response.url and response.status == 200 and data is None:
                            try:
                                data = response.json()
                                # print(f"Captured data from {response.url}")
                                page.remove_listener("response", handle_response)
                                return
                            except Exception as e:
                                print(f"Error parsing JSON from {response.url}: {e}")
                                return

                    # page.on("request", handle_request)
                    page.on("response", handle_response)
                    cortex_page.goto(url, wait_until="domcontentloaded")
                    cortex_page.wait_for_load_state("networkidle")
                    
                    if "midway-auth" in page.url:
                        input("Please complete the authentication process and press Enter to continue...")
                    
                    while data is None:
                        cortex_page.goto(url, wait_until="domcontentloaded")
                        cortex_page.wait_for_load_state("networkidle")
                    
                    return data
                
                data = capture_data(cortex_page, "/api/summaries", url)
                itinerarySummaries = data.get("itinerarySummaries", [])
                routeSummaries = data.get("routeSummaries", [])
                if len(routeSummaries) < len(itinerarySummaries):
                    totalRoutes = itinerarySummaries
                
                else:
                    totalRoutes = routeSummaries
                   
                    
                for i, route in enumerate(totalRoutes):
                    start_time = datetime.now()
                    if len(routeSummaries) < len(itinerarySummaries):
                        routes = route.get("routes", [])
                        if not routes:
                            print(f"Execution time for route - [{i + 1}/{len(totalRoutes)}]: {datetime.now() - start_time} in seconds")
                            print(f"No routes found for itinerary {i + 1}")
                            continue
                        routeId = routes[0].get("routeId")
                    else:
                        routeId = route.get("routeId")
                    if routeId in routesChecked_dict:
                        print(f"Route {routeId} already checked, skipping...")
                        print(f"Execution time for route - [{i + 1}/{len(totalRoutes)}]: {datetime.now() - start_time} in seconds")
                        continue
                    url = f"https://logistics.amazon.co.uk/internal/operations/execution/dv/routes/{routeId}?provider=ALL_DRIVERS&selectedDay={today_str}&serviceAreaId={areaId}"
                    data = capture_data(cortex_page, "/api/route-details", url)
                    addresses = data.get("addresses", [])
                    for address in addresses:
                        addressId = address.get("addressId")
                        fullAddress = str(address["address1"]) + " " + str(address["address2"]) + ", " + str(address["city"]) + ", " + str(address["postalCode"])
                        geocode = address.get("geocode", {})
                        scope = geocode.get("scope")
                        if scope == 15:
                            print(f"Address ID: {addressId} has imprecise geocode with scope 15")
                            rmsRouteDetails = data["rmsRouteDetails"]
                            routeCode = rmsRouteDetails["routeCode"]
                            stops = rmsRouteDetails["stops"]
                            for stop in stops:
                                if stop["addressId"] == addressId:
                                    sequenceNumber = stop["sequenceNumber"]
                                    tasks = stop["tasks"]
                                    if tasks:
                                        trackingId = stop['tasks'][0]['domainMap']['scannableId']
                                        data_to_file.append([today_str, routeCode, sequenceNumber, trackingId, fullAddress])
                                        print(today_str, routeCode, sequenceNumber, trackingId, fullAddress)
                                    else:
                                        print(f"No tasks found for address ID: {addressId}")
                                        
                    routesChecked_dict.add(routeId) 
                              
                    print(f"Execution time for route {routeId} - [{i + 1}/{len(totalRoutes)}]: {datetime.now() - start_time} in seconds")
                    print(f"Overall execution time: {datetime.now() - start_time_overall} in seconds")
                
                with open(csv_file, "w", newline="", encoding="utf-8") as file:
                    writer = csv.writer(file)
                    writer.writerows(data_to_file)     
                print(f"Overall execution time: {datetime.now() - start_time_overall} in seconds and file: {csv_file} saved.")

        except Exception as e:
            print(f"Error processing day {d}: {str(e)}")
            continue      
        finally:
                          
            with open(json_file, "w") as file:
                json.dump(list(routesChecked_dict), file)
