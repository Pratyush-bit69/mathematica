#!/usr/bin/env python3
"""Close-up screenshots at real scale for design review."""
import http.server
import socketserver
import threading
import os
import sys

from playwright.sync_api import sync_playwright

ROOT = "/projects/personal_development"
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)
PORT = 8732


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, *a):
        pass


def serve():
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


SHOTS = [
    ("hero", "/index.html", 1440, 900, 0),
    ("volumes", "/index.html", 1440, 900, 1150),
    ("inside", "/index.html", 1440, 1000, 4950),
    ("reader-top", "/reader.html", 1440, 950, 0),
    ("reader-math", "/reader.html", 1440, 950, 1150),
    ("reader-deep", "/reader.html", 1440, 950, 2600),
    ("reader-probs", "/reader.html#ch11", 1440, 950, 5600),
    ("lab-plot", "/lab.html", 1440, 950, 260),
    ("lab-option", "/lab.html", 1440, 950, 260),
    ("glossary", "/glossary.html", 1440, 950, 320),
]


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    serve()
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        for name, path, w, h, y in SHOTS:
            if only and only != name:
                continue
            pg = b.new_page(viewport={"width": w, "height": h})
            pg.goto(f"http://127.0.0.1:{PORT}{path}", wait_until="networkidle")
            pg.wait_for_timeout(900)
            pg.evaluate(f"window.scrollTo(0,{y})")
            pg.wait_for_timeout(2600)
            pg.screenshot(path=f"{OUT}/d-{name}.png")
            print("shot", name)
            pg.close()
        b.close()


if __name__ == "__main__":
    main()
