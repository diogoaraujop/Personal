

# POST
# 	https://mytime.aka.corp.amazon.com/wfc/bridge/ngui/widget/timestamp/record?cancelDeductions=false&token=b3c9cd57-7fba-42ac-9143-8f3f09b09439
 
 
# request body:
# {"joblocation":{},"laborLevel":[],"workRule":{}}

# headers page:
# Referer : https://mytime.aka.corp.amazon.com/wfcstatic/applications/navigator/html5/dist/timestamp/index.html?version=8.1.7.1379&widgetType=timestamphtml&domain=&instanceId=b3c9cd57-7fba-42ac-9143-8f3f09b09439&isHTMLWidget=true&isMinimized=false&modelToken=b3c9cd57-7fba-42ac-9143-8f3f09b09439&serverPath=/wfc&ssid=widgetFrame3818&userLocale=en_GB&widgetId=3818
 
 
# response:
# {"success":true,"deductionsCanceled":false,"savedLatestUsedTransfers":{"clientSideTransfers":[],"maxSize":20,"latestTransferList":true,"isJTSEnable":false},"timestampWithOffset":{"date":1774958400000,"timeZoneOffset":0,"timeZoneName":"(GMT) Greenwich Mean Time","serverDateFormat":"EEEE, MMMM dd, yyyy"}}

import asyncio
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

try:
    async def main():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Open the site — log in manually
            await page.goto("https://mytime.aka.corp.amazon.com")
            # print("Please log in manually in the browser window...")
            await page.wait_for_url("**/wfcstatic/**", timeout=120000)
            # print("Logged in! Capturing session...")

            # Capture cookies and CSRF token from intercepted requests
            csrf_token = None
            token = None

            async def handle_request(request):
                nonlocal csrf_token, token
                if "mytime.aka.corp.amazon.com" in request.url:
                    headers = request.headers
                    if "csrf_tok" in headers:
                        csrf_token = headers["csrf_tok"]
                    # Capture the token from createToken or dataForGrid requests
                    if "token=" in request.url:
                        from urllib.parse import urlparse, parse_qs
                        params = parse_qs(urlparse(request.url).query)
                        if "token" in params:
                            token = params["token"][0]

            page.on("request", handle_request)

            # Wait a bit for background requests to fire and capture CSRF/token
            await page.wait_for_timeout(5000)

            # Date range — today and 2 days ago
            end_date = datetime.now().strftime("%Y-%m-%d 00:00:00.000")
            start_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d 00:00:00.000")
            employee_id = "7737657"  # your employee ID from the request

            (f"CSRF Token: {csrf_token}")
            # print(printf"Token: {token}")

            if not csrf_token or not token:
                print("Could not auto-capture CSRF/token. Navigate to the timecard page manually...")
                await page.wait_for_timeout(10000)  # give more time to browse
                print(f"CSRF Token: {csrf_token}")
                # print(f"Token: {token}")

            # Build the URL
            import urllib.parse
            params = {
                "_uid": f"2-{int(datetime.now().timestamp() * 1000)}",
                "employeeId": employee_id,
                "endDate": end_date,
                "forException": "false",
                "purpose": "-1",
                "refresh": "true",
                "showWorkWeekDivider": "false",
                "startDate": start_date,
                "timeframeId": "9",
                "token": token,
            }
            query_string = urllib.parse.urlencode(params)
            url = f"https://mytime.aka.corp.amazon.com/wfc/bridge/services/emptimecard/rest/1.0/dataForGrid?{query_string}"
            
            content = None

            async def handle_response(response):
                nonlocal content
                if "/dataForGrid" in response.url:
                    content = await response.json()

            page.on("response", handle_response)

            while content is None:
                # print("Waiting for dataForGrid response...")
                await page.wait_for_load_state("networkidle")
                await page.reload()

            result = content
            # Make the request from within the browser context (cookies handled automatically)
            # result = await page.evaluate("""async ({url, csrfToken}) => {
            #     const r = await fetch(url, {
            #         credentials: 'include',
            #         headers: {
            #             'Accept': 'application/json, text/plain, */*',
            #             'Accept-Language': 'en-US,en;q=0.5',
            #             'X-REST-API': 'true',
            #             'KRN-FUNCTIONAL-AREA': 'TIMECARD_EDITOR',
            #             'CSRF_TOK': csrfToken,
            #             'X-Requested-With': 'true',
            #             'Sec-Fetch-Dest': 'empty',
            #             'Sec-Fetch-Mode': 'cors',
            #             'Sec-Fetch-Site': 'same-origin'
            #         }
            #     });
            #     return await r.json();
            # }""", {"url": url, "csrfToken": csrf_token})

            # print(json.dumps(result, indent=2))
            grid_saved = result["grids"]
            for grid in grid_saved:
                gridEndDate = grid["gridEndDate"]
                yesterday = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
                today = datetime.today().strftime("%Y-%m-%d")
                if gridEndDate == today:
                    rows = grid["rows"]
                    for row in rows:
                        if row["groupKey"] == today:
                            items = row["graphicalItems"]
                            for item in items:
                                if item["attributes"]["columnId"] == "scheduleShift":
                                    text = item["attributes"]["text"]
                                    if text != "":
                                        punchIn, punchOut = text.split("-")
                                        print(f"\nPunch In: {punchIn.strip()}, Punch Out: {punchOut.strip()}")
                                    else:
                                        print("\nNo schedule for today")

            await browser.close()

    asyncio.run(main())
except:
    print("Error occured. Try again!")