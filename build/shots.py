#!/usr/bin/env python3
"""Screenshot the site with Playwright and report console errors."""
import http.server
import socketserver
import threading
import os
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)

PORT = 8731


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, *a):
        pass


def serve():
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


PAGES = [
    ("index", "/index.html", 1440, 3400),
    ("reader", "/reader.html", 1440, 2400),
    ("lab", "/lab.html", 1440, 1700),
    ("glossary", "/glossary.html", 1440, 1800),
]


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    serve()
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage",
                                          "--force-color-profile=srgb"])
        for name, path, w, h in PAGES:
            if only and only != name:
                continue
            page = browser.new_page(viewport={"width": w, "height": 1000},
                                    device_scale_factor=1)
            page.on("console", lambda m: errors.append((name, m.type, m.text))
                    if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda e: errors.append((name, "pageerror", str(e))))
            page.on("requestfailed", lambda r: errors.append(
                (name, "404", r.url)))
            page.on("response", lambda r: errors.append(
                (name, "http" + str(r.status), r.url)) if r.status >= 400 else None)
            page.goto(f"http://127.0.0.1:{PORT}{path}", wait_until="networkidle")
            # scroll through so every reveal / lazy element renders
            height = page.evaluate("document.body.scrollHeight")
            y = 0
            while y < height:
                page.mouse.wheel(0, 700)
                y += 700
                page.wait_for_timeout(70)
            page.evaluate("window.scrollTo(0,0)")
            page.wait_for_timeout(1400)
            page.screenshot(path=f"{OUT}/{name}.png", full_page=True)
            print("shot", name, os.path.getsize(f"{OUT}/{name}.png"))
            page.close()
        browser.close()
    if errors:
        print("\n--- console issues ---")
        seen = set()
        for name, kind, text in errors:
            key = (name, kind, text[:120])
            if key in seen:
                continue
            seen.add(key)
            print(f"[{name}] {kind}: {text[:220]}")
    else:
        print("\nno console errors")


if __name__ == "__main__":
    main()
