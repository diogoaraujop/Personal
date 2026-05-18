from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
from getpass import getuser
import sys
from datetime import time
import requests, os, re
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning
from requests import Session as new_http_session
from requests_kerberos import HTTPKerberosAuth, DISABLED

disable_warnings(category=InsecureRequestWarning)
session = new_http_session()
session.verify = False
session.auth = HTTPKerberosAuth(mutual_authentication=DISABLED)

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

response = session.get(
    f"https://datanet-service.amazon.com/jobRun/-/25550658/{(datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")}/{(datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")}T00:00:00Z/{(datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")}T23:59:59Z"
)
data = None
if response.status_code == 200:
    data = response.json()
    print()
else:
    print(f"Error: {response.status_code}")
    print(f"Error message: {response.text}")
    print(f"Error message: {response.text()}")
    
if data:
    jobRuns = data["jobRuns"]
    for job in jobRuns:
        # print(json.dumps(jobRuns, indent=4))
        status = job["status"]
        if status == "SUCCESS":
            id = job["id"]
            print(id)
            
            
            
###############################################################################           
# today = datetime.today()
# today_str = today.strftime("%Y-%m-%d")
# yesterday = today - timedelta(days=1)
# yesterday_str = yesterday.strftime("%Y-%m-%d")
# with sync_playwright() as p:
#     browser = p.chromium.launch_persistent_context(
#         user_data_dir=r"C:\Users\diogpere\Documents\playwright_profiles\dailyupload",
#         headless=False,
#         no_viewport=True,
#         args=["--start-maximized"],
#     )

#     page = browser.pages[0]

#     jobRun = None
#     def handle_response(response):
#         global jobRun
#         if "/jobRun" in response.url and response.status == 200:
#             data = response.json()
#             page.remove_listener("response", handle_response)
#             jobRun = data.get("jobRuns", {})
#         return

#     page.on("response", handle_response)
#     page.goto(f"https://datacentral.a2z.com/datanet/etl-manager/jobs/25550658/runs?from_date={yesterday_str}&to_date={today_str}")

#     while jobRun == None:
#         page.wait_for_timeout(1000)
#         print("Waiting for response.")

#     print()
    
    