from datetime import datetime, timedelta
from contextlib import contextmanager
import base64
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
import getpass
import requests, sys

version = "v1.3.0"
TEST_MODE = False
header_script = f"""
    Project     : Punch Automation
    Author      : Diogo Pereira - @diogpere
    Version     : {version}
    Last Update : 28-08-2026
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
CHROMIUM_EXECUTABLE = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = Path.home() / "Documents" / "playwright_profile" / "punches"
SESSION_FILE = PROFILE_DIR / "mytime_session.json"

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


def save_session_data(session_data: dict):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(session_data, indent=2), encoding="utf-8")


def continue_security_key_sign_in(page, timeout_ms=10000):
    """Handle the optional Federate interstitial while redirects settle."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if urlsplit(page.url).hostname == "idp.federate.amazon.com":
            prompt = page.get_by_text("Sign in with your security key", exact=True)
            button = page.get_by_role("button", name="Continue", exact=True)
            if prompt.is_visible() and button.is_visible() and button.is_enabled():
                button.click(timeout=5000)
                print("Clicked Continue on the security-key sign-in page. Complete any security-key prompt if requested.")
                return True
        if page.locator('iframe[id="widgetFrame3818"]').is_visible():
            return False
        page.wait_for_timeout(250)
    return False


def capture_browser_session():
    print("Opening Chrome so you can sign in to MyTime and save the authenticated session.")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            executable_path=CHROMIUM_EXECUTABLE,
            headless=False,
            locale="en-US",
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto('https://mytime.aka.corp.amazon.com/', wait_until='domcontentloaded', timeout=30000)
        continue_security_key_sign_in(page)
        print("Please sign into MyTime in the browser and wait for the dashboard to load.")
        input("Press ENTER after you are logged in and ready to save the session.\n")

        # Verify access before saving: a login page can also contain cookies.
        try:
            punch_button = page.frame_locator('iframe[id="widgetFrame3818"]').locator(
                'xpath=/html/body/div/ui-view/krn-timestamp/div[2]/cc-button/button'
            )
            punch_button.wait_for(state="visible", timeout=30000)
            if not punch_button.is_enabled():
                raise RuntimeError("The MyTime punch control is disabled.")
        except Exception as exc:
            browser.close()
            raise SystemExit(
                "MyTime is not ready to punch. Complete authentication and rerun the script."
            ) from exc

        session_data = {
            "captured_at": datetime.now().isoformat(),
            "cookies": browser.cookies(),
            "document_cookie": page.evaluate("document.cookie"),
            "meta_csrf": page.evaluate("document.querySelector('meta[name=\"csrf-token\"]')?.content || ''"),
            "token": page.evaluate("document.querySelector('input[name=\"token\"]')?.value || document.querySelector('[data-token]')?.dataset?.token || ''"),
            "url": page.url,
        }
        save_session_data(session_data)
        print(f"Saved authenticated session to {SESSION_FILE}")
        # Closing cleanly flushes cookies and site storage to the persistent
        # Chrome profile, which run_punch reuses at each scheduled time.
        browser.close()
        print("Browser closed.")


def load_session_data() -> dict:
    if not SESSION_FILE.exists():
        raise FileNotFoundError(f"No saved MyTime session found at {SESSION_FILE}.")
    return json.loads(SESSION_FILE.read_text(encoding="utf-8"))


def build_authenticated_session() -> requests.Session:
    session = requests.Session()
    saved = load_session_data()
    for cookie in saved.get("cookies", []):
        session.cookies.set(
            cookie.get("name"),
            cookie.get("value"),
            domain=cookie.get("domain"),
            path=cookie.get("path") or "/",
        )
    return session


@contextmanager
def capture_punch_requests(page, run_label):
    """Record API candidates only during submission; never replay traffic."""
    captured = []
    request_records = {}

    def on_request(request):
        if request.resource_type not in ("xhr", "fetch"):
            return
        try:
            body = request.post_data_buffer
            record = {
                "method": request.method,
                "url": request.url,
                "headers": request.all_headers(),
                "body_base64": base64.b64encode(body).decode("ascii") if body is not None else None,
                "status": None,
            }
            captured.append(record)
            request_records[request] = record
        except Exception:
            print("Could not capture one API request.")

    def on_response(response):
        record = request_records.get(response.request)
        if record is not None:
            record["status"] = response.status

    page.on("request", on_request)
    page.on("response", on_response)
    try:
        yield
    finally:
        page.remove_listener("request", on_request)
        page.remove_listener("response", on_response)
        try:
            # Keep authentication headers and payloads outside the source repo.
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            destination = PROFILE_DIR / f"punch_api_{datetime.now():%Y%m%d_%H%M%S_%f}.json"
            destination.write_text(json.dumps({
                "run_label": run_label,
                "captured_at": datetime.now().isoformat(),
                "requests": captured,
            }, indent=2), encoding="utf-8")
            print(f"Saved {len(captured)} API candidates to {destination}")
        except Exception:
            # Recording failures must not trigger a duplicate punch.
            print("Could not save the API capture; punch handling will continue.")


def run_punch(run_label: str) -> bool:
    """
    Executes one punch in MyTime using the saved Chrome session profile.
    Returns True on success (or after sending message), False if retries exhausted.
    """
    data = [f"Punch run: {run_label}", f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
    retry = 0

    while retry < max_retry:
        submission_started = False
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    str(PROFILE_DIR),
                    executable_path=CHROMIUM_EXECUTABLE,
                    headless=False,
                )
                page = browser.pages[0] if browser.pages else browser.new_page()
                print(f"Using Chrome profile: {PROFILE_DIR}")
                print("Loading MyTime...")
                page.goto('https://mytime.aka.corp.amazon.com/', wait_until="domcontentloaded", timeout=30000)
                continue_security_key_sign_in(page)
                print(f"MyTime page loaded: {page.url}")

                iframe_element = page.wait_for_selector('iframe[id="widgetFrame3818"]', timeout=20000)
                iframe = iframe_element.content_frame()

                if TEST_MODE:
                    print("TEST_MODE enabled: submission click skipped.")
                    input("Press ENTER to close Chrome and finish the test.\n")
                    browser.close()
                    return True

                with capture_punch_requests(page, run_label):
                    submission_started = True
                    iframe.locator('xpath=/html/body/div/ui-view/krn-timestamp/div[2]/cc-button/button').click()
                    page.wait_for_timeout(2000)
                    try:
                        iframe.locator(
                            '//html/body/div/ui-view/krn-timestamp/krn-result-message/div/div/div[1]/span[1]'
                        ).wait_for(state="visible", timeout=10000)
                    except Exception:
                        pass  # Save traffic even when confirmation is missing.

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
                    browser.close()
                    return True

                except Exception:
                    msg = "Confirmation message not found or not visible."
                    print(msg)
                    data.append(msg)
                    browser.close()
                    return False

        except Exception as e:
            if submission_started:
                print("Submission may have reached MyTime. Check it manually; this punch will not be retried.")
                return False
            retry += 1
            err = f"Error (attempt {retry}/{max_retry}): {e}"
            print(err)
            data.append(err)
            if retry < max_retry:
                retry_msg = "Trying again..."
                print(retry_msg)
                data.append(retry_msg)
                time.sleep(5)

    data.append("Max retries reached. Closing the program.")
    if username == "diogpere":
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
    # Always open immediately so expired authentication can be renewed before
    # waiting. Chrome reuses the saved profile and its site permissions.
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


if __name__ == "__main__":
    main()
