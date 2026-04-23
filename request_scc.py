from typing import TypedDict
from requests import Session as new_http_session
from requests_kerberos import HTTPKerberosAuth, DISABLED
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning
from time import strftime
import re
import os
import requests

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
    raise SystemExit(3)

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
    raise SystemExit(4)

# Initialize logistics session
session.get("https://logistics.amazon.co.uk/station/dashboard/problemsolve")

tracking_id = "UK4090075843"

def get_shipment_info(tracking_id: str) -> dict:
    response = session.post(
        "https://logistics.amazon.co.uk/station/proxyapigateway/data",
        json={
            "resourcePath": "/os/getPackageDetailData",
            "httpMethod": "get",
            "processName": "oculus",
            "requestParams": {
                "trackingId": [tracking_id],
                "nodeId": ["DIG1"]
            }
    },
)
    if response.status_code != 200:
        return None
    data = response.json().get("packageDetail", [])
    package = data["packageData"]
    routeInfo = package["routeInfo"]
    dsp = routeInfo["provider"]
    print(f"Shipment {tracking_id} is with {dsp}")

get_shipment_info(tracking_id)