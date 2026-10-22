#!/usr/bin/env python3
"""Post the permanent GitHub Pages URL to the WhatsApp 'Temp' group and
remove the earlier tunnel-link message."""
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

PROFILE = "/tmp/opencode/whatsapp-profile"
OUT = "/tmp/opencode/shots"
GROUP = "Temp"
PERMANENT = "https://pratyush-bit69.github.io/mathematica/"
os.makedirs(OUT, exist_ok=True)

MESSAGE = (
    "MATHEMATICA is live — the Unabridged Four-Volume Mathematical Treatise: "
    "22 chapters, 115 worked examples, 21 formal proofs and 720 solved "
    "problems, plus an interactive math lab and a searchable glossary.\n"
    "Permanent address (GitHub Pages):\n" + PERMANENT
)

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

    for sel in [f"span[title='{GROUP}']", f"span:text-is('{GROUP}')",
                f"[data-testid='cell-frame']:has-text('{GROUP}')"]:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.click()
            print("opened", GROUP)
            break
    time.sleep(4)

    # --- remove any earlier tunnel-link message
    ids = page.evaluate("""() => {
      const out = [];
      document.querySelectorAll('div[data-id]').forEach(el => {
        const t = (el.innerText||'');
        if (t.includes('trycloudflare')) out.push(el.getAttribute('data-id'));
      });
      return out;
    }""")
    for mid in ids:
        bubble = page.locator(f"div[data-id='{mid}']")
        if not bubble.count():
            continue
        bubble.first.scroll_into_view_if_needed()
        time.sleep(0.6)
        bubble.first.hover()
        time.sleep(1.0)
        btns = bubble.first.locator("span[data-icon='menu'], [data-icon='menu'], "
                                    "button[role='button']")
        opened = False
        for i in range(min(btns.count(), 6)):
            try:
                btns.nth(i).click(timeout=3500)
                opened = True
                break
            except Exception:
                continue
        if not opened:
            box = bubble.first.bounding_box()
            if box:
                page.mouse.click(box["x"] + box["width"] - 18,
                                 box["y"] + box["height"] / 2)
        time.sleep(1.4)
        for label in ["Delete for everyone", "Delete message", "Delete", "Unsend"]:
            el = page.get_by_text(label, exact=False).first
            if el.count() and el.is_visible():
                el.click()
                break
        time.sleep(1.2)
        for label in ["Delete for everyone", "Delete", "Delete message"]:
            try:
                el = page.get_by_role("button", name=label).first
                if el.count() and el.is_visible():
                    el.click()
                    break
            except Exception:
                continue
        time.sleep(2.5)
        print("deleted stale message", mid)

    # --- send the permanent link
    box = page.locator("div[contenteditable='true'][data-tab='10']")
    if not box.count():
        box = page.locator("div[contenteditable='true']").last
    box.click()
    time.sleep(0.6)
    page.keyboard.type(MESSAGE, delay=8)
    time.sleep(1.2)
    page.keyboard.press("Enter")
    time.sleep(4)
    page.screenshot(path=f"{OUT}/wa-permanent.png")
    body = page.inner_text("body")
    print("permanent link present:", PERMANENT in body)
    print("any trycloudflare link still there:",
          "trycloudflare" in body)
    ctx.close()
