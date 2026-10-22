#!/usr/bin/env python3
"""Screenshot every lab tab and the light theme."""
import http.server
import socketserver
import threading
import os

from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)
PORT = 8733


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, *a):
        pass


socketserver.TCPServer.allow_reuse_address = True
httpd = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()

TABS = ["plot", "riemann", "descent", "option", "prob", "linalg"]

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.goto(f"http://127.0.0.1:{PORT}/lab.html", wait_until="networkidle")
    pg.wait_for_timeout(800)
    for t in TABS:
        pg.click(f'.tab[data-tab="{t}"]')
        pg.wait_for_timeout(1100)
        pg.screenshot(path=f"{OUT}/t-{t}.png")
        print("tab", t)
    # light theme check on the reader
    pg2 = b.new_page(viewport={"width": 1440, "height": 900})
    pg2.goto(f"http://127.0.0.1:{PORT}/reader.html", wait_until="networkidle")
    pg2.evaluate("localStorage.setItem('mathematica:theme','light')")
    pg2.reload(wait_until="networkidle")
    pg2.wait_for_timeout(1200)
    pg2.evaluate("window.scrollTo(0,1150)")
    pg2.wait_for_timeout(900)
    pg2.screenshot(path=f"{OUT}/d-light.png")
    print("light reader")
    b.close()
