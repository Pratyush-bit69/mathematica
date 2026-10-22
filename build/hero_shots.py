#!/usr/bin/env python3
"""Capture a sequence of hero frames so the animation can be judged."""
import http.server
import socketserver
import threading
import os

from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)
PORT = 8755


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
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
    for i, wait in enumerate((2500, 4000, 4000)):
        pg.wait_for_timeout(wait)
        pg.screenshot(path=f"{OUT}/hero-{i}.png")
        print("hero", i)
    # measure frame rate
    fps = pg.evaluate("""() => new Promise(res => {
        let n = 0; const t0 = performance.now();
        (function tick(){ n++; if (performance.now() - t0 < 1500)
            requestAnimationFrame(tick); else res(Math.round(n / ((performance.now()-t0)/1000))); })();
    })""")
    print("fps ~", fps)
    print("errors:", errs[:3])
    b.close()
