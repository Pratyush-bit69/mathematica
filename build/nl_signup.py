#!/usr/bin/env python3
"""Create the Netlify account and claim a permanent site URL."""
import os
import re
import secrets
import string
import sys
import time

from playwright.sync_api import sync_playwright

PROFILE = "/tmp/opencode/whatsapp-profile"
OUT = "/tmp/opencode/shots"
EMAIL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SITE_EMAIL", "")
PASSFILE = "/tmp/opencode/netlify-pass.txt"
if os.path.exists(PASSFILE):
    PASSWORD = open(PASSFILE).read().strip()
else:
    PASSWORD = "Mx" + secrets.choice(string.ascii_letters + string.digits) \
        + secrets.token_urlsafe(14) + "!7"
    open(PASSFILE, "w").write(PASSWORD)
os.makedirs(OUT, exist_ok=True)
SITE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PROFILE,
        executable_path="/usr/bin/brave",
        headless=False,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-brave-extension", "--no-first-run",
              "--no-default-browser-check"],
        viewport={"width": 1440, "height": 900},
        ignore_default_args=["--disable-extensions"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    # ---------------------------------------------------- sign up
    page.goto("https://app.netlify.com/signup/email", wait_until="domcontentloaded",
              timeout=90000)
    time.sleep(6)
    print("signup url:", page.url)
    print("fields:")
    for i in range(page.locator("input").count()):
        el = page.locator("input").nth(i)
        try:
            print("  ", el.get_attribute("type"), "| name:", el.get_attribute("name"),
                  "| ph:", el.get_attribute("placeholder"))
        except Exception:
            pass
    try:
        page.fill("input[type=email]", EMAIL)
    except Exception as e:
        print("email fill:", str(e)[:120])
    try:
        pw = page.locator("input[type=password]").first
        pw.fill(PASSWORD)
    except Exception as e:
        print("pw fill:", str(e)[:120])
    time.sleep(0.5)
    page.screenshot(path=f"{OUT}/nl-signup.png", full_page=True)
    # submit
    clicked = False
    for sel in ["button[type=submit]", "form button", "button:has-text('Sign up')",
                "button:has-text('Continue')"]:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click()
                clicked = True
                print("submitted via", sel)
                break
        except Exception:
            continue
    if not clicked:
        page.keyboard.press("Enter")
        print("submitted via Enter")
    time.sleep(12)
    page.screenshot(path=f"{OUT}/nl-signup2.png", full_page=True)
    body = page.inner_text("body")
    print("---- after signup ----")
    print(body[:900])
    print("url:", page.url)
    ctx.close()
