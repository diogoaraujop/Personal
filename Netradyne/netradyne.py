from playwright.sync_api import sync_playwright
from getpass import getuser
import csv
import os
import requests
import sys
import time

username = getuser()

def print_header(project_name: str, version: str):
    header_script = f"""
        Project     : {project_name}
        Author      : Diogo Pereira
        Version     : {version}
        Last Update : 17-05-2026
        """

    print()
    print(header_script)
    print()
    return version

def get_latest_version(version):
    print("Checking for updates...")
    repo_name = "Netradyne"
    url = f"https://api.github.com/repos/diogoaraujop/{repo_name}/releases/latest"

    try:
        response = requests.get(url, timeout=10)

        if response.status_code == 403:
            print("Could not check for updates (GitHub rate limit reached). Continuing with current version.")
            return version

        response.raise_for_status()

        data = response.json()
        latest = data["tag_name"].split("_")[-1]

        if latest != version:
            print(f"Outdated version. Downloading {latest}...")

            for asset in data.get("assets", []):
                if asset["name"].endswith(".exe"):
                    download_file(asset["browser_download_url"], asset["name"])
                    return latest

            print("No .exe file found in the release. Continuing with current version.")
            return version

        else:
            print("You are using the latest version.")
            return version

    except requests.exceptions.RequestException as e:
        print(f"Could not check for updates: {e}")
        print("Continuing with current version.")
        return version

    except Exception as e:
        print(f"Unexpected error while checking updates: {e}")
        print("Continuing with current version.")
        return version


def download_file(url, filename):
    with requests.get(url, stream=True) as response:
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        start_time = time.time()

        with open(filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue

                f.write(chunk)
                downloaded += len(chunk)

                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    elapsed = time.time() - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    remaining = (total_size - downloaded) / speed if speed > 0 else 0

                    print(
                        f"\r{percent:6.2f}% | "
                        f"{downloaded / 1024 / 1024:8.2f} MB / {total_size / 1024 / 1024:8.2f} MB | "
                        f"{speed / 1024 / 1024:6.2f} MB/s | "
                        f"ETA: {remaining:6.1f}s",
                        end=""
                    )

        print("\nDownload complete.")
        sys.exit()
    
version = print_header("Netradyne Automation", "v1.0.0")
get_latest_version(version)

db_Driver_Id_json = "db_Driver_Id.json"
db_Driver_Id_dict = {}

try:
    if os.path.exists(rf"C:\Users\{username}\Documents\netradyne\{db_Driver_Id_json}"):
        with open(rf"C:\Users\{username}\Documents\netradyne\{db_Driver_Id_json}", "r") as f:
            db_Driver_Id_dict = eval(f.read())
    else:
        print("Could not find previous driver id list. Starting fresh.")
except:
    print("Could not load previous driver id list.")

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir = rf"C:\Users\{username}\Documents\netradyne",
        headless=False,
        no_viewport=True,
        args=["--start-maximized"],
        )
    
    page = browser.pages[0]
    page.goto("https://idms.netradyne.com/console/#/greenzone-stats")
    
    if "/login" in page.url:
        
        input("Login and press ENTER to continue.")
    
    def capture_data(partialUrl, action, timeout=30000):
        capture = {}

        def handle_response(response):
            nonlocal capture

            if partialUrl in response.url and response.status == 200 and not capture:
                try:
                    capture = response.json()
                except Exception as e:
                    print(f"There was an error reading this request: {e}")

        page.on("response", handle_response)

        try:
            action()

            waited = 0

            while not capture and waited < timeout:
                print("Waiting for response...")
                page.wait_for_timeout(3000)
                waited += 1000

        finally:
            page.remove_listener("response", handle_response)

        if not capture:
            raise TimeoutError(f"No response captured for: {partialUrl}")

        return capture
    
    def manual_action(message):
        input(message)
        
    data = capture_data("fetchPlaceholderVehicles=true", page.reload)
    dataIn = data.get("data", {})
    vehicles = dataIn.get("vehicles", {})
    
    data_to_file = []
    data_to_file.append(["Date", "Registration Number", "Alert Severity", "Alert Type", "Event Description", "Driver ID", "Driver Name"])
    driver_verification = {}
    
    tab = page.locator('//div[text()="Event Distribution Analysis"]')
    tab.click()
    
    data = capture_data("/alertsStatLiteGreenzoneStatistics", lambda: manual_action("Select 'Duration' in the browser and press ENTER here to continue."))
    duration_text = page.locator('//div[@class="float-left text-left"]').nth(1).text_content()
    dataIn = data.get("data", {})
    alerts = dataIn.get("alerts", {})
    date_of_the_day = "No date"
    for alert in alerts:
        driver_id = alert.get("driver_id", "")
        date_of_the_day = alert.get("date_of_the_day", "")
        if date_of_the_day not in driver_verification:
            driver_verification[date_of_the_day] = {}
        alert_severity = alert.get("alert_severity", "")
        alert_type = alert.get("alert_type", "")
        event_description = alert.get("event_description", "")
        vehicle_id = alert.get("vehicle_id", "")
        if not vehicle_id:
            continue
        for vehicle in vehicles:
            if vehicle_id == vehicle["vehicle_id"]:
                reg = vehicle["nickname"]
                if driver_id != 0 and driver_id not in db_Driver_Id_dict:
                    db_Driver_Id_dict[driver_id] = ""
                data_to_file.append([date_of_the_day, reg, alert_severity, alert_type, event_description, driver_id, ""])
                if driver_id != 0 and reg not in driver_verification[date_of_the_day]:
                    driver_verification[date_of_the_day][reg] = driver_id          
                break
         
    for row in data_to_file:
        if row[5] == 0:
            if row[1] in driver_verification[row[0]]:
                row[5] = driver_verification[row[0]][row[1]]
        
        if row[6] != "":
            continue
        
        if row[5] != "" and row[5] != 0:
            if row[5] in db_Driver_Id_dict and db_Driver_Id_dict[row[5]] != "":
                row[6] = db_Driver_Id_dict[row[5]]      

    if not os.path.exists(rf"C:\Users\{username}\Documents\netradyne\Reports"):
        os.mkdir(rf"C:\Users\{username}\Documents\netradyne\Reports")
        print(rf"Created folder \Documents\netradyne\Reports")
        
    with open(rf"C:\Users\{username}\Documents\netradyne\{db_Driver_Id_json}", "w") as f:
        f.write(str(db_Driver_Id_dict))
        print("Driver ID list updated.")
        
    with open(rf"C:\Users\{username}\Documents\netradyne\Reports\report_{duration_text}.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(data_to_file)
        print(rf"Report saved to report_{duration_text}.csv at \Documents\netradyne\Reports")
    
    print("Done")