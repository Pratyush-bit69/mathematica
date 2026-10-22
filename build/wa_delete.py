#!/usr/bin/env python3
"""Delete a specific (stale) WhatsApp message by its data-id."""
import sys
import time

from playwright.sync_api import sync_playwright

PROFILE = "/tmp/opencode/whatsapp-profile"
OUT = "/tmp/opencode/shots"
GROUP = "Temp"
STALE = sys.argv[1] if len(sys.argv) > 1 else ""

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PROFILE,
        executable_path="/usr/bin/brave",
        headless=False,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-brave-extension", "--no-first-run"],
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
    loc = page.locator(f"span[title='{GROUP}']").first
    if loc.count():
        loc.click()
    time.sleep(4)

    bubble = page.locator(f"div[data-id='{STALE}']")
    if not bubble.count():
        print("stale bubble not found")
        ctx.close()
        sys.exit(2)
    bubble.first.scroll_into_view_if_needed()
    time.sleep(1)
    bubble.first.hover()
    time.sleep(1.2)
    # the per-message menu button appears on hover
    btns = bubble.first.locator("span[data-icon='menu'], [data-icon='menu'], "
                                "button[role='button']")
    print("menu candidates:", btns.count())
    clicked = False
    for i in range(min(btns.count(), 6)):
        try:
            btns.nth(i).click(timeout=4000)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        # fall back: click at the right-hand end of the bubble
        box = bubble.first.bounding_box()
        if box:
            page.mouse.click(box["x"] + box["width"] - 18,
                             box["y"] + box["height"] / 2)
            clicked = True
    time.sleep(1.5)
    page.screenshot(path=f"{OUT}/wa-menu.png")
    done = False
    for label in ["Delete for everyone", "Delete message", "Delete", "Unsend"]:
        el = page.get_by_text(label, exact=False).first
        if el.count() and el.is_visible():
            print("clicking", label)
            el.click()
            done = True
            break
    time.sleep(1.5)
    # confirmation dialog
    for label in ["Delete for everyone", "Delete", "Delete message"]:
        try:
            el = page.get_by_role("button", name=label).first
            if el.count() and el.is_visible():
                el.click()
                print("confirmed", label)
                done = True
                break
        except Exception:
            continue
    time.sleep(3)
    page.screenshot(path=f"{OUT}/wa-deleted.png")
    body = page.inner_text("body")
    print("stale still present:", STALE in body)
    print("a live tunnel link is present:",
          "trycloudflare.com" in body or
          "pratyush-bit69.github.io/mathematica" in body)
    ctx.close()
