#!/usr/bin/env python3
"""Open a visible Brave window at Netlify Drop so the site can be published
to a permanent *.netlify.app address."""
import os
import sys
import time

from playwright.sync_api import sync_playwright

PROFILE = "/tmp/opencode/whatsapp-profile"
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)
URL = sys.argv[1] if len(sys.argv) > 1 else "https://app.netlify.com/drop"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PROFILE,
        executable_path="/usr/bin/brave",
        headless=False,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-brave-extension", "--no-first-run",
              "--no-default-browser-check", "--start-maximized"],
        viewport={"width": 1440, "height": 900},
        ignore_default_args=["--disable-extensions"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(8)
    page.screenshot(path=f"{OUT}/deploy-page.png")
    print("URL:", page.url)
    print("---- text ----")
    print(page.inner_text("body")[:900])
    print("---- file inputs ----")
    for i in range(page.locator("input[type=file]").count()):
        print("  file input", i)
    print("---- buttons ----")
    for b in page.locator("button, a").all()[:24]:
        try:
            t = (b.inner_text() or "").strip()[:40]
            if t:
                print("  ", t)
        except Exception:
            pass
    print("OPEN — leave this window open.")
    # keep it alive
    while True:
        time.sleep(10)
