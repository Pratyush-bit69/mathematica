#!/usr/bin/env python3
"""End-to-end smoke test for the MATHEMATICA site."""
import http.server
import socketserver
import threading
import os
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = "/tmp/opencode/shots"
os.makedirs(OUT, exist_ok=True)
PORT = 8745
SUPPORT_URL = "https://www.buymeachai.in/pratyush"
fails = []


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
httpd = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  — " + str(detail)))
    if not cond:
        fails.append(name)


def check_support(pg, label, minimum=1):
    links = pg.query_selector_all(f'a[href="{SUPPORT_URL}"]')
    check(f"{label}: support link present", len(links) >= minimum, len(links))
    safe = all((l.get_attribute("target") == "_blank" and
                l.get_attribute("rel") == "noopener noreferrer") for l in links)
    check(f"{label}: support link opens safely", bool(links) and safe)
    check(f"{label}: support band visible",
          pg.is_visible(".support-band"))


with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    errors = []

    # ------------------------------------------------------------ landing
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("pageerror", lambda e: errors.append(("index", str(e))))
    pg.on("console", lambda m: errors.append(("index", m.text))
          if m.type == "error" else None)
    pg.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    check("landing: hero title", "MATHEMATICA" in pg.title(), pg.title())
    check("landing: stats rendered",
          len(pg.query_selector_all("#statStrip .stat")) == 6)
    check("landing: volume cards", len(pg.query_selector_all(".vol")) == 4)
    check("landing: chapter cards", len(pg.query_selector_all(".ch-card")) == 22)
    check("landing: feature cards", len(pg.query_selector_all(".feat")) >= 6)
    check_support(pg, "landing", 2)
    check("landing: hero support link", pg.is_visible(".hero-support"))
    check("landing: accurate solution wording",
          "720 worked solutions" in pg.inner_text("body") and
          "720 fully solved problems" not in pg.inner_text("body"))
    check("landing: no fake footer links",
          len(pg.query_selector_all('.foot-grid a[href="#"]')) == 0)
    check("landing: colophon rendered",
          len(pg.query_selector_all(".foot-note")) >= 3)
    internal = set(pg.eval_on_selector_all(
        'a[href$=".html"]', "els => els.map(e => e.getAttribute('href'))"))
    broken = [h for h in sorted(internal)
              if not pg.request.get(
                  f"http://127.0.0.1:{PORT}/{h.lstrip('/')}").ok]
    check("landing: every internal page link resolves", not broken, broken)
    check("landing: math rendered",
          len(pg.query_selector_all(".fmath .katex")) >= 4)
    # filter by volume
    pg.click('.chip[data-vol="4"]')
    pg.wait_for_timeout(400)
    check("landing: volume filter", len(pg.query_selector_all(".ch-card")) == 12)
    # theme toggle
    pg.click("[data-theme-toggle]")
    pg.wait_for_timeout(300)
    check("landing: theme toggle",
          pg.get_attribute("html", "data-theme") == "light")
    pg.click("[data-theme-toggle]")
    pg.wait_for_timeout(200)

    # ------------------------------------------------------------- search
    pg.keyboard.press("/")
    pg.wait_for_timeout(400)
    check("search: modal opens", pg.is_visible("#searchModal"))
    pg.fill("#searchInput", "Cayley-Hamilton")
    pg.wait_for_timeout(700)
    n = len(pg.query_selector_all(".sr"))
    check("search: results for Cayley-Hamilton", n > 0, n)
    pg.fill("#searchInput", "Black-Scholes PDE")
    pg.wait_for_timeout(700)
    check("search: results for Black-Scholes PDE",
          len(pg.query_selector_all(".sr")) > 0)
    pg.fill("#searchInput", "engineering students")
    pg.wait_for_timeout(500)
    check("search: result labelled by card",
          "worked example" in pg.inner_text("#searchResults .sr-kind").lower(),
          pg.inner_text("#searchResults .sr-kind"))
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    check("search: closes on escape", not pg.is_visible("#searchModal"))

    # ------------------------------------------------------------- reader
    pg.goto(f"http://127.0.0.1:{PORT}/reader.html", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    check("reader: chapter heading", len(pg.query_selector_all(".ch-head h1")) == 1)
    check_support(pg, "reader", 1)
    check("reader: treatise has 89 sections",
          pg.evaluate("window.TREATISE.meta.stats.sections") == 89)
    check("reader: 720 worked solutions",
          pg.evaluate("window.TREATISE.meta.stats.examples + window.TREATISE.meta.stats.problems") == 720)
    check("reader: toc entries", len(pg.query_selector_all(".toc a")) > 100)
    check("reader: katex spans", len(pg.query_selector_all(".katex")) > 30)
    check("reader: section headings", len(pg.query_selector_all(".sec-head")) >= 4)
    check("reader: theorem card", len(pg.query_selector_all(".tcard.theorem")) >= 1)
    # deep link
    pg.goto(f"http://127.0.0.1:{PORT}/reader.html#ch17", wait_until="networkidle")
    pg.wait_for_timeout(1400)
    check("reader: deep link to chapter 17",
          "17" in pg.inner_text(".ch-head h1") or
          "Stochastic" in pg.inner_text(".ch-head h1"))
    # Part II of the PDF is a video-link table, not treatise content.
    pg.goto(f"http://127.0.0.1:{PORT}/reader.html#ch22", wait_until="networkidle")
    pg.wait_for_timeout(1400)
    heads = pg.eval_on_selector_all(
        ".sec-head h2", "els => els.map(e => e.textContent.trim())")
    check("reader: chapter 22 has exactly two sections", len(heads) == 2, heads)
    check("reader: chapter 22 section numbers",
          all(h.startswith(p) for h, p in zip(heads, ["22.1", "22.2"])), heads)
    check("reader: chapter 22 part B is 20 problems",
          "20 Advanced" in heads[1] and "22.30" in heads[1], heads)
    # next / prev
    pg.goto(f"http://127.0.0.1:{PORT}/reader.html#ch17", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    pg.click("#nextCh")
    pg.wait_for_timeout(900)
    check("reader: next chapter", "18" in pg.inner_text(".ch-head .vol-pill"))
    # collapsible card: the statement is always visible, only the solution folds
    card = pg.query_selector(".tcard")
    if card:
        statement = card.query_selector(".tcard-statement")
        check("reader: statement always visible",
              statement is not None and len(statement.inner_text().strip()) > 20)
        toggle = card.query_selector(".tcard-toggle")
        check("reader: card has solution control", toggle is not None)
        if toggle:
            toggle.click()
            pg.wait_for_timeout(300)
            check("reader: card toggles", "open" in (card.get_attribute("class") or ""))
            solution = card.query_selector(".tcard-solution")
            check("reader: solution visible after toggle",
                  solution is not None and solution.is_visible())
            toggle.click()
            pg.wait_for_timeout(200)
            check("reader: card collapses",
                  "open" not in (card.get_attribute("class") or ""))
    # a graded problem expands to reveal its solution
    pg.goto(f"http://127.0.0.1:{PORT}/reader.html#ch11", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    prob = pg.query_selector(".tcard.prob")
    if prob:
        check("reader: problems start collapsed",
              "open" not in (prob.get_attribute("class") or ""))
        prob.query_selector(".tcard-toggle").click()
        pg.wait_for_timeout(400)
        body = prob.query_selector(".tcard-solution")
        check("reader: problem reveals solution",
              body is not None and body.is_visible() and len(body.inner_text().strip()) > 40)
    pg.click("#toggleAll")
    pg.wait_for_timeout(500)
    open_count = len(pg.query_selector_all(".tcard.open"))
    check("reader: expand all", open_count > 5, open_count)
    # rail + progress
    check("reader: rail items", len(pg.query_selector_all("#railList a")) >= 3)
    # mark read
    pg.click("#markRead")
    pg.wait_for_timeout(200)
    check("reader: mark read", "✓" in pg.inner_text("#markRead"))

    # --------------------------------------------------------------- lab
    pg.goto(f"http://127.0.0.1:{PORT}/lab.html", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    check("lab: plotter canvas", pg.query_selector("#pCanvas") is not None)
    check("lab: readout populated",
          "f(x" in pg.inner_text("#pReadout"))
    check_support(pg, "lab", 1)
    pg.click(".search-trigger")
    pg.wait_for_timeout(300)
    check("lab: search modal opens", pg.is_visible("#searchModal"))
    pg.fill("#searchInput", "Cayley-Hamilton")
    pg.wait_for_timeout(700)
    check("lab: search returns results",
          len(pg.query_selector_all("#searchResults .sr")) > 0)
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    check("lab: search closes on escape", not pg.is_visible("#searchModal"))
    for t in ["riemann", "descent", "option", "prob", "linalg"]:
        pg.click(f'.tab[data-tab="{t}"]')
        pg.wait_for_timeout(700)
        check(f"lab: {t} pane visible",
              pg.is_visible(f'.tabpane[data-pane="{t}"]'))
    # interactive: change the function
    pg.click('.tab[data-tab="plot"]')
    pg.wait_for_timeout(500)
    pg.fill("#pFn", "x^2 - 4")
    pg.wait_for_timeout(700)
    check("lab: expression parser",
          "2 · x" in pg.inner_text("#pReadout") or "2x" in pg.inner_text("#pReadout"),
          pg.inner_text("#pReadout")[:80])

    # ----------------------------------------------------------- glossary
    pg.goto(f"http://127.0.0.1:{PORT}/glossary.html", wait_until="networkidle")
    pg.wait_for_timeout(900)
    check_support(pg, "glossary", 1)
    check("glossary: concepts", len(pg.query_selector_all("#gTerms .card")) > 50)
    pg.click('.chip[data-mode="formulas"]')
    pg.wait_for_timeout(500)
    check("glossary: formulas", len(pg.query_selector_all("#gFormulas .katex")) > 20)
    pg.click('.chip[data-mode="theorems"]')
    pg.wait_for_timeout(500)
    check("glossary: theorem index", len(pg.query_selector_all("#gTheorems .card")) == 21)
    pg.click('.chip[data-mode="terms"]')
    pg.wait_for_timeout(300)
    before_filter = len(pg.query_selector_all("#gTerms .card"))
    pg.fill("#gSearch", "Black")
    pg.wait_for_timeout(500)
    after_filter = len(pg.query_selector_all("#gTerms .card"))
    check("glossary: filter", 0 < after_filter < before_filter,
          f"{after_filter} of {before_filter}")

    # --------------------------------------------------- mobile reading tools
    mobile = b.new_page(viewport={"width": 390, "height": 844})
    mobile.on("pageerror", lambda e: errors.append(("mobile", str(e))))
    mobile.goto(f"http://127.0.0.1:{PORT}/reader.html#ch1", wait_until="networkidle")
    mobile.wait_for_timeout(900)
    check("mobile: no horizontal overflow",
          mobile.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") == 0)
    check("mobile: statements visible while collapsed",
          mobile.evaluate("""() => [...document.querySelectorAll('.tcard-statement')]
              .every(el => el.getBoundingClientRect().height > 0)"""))
    check("mobile: toc hidden initially",
          mobile.get_attribute("#toc", "aria-hidden") == "true")
    mobile.click("#tocToggle")
    mobile.wait_for_timeout(300)
    check("mobile: toc opens", mobile.get_attribute("#toc", "aria-hidden") == "false")
    check("mobile: expand-all available in toc", mobile.is_visible("#tocExpand"))
    mobile.click("#tocExpand")
    mobile.wait_for_timeout(400)
    check("mobile: expand all from toc",
          len(mobile.query_selector_all(".tcard.open")) > 5,
          len(mobile.query_selector_all(".tcard.open")))
    mobile.keyboard.press("Escape")
    mobile.wait_for_timeout(250)
    check("mobile: toc closes on escape",
          mobile.get_attribute("#toc", "aria-hidden") == "true")
    for path in ["index", "lab", "glossary"]:
        mobile.goto(f"http://127.0.0.1:{PORT}/{path}.html", wait_until="networkidle")
        mobile.wait_for_timeout(700)
        check(f"mobile: {path} has no horizontal overflow",
              mobile.evaluate("document.documentElement.scrollWidth - "
                              "document.documentElement.clientWidth") == 0)
    mobile.close()

    # ----------------------------------------------------------- print view
    pg.goto(f"http://127.0.0.1:{PORT}/reader.html#ch1", wait_until="networkidle")
    pg.wait_for_timeout(700)
    pg.emulate_media(media="print")
    pg.wait_for_timeout(250)
    check("print: white paper", pg.evaluate(
        "getComputedStyle(document.body).backgroundColor") == "rgb(255, 255, 255)")
    check("print: dark ink", pg.evaluate(
        "getComputedStyle(document.body).color") == "rgb(17, 17, 17)")
    check("print: chrome hidden", pg.evaluate(
        "getComputedStyle(document.querySelector('.nav')).display") == "none")
    check("print: support band hidden", pg.evaluate(
        "getComputedStyle(document.querySelector('.support-band')).display") == "none")
    check("print: solutions expanded", pg.evaluate(
        "getComputedStyle(document.querySelector('.tcard-solution')).display") == "block")
    pg.emulate_media(media="screen")

    pg.close()
    b.close()

print()
if errors:
    print("console/page errors:")
    for e in errors[:20]:
        print("   ", e)
else:
    print("no console errors")

print()
print(("ALL CHECKS PASSED" if not fails and not errors
       else f"{len(fails)} FAILURES: {fails}"))
sys.exit(1 if (fails or errors) else 0)
