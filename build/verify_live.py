#!/usr/bin/env python3
"""Verify the deployed GitHub Pages site end to end."""
import http.server
import socketserver
import threading
import os
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else \
    "https://pratyush-bit69.github.io/mathematica"
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)
PORT = 8771

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name +
          ("" if cond else "  — " + str(detail)))
    if not cond:
        fails.append(name)


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory="/tmp")

    def log_message(self, *a):
        pass


socketserver.TCPServer.allow_reuse_address = True
httpd = socketserver.TCPServer(("127.0.0.1", PORT), H)
threading.Thread(target=httpd.serve_forever, daemon=True).start()

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    errs = []
    pg = b.new_page(viewport={"width": 1440, "height": 950})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

    pg.goto(BASE + "/", wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(2500)
    check("landing loads", "MATHEMATICA" in pg.title().upper(), pg.title())
    check("hero canvas painted", pg.evaluate(
        "() => { const c=document.getElementById('heroCanvas');"
        " const x=c.getContext('2d').getImageData(0,0,c.width,c.height).data;"
        " let n=0; for(let i=3;i<x.length;i+=4000) if(x[i]>0) n++;"
        " return n; }") > 20)
    check("stat strip", len(pg.query_selector_all("#statStrip .stat")) == 6)
    check("volume cards", len(pg.query_selector_all(".vol")) == 4)
    check("chapter cards", len(pg.query_selector_all(".ch-card")) == 22)
    check("katex on landing", len(pg.query_selector_all(".katex")) >= 4)
    pg.screenshot(path=f"{OUT}/gh-live-index.png", full_page=False)

    # reader
    pg.goto(BASE + "/reader.html", wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(2500)
    check("reader chapter", len(pg.query_selector_all(".ch-head h1")) == 1)
    check("reader katex", len(pg.query_selector_all(".katex")) > 40)
    check("reader toc", len(pg.query_selector_all(".toc a")) > 100)
    card = pg.query_selector(".tcard.prob")
    if card:
        card.query_selector(".tcard-head").click()
        pg.wait_for_timeout(500)
        body = card.query_selector(".tcard-body")
        check("problem expands with solution",
              body is not None and len(body.inner_text().strip()) > 60)
    pg.screenshot(path=f"{OUT}/gh-live-reader.png", full_page=False)

    # search
    pg.goto(BASE + "/", wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(1500)
    pg.keyboard.press("/")
    pg.wait_for_timeout(500)
    pg.fill("#searchInput", "Cayley-Hamilton")
    pg.wait_for_timeout(900)
    check("search finds results", len(pg.query_selector_all(".sr")) > 0)
    pg.fill("#searchInput", "Black-Scholes PDE")
    pg.wait_for_timeout(900)
    check("search finds finance results", len(pg.query_selector_all(".sr")) > 0)

    # lab
    pg.goto(BASE + "/lab.html", wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(2000)
    check("lab plotter", "f(x" in pg.inner_text("#pReadout"))
    pg.click('.tab[data-tab="option"]')
    pg.wait_for_timeout(900)
    check("lab option pane", pg.is_visible('.tabpane[data-pane="option"]'))

    # glossary
    pg.goto(BASE + "/glossary.html", wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(1200)
    check("glossary concepts", len(pg.query_selector_all("#gTerms .card")) > 50)

    pg.close()
    b.close()

print()
print("console errors:", errs[:5] if errs else "none")
print("ALL PASSED" if not fails and not errs else f"FAILURES: {fails}")
sys.exit(0 if not fails and not errs else 1)
