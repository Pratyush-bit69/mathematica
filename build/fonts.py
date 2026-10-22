#!/usr/bin/env python3
"""Download Google Fonts latin subsets and vendor them locally."""
import os
import re
import urllib.request

OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
CSS = os.path.join(OUT, "fonts.css")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
API = ("https://fonts.googleapis.com/css2?"
       "family=Newsreader:ital,opsz,wght@0,6..72,200..800;1,6..72,200..800"
       "&family=Inter:wght@300;400;500;600;700;800"
       "&family=JetBrains+Mono:wght@400;500;700"
       "&display=swap")

# keep only latin + latin-ext blocks
KEEP = ("latin", "latin-ext")


def get(url, ua=UA):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    os.makedirs(OUT, exist_ok=True)
    css = get(API).decode("utf-8")
    blocks = re.findall(r"/\*\s*([\w-]+)\s*\*/\s*(@font-face\s*\{.*?\})",
                         css, re.S)
    out = []
    seen = {}
    for name, block in blocks:
        if name not in KEEP:
            continue
        urls = re.findall(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", block)
        if not urls:
            continue
        local = block
        for u in urls:
            fname = u.rsplit("/", 1)[-1]
            path = os.path.join(OUT, fname)
            if not os.path.exists(path):
                with open(path, "wb") as fh:
                    fh.write(get(u))
            local = local.replace(u, fname)
        out.append(local.strip())
    with open(CSS, "w", encoding="utf-8") as fh:
        fh.write("/* Vendored Google Fonts (latin subsets) */\n")
        fh.write("\n".join(out) + "\n")
    n = len([f for f in os.listdir(OUT) if f.endswith(".woff2")])
    print(f"wrote {CSS} with {len(out)} faces, {n} font files")


if __name__ == "__main__":
    main()
