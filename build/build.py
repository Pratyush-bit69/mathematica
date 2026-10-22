#!/usr/bin/env python3
"""Build assets/data/treatise.js from the source PDF."""
import json
import os
import re
import sys
from collections import Counter, defaultdict

from pdfxml import load
from docbuild import (page_words, build_lines, build_blocks, line_runs,
                      merge_text_runs, HEAD_RE, SEC_RE, VOL_RE, THEOREM_RE,
                      WORKED_RE, EX_RE, EXAM_RE, TIER_RE, PAGE_CENTER)
from extract import load_outline

PDF = "/home/pratyushn/Downloads/Unabridged_Mathematics_Treatise_Complete.pdf"
XML = "/tmp/opencode/mathpdf/doc.xml"
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "data",
                   "treatise.js")
WORK = "/tmp/opencode/mathpdf"


def ensure_inputs():
    """Regenerate the pdftohtml extracts if they are missing."""
    if os.path.exists(XML) and os.path.exists(os.path.join(WORK, "p13.html")):
        return
    os.makedirs(WORK, exist_ok=True)
    import subprocess
    print("extracting PDF geometry …", flush=True)
    subprocess.run(["pdftohtml", "-xml", "-noframes", "-i", "-hidden", "-q",
                    PDF, os.path.join(WORK, "doc")], check=True)
    subprocess.run(["pdftohtml", "-i", "-noframes", "-q", "-f", "13", "-l", "13",
                    PDF, os.path.join(WORK, "p13")], check=True)

HEADER_RE = re.compile(r"^MATHEMATICS:\s*FOUNDATIONAL ALGEBRA")
FOOTER_RE = re.compile(r"Unabridged Chapters")


def strip_chrome(items):
    keep = []
    for it in items:
        if it.top < 42:
            continue
        if it.top > 1120:
            continue
        if HEADER_RE.match(it.text.strip()):
            continue
        if FOOTER_RE.search(it.text):
            continue
        keep.append(it)
    return keep


VOL_RE = re.compile(r"^\s*VOLUME\s+(I{1,3}V?|IV)\b")
DIVIDER_RE = re.compile(r"^\s*CHAPTER\s+\d+\s*$")
CHAP_OUTLINE_RE = re.compile(r"^Chapter\s+(\d+)\s*:\s*(.*)$")


def parse_outline(outline):
    """Turn the flat PDF outline into {chapter: [section titles]}."""
    tree = {}
    part2 = []
    cur = None
    for t in outline:
        m = CHAP_OUTLINE_RE.match(t)
        if m:
            cur = int(m.group(1))
            tree[cur] = {"title": m.group(2).strip(), "sections": []}
            continue
        if t.startswith("Part II"):
            part2 = []
            continue
        if cur is not None:
            tree[cur]["sections"].append(t)
    return tree, part2


def main():
    ensure_inputs()
    pages, fonts = load(XML)
    outline = load_outline()
    otree, _ = parse_outline(outline)
    print("pages", len(pages), "outline", len(outline),
          "chapters in outline", len(otree))

    doc_blocks = []
    chapter_marks = []
    body_start = None
    for p in pages:
        items = strip_chrome(p.items)
        if not items:
            continue
        if body_start is None:
            if any(DIVIDER_RE.match(it.text.strip()) for it in items):
                body_start = p.num
            else:
                continue        # cover / preface / table of contents
        words = page_words(items)
        lines = build_lines(words)
        blocks = build_blocks(lines)
        doc_blocks.append((p.num, blocks))

    # ------------------------------------------------------------ assemble
    chapters = []
    cur = None
    front = []
    for pnum, blocks in doc_blocks:
        for b in blocks:
            if b["type"] == "chapter":
                cur = {
                    "num": b["num"], "title": b["title"], "page": pnum,
                    "intro": [], "sections": [],
                }
                chapters.append(cur)
                continue
            if cur is None:
                front.append({"type": "front", "page": pnum, "block": b})
                continue
            if b["type"] == "section":
                cur["sections"].append({"num": b["num"],
                                        "title": b["title"], "blocks": []})
                continue
            if cur["sections"]:
                cur["sections"][-1]["blocks"].append(b)
            else:
                cur["intro"].append(b)

    # volume dividers live in the front flow; attach volume info by chapter
    volumes = [
        {"id": 1, "roman": "I", "name": "Foundations of Pure & Linear Algebra",
         "chapters": [1, 2, 3, 4],
         "blurb": "Sets & Functions · Complex Numbers · Induction & "
                  "Combinatorics · Matrices & Determinants"},
        {"id": 2, "roman": "II", "name": "Analytic Geometry & Calculus",
         "chapters": [5, 6, 7],
         "blurb": "Lines, Circles & Conics · Limits & Derivatives · "
                  "Integrals, Areas & ODEs"},
        {"id": 3, "roman": "III", "name": "Trigonometry, Vectors & Probability",
         "chapters": [8, 9, 10],
         "blurb": "Trig & Inverse Trig · 3D Vectors & LPP · Statistics & "
                  "Bayes"},
        {"id": 4, "roman": "IV",
         "name": "Graduate AI, Machine Learning & Quantitative Finance",
         "chapters": list(range(11, 23)),
         "blurb": "Multivariable & Matrix Calculus · SVD & Spectral Theory · "
                  "Information Theory · Convex Optimisation · Itô Calculus & "
                  "Black-Scholes · PDEs & Monte Carlo · Transformers · RL · "
                  "Jumps, Heston & Yield Curves"},
    ]
    vol_of = {}
    for v in volumes:
        for c in v["chapters"]:
            vol_of[c] = v["id"]
    for c in chapters:
        c["volume"] = vol_of.get(c["num"], 4)
        info = otree.get(c["num"])
        if info:
            c["title"] = info["title"]
            secs = info["sections"]
            for i, s in enumerate(c["sections"]):
                if i < len(secs):
                    s["title"] = secs[i]
                s["title"] = re.sub(r"\s+", " ", s["title"]).strip()

    stats = {
        "chapters": len(chapters),
        "sections": sum(len(c["sections"]) for c in chapters),
        "theorems": sum(1 for _, bl in doc_blocks for b in bl
                        if b["type"] == "theorem"),
        "examples": sum(1 for _, bl in doc_blocks for b in bl
                        if b["type"] == "example"),
        "problems": sum(1 for _, bl in doc_blocks for b in bl
                        if b["type"] in ("problem", "exam")),
        "displays": sum(1 for _, bl in doc_blocks for b in bl
                        if b["type"] == "display"),
        "pages": len(pages),
    }

    out = {
        "meta": {
            "title": "Mathematics",
            "subtitle": "From Foundational Algebra, Analytic Geometry & Real "
                        "Calculus to Deep Learning, Stochastic Processes & "
                        "Quantitative Finance",
            "tagline": "A Self-Contained, Proof-Driven Reference and Solved "
                       "Problem Book",
            "stats": stats,
            "source": os.path.basename(PDF),
        },
        "outline": outline,
        "volumes": volumes,
        "chapters": chapters,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("window.TREATISE = ")
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")
    size = os.path.getsize(OUT)
    print("wrote", OUT, f"{size/1024:.0f} KB")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
