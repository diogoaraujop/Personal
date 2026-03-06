from datetime import datetime, timedelta
import time
from playwright.sync_api import sync_playwright
import getpass
import requests

header_script = f"""
    Project     : Punch Automation
    Author      : Diogo Pereira - @diogpere
    Version     : 1.0.0
    Last Update : 06-03-2026
    """

print()
print(header_script)
print()

webhook_url = 'https://hooks.slack.com/triggers/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'
username = getpass.getuser()
USER_DATA_DIR = f"C:/Users/{username}/Documents/playwright_profile/punches"

punch_time_first_default = "12:00"

punch_time_first = input(
    f"Type what time you would like your first punch (HH:MM) or press ENTER to use the default time ({punch_time_first_default}):\n"
)

if punch_time_first.strip() == "":
    punch_time_first = punch_time_first_default

# Parse times
first_dt_time = datetime.strptime(punch_time_first, "%H:%M").time()
today = datetime.now().date()
first_punch_dt = datetime.combine(today, first_dt_time)

second_punch_dt = first_punch_dt + timedelta(minutes=30)

print(f"Your punches will be done at {first_punch_dt.strftime('%H:%M')} and {second_punch_dt.strftime('%H:%M')}")

max_retry = 3


def send_slack(message: str):
    # Adjust "message"/"text" depending on how your Slack trigger is configured
    response = requests.post(webhook_url, json={"message": message})
    if response.status_code == 200:
        print("Slack message sent.")
    else:
        print(f"Slack error: {response.status_code} - {response.text}")


def run_punch(run_label: str) -> bool:
    """
    Executes one punch in MyTime.
    Returns True on success (or after sending message), False if retries exhausted.
    """
    data = [f"Punch run: {run_label}", f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
    retry = 0

    while retry < max_retry:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    USER_DATA_DIR,
                    headless=False,
                )
                page = browser.pages[0]
                page.goto('https://mytime.aka.corp.amazon.com/')

                # Wait for iframe and click button
                iframe_element = page.wait_for_selector('iframe[id="widgetFrame3818"]', timeout=20000)
                iframe = iframe_element.content_frame()

                iframe.locator('xpath=/html/body/div/ui-view/krn-timestamp/div[2]/cc-button/button').click()

                time.sleep(2)

                try:
                    timestamp_text_el = iframe.locator(
                        '//html/body/div/ui-view/krn-timestamp/krn-result-message/div/div/div[1]/span[1]'
                    )
                    timestamp_text_el.wait_for(state="visible", timeout=5000)

                    timestamp_text2 = iframe.locator(
                        '//html/body/div/ui-view/krn-timestamp/krn-result-message/div/div/div[1]/span[2]'
                    ).text_content()
                    timestamp_text = timestamp_text_el.text_content()

                    confirmation = f"Confirmation: {timestamp_text} {timestamp_text2}"
                    print(confirmation)
                    data.append(confirmation)

                except Exception:
                    msg = "Confirmation message not found or not visible."
                    print(msg)
                    data.append(msg)

                # Close context (with-block does this automatically)
                message = "\n".join(data)
                send_slack(message)
                return True  # success, no more retries

        except Exception as e:
            retry += 1
            err = f"Error (attempt {retry}/{max_retry}): {e}"
            print(err)
            data.append(err)
            if retry < max_retry:
                retry_msg = "Trying again..."
                print(retry_msg)
                data.append(retry_msg)
                time.sleep(5)

    # If we reach here, retries failed
    data.append("Max retries reached. Closing the program.")
    if username == "diogpere":  # Only send Slack message if it's the main user (optional)
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


# --- MAIN FLOW ---

now = datetime.now()

# If the chosen time is already in the past, schedule for tomorrow (optional safety)
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
run_punch("First punch")

print(f"Waiting for second punch at {second_punch_dt.strftime('%Y-%m-%d %H:%M')}")
sleep_until(second_punch_dt)

print("Running SECOND punch...")
run_punch("Second punch")

print("Both punches done. Exiting.")
