#!/usr/bin/env python3
"""Create the Netlify account via the Google OAuth flow (already signed in)."""
import os
import sys
import time

from playwright.sync_api import sync_playwright

PROFILE = "/tmp/opencode/whatsapp-profile"
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)

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
    page.goto("https://app.netlify.com/signup", wait_until="domcontentloaded",
              timeout=90000)
    time.sleep(7)
    print("url:", page.url)
    # look for a Google entry point
    for sel in ["button:has-text('Google')", "a:has-text('Google')",
                "text=Continue with Google", "button:has-text('Git provider')",
                "a:has-text('Sign up with a Git provider')"]:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                print("clicking", sel)
                loc.click()
                break
        except Exception:
            continue
    time.sleep(9)
    page.screenshot(path=f"{OUT}/nl-google1.png", full_page=True)
    print("url now:", page.url)
    print(page.inner_text("body")[:800])
    # google account chooser
    try:
        for sel in ["div[role='listitem']", "[data-identifier]",
                    "div[jsname='aigfmp']"]:
            loc = page.locator(sel)
            if loc.count():
                print("google chooser items:", loc.count())
                break
    except Exception:
        pass
    ctx.close()
