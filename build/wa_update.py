#!/usr/bin/env python3
"""Replace the WhatsApp message in the Temp group with the live tunnel URL.

Deletes the previous (now stale) message if it is still recent, then posts the
current one.  The live address is read from the site's own /live-url endpoint
so it can never drift out of sync with the running tunnel.
"""
import os
import re
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

PROFILE = "/tmp/opencode/whatsapp-profile"
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)
GROUP = "Temp"
MESSAGE = (
    "MATHEMATICA is live — the Unabridged Four-Volume Mathematical Treatise: "
    "22 chapters, 115 worked examples, 21 formal proofs and 720 solved "
    "problems, plus an interactive math lab and a searchable glossary.\n"
)


def live_url():
    for url in ("http://127.0.0.1:8080/live-url",
                "http://127.0.0.1:8080/live-url.txt"):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                u = r.read().decode().strip()
                if u.startswith("http"):
                    return u
        except Exception:
            continue
    p = "/projects/personal_development/live-url.txt"
    if os.path.exists(p):
        return open(p).read().strip()
    return ""


URL = live_url()
if not URL:
    print("no live url found")
    sys.exit(1)
print("live url:", URL)

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
    page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded",
              timeout=90000)
    for _ in range(30):
        if page.locator("[data-testid='chat-list'], #pane-side").count():
            break
        time.sleep(2)
    time.sleep(4)

    # open the group
    for sel in [f"span[title='{GROUP}']",
                f"[data-testid='cell-frame']:has-text('{GROUP}')",
                f"span:text-is('{GROUP}')"]:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.click()
            print("opened", GROUP)
            break
    time.sleep(4)

    # delete a previous message of ours that contains a trycloudflare link
    stale = 0
    for sel in ["div[data-id^='false_']:has-text('trycloudflare')",
                "div[role='listitem']:has-text('trycloudflare')"]:
        loc = page.locator(sel)
        n = loc.count()
        if n:
            last = loc.nth(n - 1)
            try:
                last.hover()
                time.sleep(0.6)
                menu = last.locator("span[data-icon='menu'], "
                                    "[data-icon='menu'], button")
                if menu.count():
                    menu.first.click()
                    time.sleep(1.2)
                    for d in ["Delete for everyone", "Delete", "Unsend"]:
                        dloc = page.get_by_text(d, exact=False).first
                        if dloc.count() and dloc.is_visible():
                            dloc.click()
                            stale += 1
                            break
                    time.sleep(1)
                    try:
                        page.get_by_text("Delete", exact=True).last.click()
                    except Exception:
                        pass
                    time.sleep(1.5)
                    break
            except Exception as e:
                print("delete err:", str(e)[:120])
    print("stale messages deleted:", stale)
    time.sleep(1)

    # send the new message
    box = page.locator("div[contenteditable='true'][data-tab='10']")
    if not box.count():
        box = page.locator("div[contenteditable='true']").last
    box.click()
    time.sleep(0.6)
    page.keyboard.type(MESSAGE + URL, delay=10)
    time.sleep(1.2)
    page.keyboard.press("Enter")
    time.sleep(4)
    page.screenshot(path=f"{OUT}/wa-final.png")
    body = page.inner_text("body")
    print("link visible:", URL in body)
    ctx.close()
