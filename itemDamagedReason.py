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


def get_node_id(tracking_id: str) -> str | None:
    try:
        response = session.post(
            "https://logistics.amazon.co.uk/station/proxyapigateway/data",
            json={
                "resourcePath": "/os/getPackageHistoryData",
                "httpMethod": "post",
                "processName": "oculus",
                "requestBody": {
                    "packageId": tracking_id,
                    "pageSize": 100,
                    "pageToken": None,
                    "startTime": None,
                    "endTime": None,
                },
            },
        )
        if response.status_code != 200:
            return None
        for event in response.json().get("packageHistory", []):
            source = event.get("source")
            if source:
                return source
    except Exception as e:
        print(f"Error getting node ID for {tracking_id}: {e}")
    return None


def get_damage_reason(tracking_id: str) -> str:
    print(f" Checking\t{tracking_id = }")

    try:
        node_id = get_node_id(tracking_id)
        if not node_id:
            return "Station Not Found"

        print(f"   Detected station: {node_id}")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }

        response = session.post(
            "https://logistics.amazon.co.uk/station/proxyapigateway/data",
            headers=headers,
            json={
                "httpMethod": "post",
                "processName": "nnsNAWS",
                "requestBody": {
                    "nodeId": node_id,
                    "requireMetadata": True,
                    "scannableIds": [tracking_id],
                    "taskItemTypes": ["NEEDS_APPROVAL_DAMAGED"],
                },
                "resourcePath": "/nnsnaws/nnsnaws/getTaskItems",
            },
        )

        data = response.json()
        print(f"   DEBUG response keys: {list(data.keys())}")
        task_items = data.get("taskItems", [])
        print(f"   DEBUG taskItems count: {len(task_items)}")

        if not task_items:
            # Try without filtering by task type
            response2 = session.post(
                "https://logistics.amazon.co.uk/station/proxyapigateway/data",
                headers=headers,
                json={
                    "httpMethod": "post",
                    "processName": "nnsNAWS",
                    "requestBody": {
                        "nodeId": node_id,
                        "requireMetadata": True,
                        "scannableIds": [tracking_id],
                    },
                    "resourcePath": "/nnsnaws/nnsnaws/getTaskItems",
                },
            )
            data2 = response2.json()
            task_items2 = data2.get("taskItems", [])
            print(f"   DEBUG (no type filter) taskItems count: {len(task_items2)}")
            if task_items2:
                print(f"   DEBUG first item: {task_items2[0]}")
            else:
                print(f"   DEBUG full response (no filter): {data2}")

        for item in task_items:
            print(f"   DEBUG item keys: {list(item.keys())}")
            if item.get("scannableId") == tracking_id:
                metadata = item.get("taskItemMetadata", {})
                print(f"   DEBUG metadata keys: {list(metadata.keys())}")
                asin_details = metadata.get("asinDetails", [])
                if asin_details and isinstance(asin_details, list):
                    print(f"   DEBUG asinDetails[0] keys: {list(asin_details[0].keys())}")
                    print(f"   DEBUG asinDetails[0]: {asin_details[0]}")
                    return asin_details[0].get("itemDamagedReason", "N/A")

        return "Not Found"

    except Exception as e:
        print(f"Error checking {tracking_id}: {str(e)}")
        return "Error"


def main(tracking_id_list: list[str]):
    print("Please Wait...")
    csv_string = "tracking_id,damage_reason"
    damage_reasons = {}  # To keep track of counts

    for tracking_id in tracking_id_list:
        damage_reason = get_damage_reason(tracking_id)
        csv_string += f"\n{tracking_id},{damage_reason}"
        damage_reasons[damage_reason] = damage_reasons.get(damage_reason, 0) + 1

    output_path = r"C:\Users\bentgeok\Desktop\Python"
    filename = f"damage_reasons_{strftime('%Y%m%d%H%M')}.csv"
    full_path = os.path.join(output_path, filename)

    with open(full_path, "wt+") as csv:
        csv.write(csv_string)

    print(f"\nCSV written to: {filename}")
    print("\nDamage Reason Summary:")
    for reason, count in damage_reasons.items():
        print(f"  {reason}: {count}")


def user_list() -> list[str]:
    print("Paste Tracking IDs below and press enter twice when done:")
    tracking_id_list: list[str] = []
    while True:
        tracking_id = input()
        if tracking_id == "":
            return tracking_id_list
        tracking_id_list.append(tracking_id)


if __name__ == "__main__":
    main(user_list())
