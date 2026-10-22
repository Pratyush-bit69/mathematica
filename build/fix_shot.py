#!/usr/bin/env python3
"""Screenshot the exact region the user reported (chapter 1 graded problems)."""
import http.server
import socketserver
import threading
import os

from playwright.sync_api import sync_playwright

ROOT = "/projects/personal_development"
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)
PORT = 8751


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def log_message(self, *a):
        pass


socketserver.TCPServer.allow_reuse_address = True
httpd = socketserver.TCPServer(("127.0.0.1", PORT), H)
threading.Thread(target=httpd.serve_forever, daemon=True).start()

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    pg = b.new_page(viewport={"width": 940, "height": 900})
    pg.goto(f"http://127.0.0.1:{PORT}/reader.html#ch1", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    # open the first graded problem card
    prob = pg.query_selector(".tcard.prob")
    if prob:
        prob.query_selector(".tcard-head").click()
        pg.wait_for_timeout(600)
        prob.scroll_into_view_if_needed()
        pg.wait_for_timeout(400)
    pg.screenshot(path=f"{OUT}/fix-problem.png")
    print("shot fix-problem")
    # and a worked example
    ex = pg.query_selector(".tcard.ex")
    if ex:
        ex.scroll_into_view_if_needed()
        pg.wait_for_timeout(400)
        ex.scroll_into_view_if_needed()
        pg.wait_for_timeout(300)
        pg.screenshot(path=f"{OUT}/fix-example.png")
        print("shot fix-example")
    b.close()
