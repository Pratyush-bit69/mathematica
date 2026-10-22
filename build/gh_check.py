#!/usr/bin/env python3
"""Inspect the GitHub repo through the user's live browser session."""
import os
import shutil
import sys
import time

from playwright.sync_api import sync_playwright

SRC = "/home/pratyushn/.config/BraveSoftware/Brave-Browser/Default"
DST = "/tmp/opencode/whatsapp-profile/Default"
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)

# refresh the session cookies from the live profile
for f in ("Cookies", "Cookies-journal"):
    try:
        shutil.copy(os.path.join(SRC, f), os.path.join(DST, f))
    except OSError:
        pass

TARGET = sys.argv[1] if len(sys.argv) > 1 else \
    "https://github.com/Pratyush-bit69/mathematica"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        "/tmp/opencode/whatsapp-profile",
        executable_path="/usr/bin/brave",
        headless=False,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-brave-extension", "--no-first-run",
              "--no-default-browser-check"],
        viewport={"width": 1440, "height": 950},
        ignore_default_args=["--disable-extensions"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(TARGET, wait_until="domcontentloaded", timeout=90000)
    time.sleep(7)
    page.screenshot(path=f"{OUT}/gh-repo.png", full_page=False)
    print("url:", page.url)
    print("---- text ----")
    print(page.inner_text("body")[:2500])
    ctx.close()
