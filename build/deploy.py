#!/usr/bin/env python3
"""Publish the MATHEMATICA site to a permanent netlify.app address."""
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

PROFILE = "/tmp/opencode/whatsapp-profile"
OUT = "/tmp/opencode/shots"
SITE = "/projects/personal_development"
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
    page.goto("https://app.netlify.com/drop", wait_until="domcontentloaded",
              timeout=90000)
    time.sleep(7)

    inputs = page.locator("input[type=file]")
    print("file inputs:", inputs.count())
    for i in range(inputs.count()):
        el = inputs.nth(i)
        try:
            print("  ", i, "multiple:", el.get_attribute("multiple"),
                  "webkitdir:", el.get_attribute("webkitdirectory"))
        except Exception:
            pass

    done = False
    for i in range(inputs.count()):
        el = inputs.nth(i)
        try:
            if el.get_attribute("webkitdirectory") is not None:
                el.set_input_files(SITE)
            else:
                el.set_input_files(os.path.join(SITE, "index.html"))
            done = True
            print("uploaded via input", i)
            break
        except Exception as e:
            print("  input", i, "failed:", str(e)[:140])
    if not done:
        print("NO USABLE FILE INPUT")
        page.screenshot(path=f"{OUT}/deploy-fail.png")
        ctx.close()
        sys.exit(2)

    # wait for the site to be assigned a url
    url = None
    for _ in range(60):
        time.sleep(3)
        body = ""
        try:
            body = page.inner_text("body")
        except Exception:
            continue
        m = re.search(r"https://[a-z0-9-]+\.netlify\.app", body)
        if m:
            url = m.group(0)
            break
        try:
            m2 = re.search(r"https://[a-z0-9-]+\.netlify\.app",
                           page.url)
            if m2:
                url = m2.group(0)
                break
        except Exception:
            pass
    page.screenshot(path=f"{OUT}/deploy-done.png", full_page=True)
    print("---- body ----")
    print(page.inner_text("body")[:1200])
    print("URL:", url)
    if url:
        open("/tmp/opencode/netlify-url.txt", "w").write(url)
    ctx.close()
    sys.exit(0 if url else 3)
