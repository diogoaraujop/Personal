from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
import os, requests, sys
import time
from getpass import getuser
from pathlib import Path

CLICK_DELAY = 200
LEVEL_DELAY = 1000
MAX_LEVELS = 6

username = getuser()

def print_header(project_name: str, version: str):
    header_script = f"""
        Project     : {project_name}
        Author      : Diogo Pereira - @diogpere
        Version     : {version}
        Last Update : 15-05-2026
        """

    print()
    print(header_script)
    print()
    return version

def get_latest_version(repo_name: str, version: str):
    print("Checking for updates...")
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

def expand_all_rows(page, table_div, max_levels=6):
    total_clicks = 0

    for level in range(1, max_levels + 1):
        print(f"Starting level {level}...")

        level_clicks = 0

        while True:
            expand_buttons = table_div.locator(
                'td div.css-1tauhsg button:has(span[aria-label="Expand row"])'
            )

            count = expand_buttons.count()

            if count == 0:
                break

            btn = expand_buttons.first

            try:
                btn.scroll_into_view_if_needed()
                btn.click(timeout=5000)
                # print(f"[{total_clicks + 1}]Clicked successfully")
                total_clicks += 1
                level_clicks += 1
                page.wait_for_timeout(200)

            except Exception as e:
                pass
                # print(f"Could not click on {total_clicks + 1} available expand button")
                # break

        print(f"Level {level}: expanded {level_clicks} rows")

        if level_clicks == 0:
            print("No more expandable rows.")
            break

        page.wait_for_timeout(1000)

    print(f"Expanded total: {total_clicks} rows")
    
print_header("Perfect Mile Pull Data", "v1.0.0")

print(f"Hi, {username}")
print()
get_latest_version("PerfectMile", "v1.0.0")

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=Path("PerfectMile"),
        headless=False,
        no_viewport=True,
        args=["--start-maximized"]
    )

    page = browser.pages[0]

    page.goto("https://perfectmile.a2z.com/?visualization=table&breakdown=default&layout=sddonat&periodicity=WEEKLY&timeAggregationConfig=%7B%22value%22%3A%22SIX_WEEKS%22%2C%22type%22%3A%22TimePeriod%22%7D&drilldowns=%5B%7B%22technicalName%22%3A%22parent_country%22%2C%22limit%22%3A0%2C%22performanceRating%22%3Anull%7D%2C%7B%22technicalName%22%3A%22location%22%2C%22limit%22%3A0%2C%22performanceRating%22%3Anull%7D%5D&scopeType=subRegion&scopeValue=UK+%2B+IE&pageFilters=%7B%22filters%22%3A%7B%22dashboard%22%3A%7B%22location_type%22%3A%5B%223P%22%2C%22DS%22%2C%22SC%22%2C%22XP%22%2C%22HQ%22%2C%22WW%22%5D%7D%7D%7D&business=AMZL&profileRegion=EU&profileCountry=UK&analyzeDrilldowns=%5B%5D&metrics=%5B%5D&metricList=%5B%5D")
    if "https://midway-auth.amazon.com/login" in page.url:
        print("Redirected to Midway login. Reloading...")

        while "perfectmile.a2z.com" not in page.url:
            page.wait_for_timeout(1000)
        print("Login completed. Back to PerfectMile.")
            
    input("\nSelect the metrics, change the date range and press Enter to continue...")

    div_table = page.locator('div[data-cy].sc-ZqGJI.eJsAEj')
    div_count = div_table.count()

    print(f"Total tables found: {div_count}")

    for i in range(div_count):
        print(f"\nProcessing table {i + 1}/{div_count}...")

        table = div_table.nth(i)

        expandable_div = table.locator('div[aria-expanded]').first
        aria_expanded = expandable_div.get_attribute("aria-expanded")

        if aria_expanded != "true":
            continue
            # print("Table is not expanded, opening it...")
            # expandable_div.click()
            # page.wait_for_timeout(1000)

        expand_all_rows(page, table, 2)
        
        download_btn = table.locator('button.sc-dUipGc.eWRPys.css-rgh3oe').first
        download_btn.scroll_into_view_if_needed()
        download_btn.wait_for(state="visible")

        with page.expect_download(timeout=(1000 * 60 * 10)) as download_info:
            download_btn.click()

        download = download_info.value
        download_name = download.suggested_filename
        download.save_as(download_name)

        print(f"Downloaded: {download_name}")

        page.wait_for_timeout(1000)

        try:
            expandable_div.click()
        except:
            pass

    print("All downloads completed.")