#!/usr/bin/env python3
"""Open WhatsApp Web in a copy of the Brave profile and report the state."""
import os
import sys
import time

from playwright.sync_api import sync_playwright

PROFILE = "/tmp/opencode/whatsapp-profile"
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)
URL = "https://web.whatsapp.com/"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PROFILE,
        executable_path="/usr/bin/brave",
        headless=False,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-brave-extension", "--no-first-run",
              "--no-default-browser-check",
              "--disable-features=Translate,BraveRewards"],
        viewport={"width": 1440, "height": 900},
        ignore_default_args=["--disable-extensions"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(6)
    for i in range(14):
        try:
            if page.locator("div[role='textbox'], textarea").count() > 0:
                break
        except Exception:
            pass
        time.sleep(3)
    time.sleep(3)
    page.screenshot(path=f"{OUT}/wa-recon.png")
    print("URL:", page.url)
    txt = page.inner_text("body")[:600]
    print("---- visible text ----")
    print(txt)
    print("---- markers ----")
    for sel, label in [
        ("canvas", "qr/canvas"),
        ("div[role='textbox']", "message box"),
        ("header", "header"),
        ("[aria-label='Search input textbox']", "search"),
        ("[data-testid='chat-list']", "chat list"),
    ]:
        try:
            print(label, "->", page.locator(sel).count())
        except Exception as e:
            print(label, "-> err")
    ctx.close()
