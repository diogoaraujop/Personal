from requests import Session as new_http_session
from requests_kerberos import HTTPKerberosAuth, DISABLED
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning
import re, os, requests, sys, html
from datetime import datetime, timedelta, date, timezone
import time
from getpass import getuser
import pandas as pd
from playwright.sync_api import sync_playwright
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

disable_warnings(category=InsecureRequestWarning)
session = new_http_session()
session.verify = False
session.auth = HTTPKerberosAuth(mutual_authentication=DISABLED)


project_name = ""
version = "v2.0.0"
header_script = f"""
    Project     : {project_name}
    Author      : Diogo Pereira - @diogpere
    Version     : {version}
    Last Update : 21-04-2026
    """

print()
print(header_script)
print()

def get_latest_version():
    print("Checking for updates...")
    repo_name = "PM_FCLM"
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
    

get_latest_version()

# Add Midway cookie handling
COOKIE_FILE = os.path.expanduser("~/.midway/cookie")
try:
    with open(COOKIE_FILE) as cf:
        for line in cf:
            elem = re.sub(r"^#HttpOnly_", "", line.rstrip()).split()
            if len(elem) == 7:
                session.cookies.set_cookie(
                    requests.cookies.create_cookie(
                        domain=elem[0], name=elem[5], value=elem[6]
                    )
                )
except:
    os.system("mwinit")

# Verify authentication
if (
    session.post(
        "https://isengard-service.amazon.com",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=UTF-8",
            "Content-Encoding": "amz-1.0",
            "X-Amz-Target": "IsengardService.Hello",
        },
    ).status_code
    != 200
):
    os.system("mwinit")
    
# Initialize logistics session
session.get("https://logistics.amazon.co.uk/station/dashboard/problemsolve")