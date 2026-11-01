"""Reuse Firefox MyTime/Midway cookies; fall back to interactive Chrome login."""
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
import time
from urllib.parse import urlsplit
from playwright.sync_api import Error

URL = "https://mytime.aka.corp.amazon.com/"
PROFILE_DIR = Path(os.environ["LOCALAPPDATA"]) / "PunchesAutoLogin/chrome"
BUTTON = 'xpath=/html/body/div/ui-view/krn-timestamp/div[2]/cc-button/button'


def firefox_cookies():
    root = Path(os.environ["APPDATA"]) / "Mozilla/Firefox/Profiles"
    def modified(profile):
        return max((p.stat().st_mtime for p in [profile / "cookies.sqlite", profile / "cookies.sqlite-wal"] if p.exists()), default=0)
    for profile in sorted(root.glob("*"), key=modified, reverse=True):
        try:
            connection = sqlite3.connect((profile / "cookies.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
            try:
                rows = connection.execute(
                    "SELECT host,name,value,path,expiry,isSecure,isHttpOnly,sameSite FROM moz_cookies "
                    "WHERE host IN (?,?,?,?) AND expiry > ? AND originAttributes = ''",
                    ("mytime.aka.corp.amazon.com", ".mytime.aka.corp.amazon.com",
                     "midway-auth.amazon.com", ".midway-auth.amazon.com", time.time()),
                ).fetchall()
            finally:
                connection.close()
            if rows:
                return [dict(domain=h, name=n, value=v, path=p, expires=e, secure=bool(s),
                             httpOnly=bool(http), sameSite={0:"None",1:"Lax",2:"Strict"}.get(ss,"Lax"))
                        for h,n,v,p,e,s,http,ss in rows]
        except (OSError, sqlite3.Error):
            continue
    return []


def wait_ready(page, seconds):
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    except Error:
        pass
    deadline = time.monotonic() + seconds
    security_key_continued = False
    while time.monotonic() < deadline and not page.is_closed():
        try:
            if not security_key_continued and urlsplit(page.url).hostname == "idp.federate.amazon.com":
                prompt = page.get_by_text("Sign in with your security key", exact=True)
                continue_button = page.get_by_role("button", name="Continue", exact=True)
                if prompt.is_visible() and continue_button.is_visible() and continue_button.is_enabled(timeout=1000):
                    continue_button.click(timeout=5000)
                    security_key_continued = True
                    print("Clicked Continue on the security-key sign-in page. Complete any security-key prompt if requested.", flush=True)
            button = page.frame_locator('iframe[id="widgetFrame3818"]').locator(BUTTON)
            if button.is_visible() and button.is_enabled(timeout=1000):
                return True
            page.wait_for_timeout(500)
        except Error:
            if page.is_closed():
                return False
    return False


@contextmanager
def authenticated_mytime(playwright, login_timeout=300):
    """Yield a page only after the punch control is visible and enabled. Never click it."""
    cookies = firefox_cookies()
    browser = None
    context = None
    ready_page = None
    try:
        if cookies:
            print(f"Trying {len(cookies)} MyTime/Midway cookies from Firefox.", flush=True)
            try:
                browser = playwright.chromium.launch(channel="chrome", headless=False, timeout=30000)
                context = browser.new_context(locale="en-US")
                context.add_cookies(cookies)
                cookies.clear()
                page = context.new_page()
                if wait_ready(page, 30):
                    ready_page = page
            except Error:
                print("Firefox session could not be verified.")
        if ready_page is not None:
            print("MyTime ready using Firefox cookies.", flush=True)
            yield ready_page
            return
    finally:
        cookies.clear()
        if context:
            context.close()
        if browser:
            browser.close()

    print("Opening saved Chrome profile. Complete MyTime login if prompted; waiting up to five minutes.", flush=True)
    context = playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR), channel="chrome", headless=False, locale="en-US", timeout=30000)
    try:
        page = context.pages[0] if context.pages else context.new_page()
        if not wait_ready(page, login_timeout):
            raise RuntimeError("MyTime punch control is not ready; no punch submitted")
        print("MyTime ready using the saved browser profile.", flush=True)
        yield page
    finally:
        context.close()
