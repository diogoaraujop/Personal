from datetime import datetime, timedelta
import argparse
from mytime_auto_login import authenticated_mytime
import json
import os
from pathlib import Path
import time
from playwright.sync_api import sync_playwright
import getpass
import requests, sys

version = "v1.4.0-auto-login"
TEST_MODE = False
header_script = f"""
    Project     : Punch Automation
    Author      : Diogo Pereira - @diogpere
    Version     : {version}
    Last Update : 07-09-2026
    """

print()
print(header_script)
print()

def get_latest_version():
    print("Checking for updates...")
    repo_name = "Personal"
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
    

# if not TEST_MODE:
#     get_latest_version()

webhook_url = os.environ.get("PUNCHES_SLACK_WEBHOOK_URL") or (__import__("pathlib").Path(__file__).with_name("chime-webhook.local-secret").read_text(encoding="utf-8").strip() if __import__("pathlib").Path(__file__).with_name("chime-webhook.local-secret").exists() else "")
username = getpass.getuser()
punch_time_first_default = "12:00"

max_retry = 3


def send_slack(message: str):
    # Adjust "message"/"text" depending on how your Slack trigger is configured
    if not webhook_url:
        print("Slack webhook is not configured; skipping notification.")
        return
    try:
        response = requests.post(webhook_url, json={"message": message}, timeout=10)
        if 200 <= response.status_code < 300:
            print("Slack message sent.")
        else:
            print(f"Slack notification failed (HTTP {response.status_code}).")
    except requests.exceptions.RequestException:
        # Do not expose the webhook URL or turn notification failure into a
        # failed punch after MyTime has already confirmed submission.
        print("Slack notification failed due to a network error or timeout.")


def capture_browser_session():
    """Check readiness only. No credential exports, punch clicks, or notifications."""
    with sync_playwright() as playwright:
        with authenticated_mytime(playwright):
            print("Authentication verified. No punch submitted.")


def run_punch(run_label: str) -> bool:
    """
    Executes one punch in MyTime using Firefox cookies or an authenticated Chrome profile.
    Returns True on success (or after sending message), False if retries exhausted.
    """
    data = [f"Punch run: {run_label}", f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
    retry = 0

    while retry < max_retry:
        submission_started = False
        try:
            with sync_playwright() as p:
                with authenticated_mytime(p) as page:
                    iframe_element = page.wait_for_selector('iframe[id="widgetFrame3818"]', timeout=20000)
                    iframe = iframe_element.content_frame()

                    if TEST_MODE:
                        print("TEST_MODE enabled: submission click skipped.")
                        return True

                    submission_started = True
                    iframe.locator('xpath=/html/body/div/ui-view/krn-timestamp/div[2]/cc-button/button').click()
                    page.wait_for_timeout(2000)
                    try:
                        iframe.locator(
                            '//html/body/div/ui-view/krn-timestamp/krn-result-message/div/div/div[1]/span[1]'
                        ).wait_for(state="visible", timeout=10000)
                    except Exception:
                        pass  # The confirmation check below determines the result.

                    try:
                        timestamp_text_el = iframe.locator(
                            '//html/body/div/ui-view/krn-timestamp/krn-result-message/div/div/div[1]/span[1]'
                        )
                        timestamp_text_el.wait_for(state="visible", timeout=10000)

                        timestamp_text2 = iframe.locator(
                            '//html/body/div/ui-view/krn-timestamp/krn-result-message/div/div/div[1]/span[2]'
                        ).text_content()
                        timestamp_text = timestamp_text_el.text_content()

                        confirmation = f"Confirmation: {timestamp_text} {timestamp_text2}"
                        print(confirmation)
                        data.append(confirmation)
                        send_slack("\n".join(data))
                        return True

                    except Exception:
                        msg = "Confirmation message not found or not visible."
                        print(msg)
                        data.append(msg)
                        return False

        except Exception as e:
            if submission_started:
                print("Submission may have reached MyTime. Check it manually; this punch will not be retried.")
                return False
            retry += 1
            err = f"Error (attempt {retry}/{max_retry}): {type(e).__name__}"
            print(err)
            data.append(err)
            if retry < max_retry:
                retry_msg = "Trying again..."
                print(retry_msg)
                data.append(retry_msg)
                time.sleep(5)

    data.append("Max retries reached. Closing the program.")
    if username == "diogpere" and not TEST_MODE:
        send_slack("\n".join(data))
    return False


def sleep_until(target_dt: datetime):
    """Sleep until the given datetime (rounded to no more than 60s chunks)."""
    while True:
        now = datetime.now()
        if now >= target_dt:
            break
        seconds_left = (target_dt - now).total_seconds()
        # Don't sleep longer than 60s to keep some responsiveness
        sleep_time = min(60, max(1, int(seconds_left)))
        print(f"Current time: {now.strftime('%H:%M:%S')}. Sleeping {sleep_time} seconds until {target_dt.strftime('%H:%M')}.")
        time.sleep(sleep_time)


def main():
    # Verify authentication now and again at each scheduled punch.
    capture_browser_session()

    punch_time_first = (
        punch_time_first_default
        if TEST_MODE
        else input(
            f"Type what time you would like your first punch (HH:MM) or press ENTER to use the default time ({punch_time_first_default}):\n"
        )
    )

    if punch_time_first.strip() == "":
        punch_time_first = punch_time_first_default

    first_dt_time = datetime.strptime(punch_time_first, "%H:%M").time()
    today = datetime.now().date()
    first_punch_dt = datetime.combine(today, first_dt_time)
    second_punch_dt = first_punch_dt + timedelta(minutes=30)

    print(f"Your punches will be done at {first_punch_dt.strftime('%H:%M')} and {second_punch_dt.strftime('%H:%M')}")

    now = datetime.now()
    if first_punch_dt <= now:
        print(
            f"Warning: {first_punch_dt.strftime('%H:%M')} is already past for today. "
            "Scheduling punches for tomorrow."
        )
        first_punch_dt = first_punch_dt + timedelta(days=1)
        second_punch_dt = second_punch_dt + timedelta(days=1)

    print(f"Waiting for first punch at {first_punch_dt.strftime('%Y-%m-%d %H:%M')}")
    sleep_until(first_punch_dt)

    print("Running FIRST punch...")
    first_success = run_punch("First punch")

    print(f"Waiting for second punch at {second_punch_dt.strftime('%Y-%m-%d %H:%M')}")
    sleep_until(second_punch_dt)

    print("Running SECOND punch...")
    second_success = run_punch("Second punch")

    if first_success and second_success:
        print("Both punches done. Exiting.")
    else:
        print("One or more punches could not be confirmed. Check MyTime before retrying.")


def cli():
    parser = argparse.ArgumentParser(description="Punch scheduler with Firefox-first MyTime login")
    parser.add_argument("--test-auth", action="store_true", help="Verify login only; no punches, scheduling, or Slack messages")
    args = parser.parse_args()
    if args.test_auth:
        capture_browser_session()
    else:
        main()


if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        print("Interrupted by user.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"Stopped ({type(exc).__name__}). Check MyTime before retrying any punch.")
        raise SystemExit(1)
