#!/usr/bin/env python3
"""Send the tunnel link to the 'Temp' WhatsApp group via WhatsApp Web."""
import os
import sys
import time

from playwright.sync_api import sync_playwright

PROFILE = "/tmp/opencode/whatsapp-profile"
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)

TUNNEL = sys.argv[1] if len(sys.argv) > 1 else \
    "https://brass-would-cover-card.trycloudflare.com"
GROUP = sys.argv[2] if len(sys.argv) > 2 else "Temp"
MESSAGE = (
    "MATHEMATICA is live — the Unabridged Four-Volume Mathematical Treatise: "
    "22 chapters, 115 worked examples, 21 formal proofs and 720 solved "
    "problems, plus an interactive math lab and a searchable glossary.\n"
    + TUNNEL
)

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
    page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded",
              timeout=90000)

    # wait for the app shell
    for _ in range(30):
        if page.locator("[data-testid='chat-list'], #pane-side").count():
            break
        time.sleep(2)
    time.sleep(4)

    # --- open the group
    print("searching for group:", GROUP)
    try:
        page.fill("input[placeholder*='Search'], div[role='textbox']"
                  "[aria-label*='Search'], [data-testid='chat-search']"
                  "[role='textbox']", GROUP)
    except Exception as e:
        print("search box:", e)
    time.sleep(3)
    page.screenshot(path=f"{OUT}/wa-search.png")

    clicked = False
    for sel in [
        f"span[title='{GROUP}']",
        f"[data-testid='cell-frame']:has-text('{GROUP}')",
        f"div[role='gridcell']:has-text('{GROUP}')",
        f"span:text-is('{GROUP}')",
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click()
                clicked = True
                print("clicked via", sel)
                break
        except Exception:
            continue
    if not clicked:
        page.screenshot(path=f"{OUT}/wa-notfound.png")
        print("COULD NOT FIND GROUP")
        ctx.close()
        sys.exit(2)
    time.sleep(4)

    # --- find the composer
    box = None
    for sel in ["div[contenteditable='true'][data-tab='10']",
                "footer div[contenteditable='true']",
                "div[role='textbox'][contenteditable='true']",
                "div[contenteditable='true']"]:
        loc = page.locator(sel)
        if loc.count():
            box = loc.last
            print("composer:", sel)
            break
    if box is None:
        page.screenshot(path=f"{OUT}/wa-nobox.png")
        print("NO COMPOSER")
        ctx.close()
        sys.exit(3)

    time.sleep(1)
    box.click()
    time.sleep(0.6)
    page.keyboard.type(MESSAGE, delay=12)
    time.sleep(1.5)
    page.screenshot(path=f"{OUT}/wa-typed.png")

    page.keyboard.press("Enter")
    time.sleep(4)
    page.screenshot(path=f"{OUT}/wa-sent.png")

    # --- verify
    body = page.inner_text("body")
    ok = TUNNEL in body
    print("link visible in chat:", ok)
    print("tail:", body[-400:].replace("\n", " | ")[:400])
    ctx.close()
    sys.exit(0 if ok else 4)
