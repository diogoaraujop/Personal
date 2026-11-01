# Rota updater

This package adds an **Update rota from AtoZ** button to Google Sheets. A small Google Apps Script helper reads and saves cells using SpreadsheetApp. Version 3.1 opens each associate's manager timecard in a second tab using the login from the rota, then makes a same-origin fetch with `credentials: 'include'` from that AtoZ tab. Associates are processed sequentially. Tabs close automatically after success or failure. Keep the original rota tab open throughout.

## Updating to version 4.1

Replace the entire Tampermonkey script, including its metadata header, with `rota-updater.user.js`. This copy includes the helper URL and token provided during setup. Save and reload Google Sheets. Accept Tampermonkey's new tab/storage permissions if prompted. Replace Code.gs too, preserving your configured ROTA.spreadsheetId and layout settings. Deploy a NEW VERSION of the existing web app deployment so its /exec URL stays the same. Version 4 checks the helper version before processing. The helper still needs the spreadsheet authorization described during setup.

## Setup

1. In the rota spreadsheet, open **Extensions > Apps Script** and paste `Code.gs`.
2. Set `ROTA.spreadsheetId` to the ID between `/d/` and `/edit` in the spreadsheet URL. Defaults match your screenshot: identity headers in row 1, dates in row 3, employees from row 5, `Employee ID` and `User ID` headers. Merged header cells are supported because their text is in row 1. Dates can be real sheet dates, `dd/mm/yyyy`, or `yyyy-mm-dd`.
3. In Apps Script **Project Settings > Script properties**, add `ROTA_TOKEN` with a randomly generated secret of at least 32 characters. Use the same value in the userscript's `CONFIG.token`.
4. **Deploy > New deployment > Web app**. For personal use choose **Execute as: Me**, **Who has access: Only myself**. Authorize spreadsheet access. Do not deploy with anonymous/public access. Workspace settings may restrict web apps.
5. Copy the deployment URL ending in `/exec` into `CONFIG.helperUrl`. Open it in the same browser and sign in; it should say `Rota helper ready`.
6. Create a new Tampermonkey script and replace its contents with `rota-updater.user.js`, including the configured URL and token. Disable the old rota updater to avoid duplicate buttons.
7. Sign in to AtoZ with access to the employees' manager timecards. Open the target spreadsheet tab, choose a date range of up to seven days, and click **Update rota from AtoZ**.

## Rules

- Version 4.1 also creates SICK from approved timeOff records whose type explicitly matches Sick, Sickness, SickLeave, or SicknessAbsence, optionally with TimeOff_GBR prefix and Days/Hours suffix. Matching ignores spaces, underscores, hyphens and case. These are narrow example-based rules, not yet validated against a real sickness response. Family sickness, unknown types, pending/rejected/cancelled time off, punches and anomalies do not establish sickness. HOL wins over SICK on overlapping dates. Existing SICK cells remain preserved; new SICK can replace blank/IN/OFF/HOL cells. Update and redeploy Code.gs alongside the userscript.
- Version 4.2 saves and verifies each associate immediately before opening the next tab. Stop cancels checking and discards unsent changes; previously saved changes remain. Stop also works during saving: it waits for the in-flight save to finish, then prevents further associates from running. A submitted server-side write cannot be undone by Stop. Save failures stop the run because some cells may already have changed. No helper update is required when upgrading from version 4.1.
- Read employee IDs/logins from the sheet; never use the sample employee ID as a default.
- Use `timeCardDayList[].date`, not the request's overall timestamp range. Your sample lists approved holiday on 8, 9, 10 and 11 September 2026, including a daily entry on the 11th.
- Approved annual leave/vacation/bank holiday types listed in `HOLIDAY_TYPES` become `HOL`. All other time-off types and all anomalies are ignored. Approved HOL overrides the schedule code for that date. Rejected, cancelled and pending requests are ignored.
- Blank, IN, OFF and HOL cells are synchronized from AtoZ. Other manual codes and formulas are preserved. Non-deleted shifts mean IN; an explicitly empty/deleted-only shifts list means OFF. Punches alone do not define the rota. Missing response dates remain unchanged. Existing HOL can become IN/OFF when the returned holiday data no longer contains an approved holiday. Formatting is preserved.
- Any approved partial-day time off also changes the daily IN code, matching the requested day-code behaviour; hours are not prorated.
- All associate-page errors (HTTP, network, timeout, closed tab, invalid response, component error or employee mismatch) are logged and skipped. Their cells remain unchanged. Helper read/save failures still stop the run. Tabs open in the background and close after success or failure. The summary counts skipped associates; successfully checked associates can still be saved.
- Recheck employee identity and the original cell value before each write and read saved values back. Apps Script locks serialize helper requests but cannot lock out human edits; avoid sorting/editing the rota during a run. Writes are not transactional: a failure during saving can leave some changes applied. Inspect the sheet/version history before rerunning.

## Authentication and validation limits

The AtoZ tab uses its signed-in session; opening a page does not grant manager access that your account lacks. If sign-in redirects discard the job fragment, finish signing in and rerun from the rota. The run times out after three minutes per associate (API fetch timeout: one minute). Google helper requests still use Tampermonkey cross-origin requests with browser cookies (`anonymous: false`). HTML instead of JSON usually means sign-in is required. This has not been tested against your live accounts, and no live rota has been modified. Temporary jobs contain an employee identity and date range; results contain only date/code pairs in Tampermonkey storage, removed after completion or timeout. Abandoned expired jobs are removed on the next script load. Full API responses are not stored.

The supplied response is for a different employee from the example POST. Tests use its own identity; a live mismatched response is rejected.

Official references: [Apps Script web apps](https://developers.google.com/apps-script/guides/web), [Tampermonkey requests](https://www.tampermonkey.net/documentation.php#api:GM_xmlhttpRequest).
