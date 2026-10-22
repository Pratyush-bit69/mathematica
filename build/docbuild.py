"""Assemble the reconstructed treatise into a structured JSON document."""
import json
import re
import sys
from collections import Counter, defaultdict

from pdfxml import load
from extract import (MW, build_math, classify, group_rows, contiguous_groups,
                     split_words, load_outline, gspan, find_script_fractions)
import mathast as MA
from mathast import Run, Sym, Text, Script, Frac, Sqrt, BigOp, Matrix

TEXT_LEFT = 65.0
TEXT_RIGHT = 853.0
PAGE_CENTER = 459.0

HEAD_RE = re.compile(r"^\s*(\d+)\s+Chapter\s+(\d+)\s*:\s*(.*)$")
SEC_RE = re.compile(r"^\s*(\d{1,2}\.\d{1,2})\s{1,3}(\S.*)$")
THEOREM_RE = re.compile(r"^\s*Theorem\s+(\d+\.\d+)\s*:\s*(.*)$")
WORKED_RE = re.compile(r"^\s*Worked Example\s+(\d+\.\d+)\s*\(([^)]*)\)")
EX_RE = re.compile(r"^\s*(?:Ex|Prob)\s+(\d+\.\d+)\s*\(([^)]*)\)")
EXAM_RE = re.compile(r"^\s*Exam\s+(\d+\.\d+)\s*\(([^)]*)\)")
TIER_RE = re.compile(r"^\s*Tier\s+\d+\s*:")
VOL_RE = re.compile(r"^\s*VOLUME\s+(I{1,3}V?|IV)\b")
PART_RE = re.compile(r"^\s*Part\s+([IVX]+)\s*:")

# run-in labels that head a line of a worked example / proof
LABEL_RES = [
    ("question", re.compile(r"^Problem\s*:")),
    ("solution", re.compile(r"^(?:\d\.\s*)?(?:Detailed\s+)?Step-by-Step\s+Solution\s*:")),
    ("solution", re.compile(r"^(?:\d\.\s*)?Complete\s+Step-by-Step\s+Derivation\s*:")),
    ("solution", re.compile(r"^(?:\d\.\s*)?First-Principles\s+Strategy\s*(?:&|and)\s*Structural\s+Setup\s*:")),
    ("proof", re.compile(r"^Proof\s*:")),
    ("verify", re.compile(r"^(?:\d\.\s*)?Verification\s*&\s*Structural\s+Takeaway\s*:")),
    ("verify", re.compile(r"^(?:\d\.\s*)?Verification\s*and\s*Structural\s+Takeaway\s*:")),
    ("solution", re.compile(r"^Step\s+\d+\s*[^:]{0,70}:")),
    ("solution", re.compile(r"^Step\s+\d+\s*:")),
]
PROOF_OF_RE = re.compile(r"^\s*Proof of\s+(.*)$")

MATHLIKE = set("0123456789.,+-−=<>()[]{}:;'\"!/| ")


# ------------------------------------------------------------------ words

def page_words(items):
    """Turn positioned items into classified words."""
    words = []
    for it in items:
        if not it.text.strip():
            # extensible delimiter pieces (big brackets / braces) have no text
            if it.family == "CMEX10" and it.width > 4:
                words.append(MW("", it.left, it.right, it.size, "math",
                                "CMEX10", it.top, False, False))
            continue
        for (t, l, r, src, sp) in split_words(it):
            if not t:
                continue
            role = classify(t, src)
            words.append(MW(t, l, r, src.size, role, src.family, src.top,
                            src.bold, sp))
    return absorb(words)


ABSORB_CHARS = set("0123456789.,;:+\-−=<>()[]{}/*!|' ")


def absorb(words):
    """Pull base-sized digits/punctuation next to math into the math span."""
    mathish = [w for w in words if w.role == "math"]
    if not mathish:
        return words
    for w in words:
        if w.role != "text":
            continue
        t = w.t.strip()
        if not t:
            continue
        math_like = all(c in ABSORB_CHARS for c in t) or (
            len(t) == 1 and t.isalpha())
        if not math_like:
            continue
        for m in mathish:
            if m.l >= w.r:
                gap = m.l - w.r
            elif w.l >= m.r:
                gap = w.l - m.r
            else:
                gap = -0.5          # overlapping glyph (e.g. a slash over ∈)
            if gap <= 2.6:
                w.role = "math"
                break
    return words


# ------------------------------------------------------------------ lines

def build_lines(words):
    """Group words into visual lines (script words are attached to a line)."""
    base = [w for w in words if w.role != "script"]
    scripts = [w for w in words if w.role == "script"]
    lines = []
    for w in sorted(base, key=lambda w: (w.top, w.l)):
        placed = False
        for ln in lines:
            if abs(ln["top"] - w.top) <= 3.6:
                ln["top"] = (ln["top"] * ln["n"] + w.top) / (ln["n"] + 1)
                ln["ws"].append(w)
                ln["n"] += 1
                placed = True
                break
        if not placed:
            lines.append({"top": w.top, "ws": [w], "n": 1, "scripts": []})
    for ln in lines:
        ln["ws"].sort(key=lambda w: w.l)
    lines.sort(key=lambda l: l["top"])

    # attach script words to the line that owns their base
    for sw in scripts:
        best = None
        for ln in lines:
            if abs(ln["top"] - sw.top) > 16:
                continue          # a script belongs to a vertically near line
            has = None
            for w in ln["ws"]:
                if w.r <= sw.l + 2.0:
                    has = "left"
                elif has == "left":
                    has = "both"
            if has == "both":
                best = (0.0, ln)      # a line that brackets the script
                break
        if best is None:
            for ln in lines:
                if abs(ln["top"] - sw.top) > 16:
                    continue
                for w in ln["ws"]:
                    if w.r <= sw.l + 2.0 and w.r >= sw.l - 30:
                        d = abs(w.r - sw.l)
                        if best is None or d < best[0]:
                            best = (d, ln)
        if best is None:
            cands = [l for l in lines if abs(l["top"] - sw.top) <= 16]
            best = (1e9, min(cands, key=lambda l: abs(l["top"] - sw.top))) \
                if cands else None
        if best is not None:
            best[1]["scripts"].append(sw)
    for ln in lines:
        ln["scripts"].sort(key=lambda w: w.l)
    return lines


def line_runs(line, words=None):
    """Split a line into alternating text / math runs."""
    ws = words if words is not None else line["ws"]
    scripts = line.get("scripts", [])

    # A fraction's numerator and denominator live on different rows; group
    # them into a single unit so they stay inside one math run.
    pairs = find_script_fractions(scripts, ws)
    in_frac = set()
    units = []
    for num, den, lo, hi in pairs:
        for w in num + den:
            in_frac.add(id(w))
        units.append({"x": lo, "kind": "frac", "ws": num + den})
    for w in scripts:
        if id(w) in in_frac:
            continue
        units.append({"x": w.l, "kind": "script", "ws": [w]})
    for w in ws:
        units.append({"x": w.l, "kind": "base", "ws": [w]})
    units.sort(key=lambda u: u["x"])

    runs = []
    cur = None
    for u in units:
        if u["kind"] == "script":
            continue
        w = u["ws"][0]
        kind = "math" if (u["kind"] == "frac" or w.role == "math") else "text"
        if cur is None or cur["k"] != kind:
            cur = {"k": kind, "ws": []}
            runs.append(cur)
        cur["ws"].extend(u["ws"])
    # attach the remaining scripts to the run holding their base
    for sw in scripts:
        if id(sw) in in_frac:
            continue
        target = None
        for r in runs:
            if r["k"] != "math":
                continue
            for w in r["ws"]:
                if w.r <= sw.l + 2.0 and w.r >= sw.l - 30:
                    d = abs(w.r - sw.l)
                    if target is None or d < target[0]:
                        target = (d, r)
        if target is not None:
            target[1]["ws"].append(sw)
    out = []
    prev_word = None
    # a text fragment wedged between two maths inside a formula belongs to it
    total = sum(len(r["ws"]) for r in runs)
    nmath = sum(len(r["ws"]) for r in runs if r["k"] == "math")
    mathy = total > 0 and nmath / total >= 0.55
    for ri, r in enumerate(runs):
        if r["k"] == "text" and mathy and ri > 0 and ri < len(runs) - 1 \
                and runs[ri - 1]["k"] == "math" and runs[ri + 1]["k"] == "math":
            r = {"k": "math", "ws": r["ws"], "texty": True}
        need_space = False
        if r["ws"]:
            w0 = r["ws"][0]
            if prev_word is not None and (w0.sp or (w0.l - prev_word.r) > 2.4):
                need_space = True
        if r["k"] == "text":
            s = []
            for i, w in enumerate(r["ws"]):
                if i:
                    prev = r["ws"][i - 1]
                    if w.sp or (w.l - prev.r) > 2.4:
                        s.append(" ")
                s.append(w.t)
            txt = "".join(s)
            if txt.strip():
                if need_space:
                    txt = " " + txt
                out.append({"k": "text", "v": txt,
                            "b": any(w.bold for w in r["ws"])})
        else:
            ws2 = sorted(r["ws"], key=lambda w: (w.top, w.l))
            node = build_math(ws2)
            latex = node.latex()
            html = node.html()
            if need_space:
                if out and out[-1]["k"] == "text":
                    out[-1]["v"] = out[-1]["v"] + " "
                else:
                    latex = "\\ " + latex
                    html = '<span class="mspace"></span>' + html
            out.append({"k": "math", "latex": latex, "html": html})
        if r["ws"]:
            prev_word = r["ws"][-1]
    # tidy: collapse double spaces and strip the very first
    for i, o in enumerate(out):
        if o["k"] == "text":
            o["v"] = re.sub(r"  +", " ", o["v"])
            if i == 0:
                o["v"] = o["v"].lstrip()
    return out


def merge_text_runs(runs, dehyphenate=False):
    out = []
    for r in runs:
        if r["k"] == "text" and out and out[-1]["k"] == "text":
            prev = out[-1]["v"]
            if dehyphenate and prev.endswith("-") and r["v"][:1].islower():
                out[-1]["v"] = prev[:-1] + r["v"]
            else:
                out[-1]["v"] = prev + " " + r["v"]
            out[-1]["b"] = out[-1]["b"] and r["b"]
        else:
            out.append(dict(r))
    return out


# ----------------------------------------------------------------- blocks

def line_is_display(line, runs):
    """A centred, mostly-mathematical line is a display equation."""
    ws = line["ws"]
    if not ws:
        return False
    mathchars = sum(1 for w in ws if w.role == "math")
    if mathchars < max(2, len(ws) * 0.5):
        return False
    lo = min(w.l for w in ws)
    hi = max(w.r for w in ws)
    c = (lo + hi) / 2.0
    return abs(c - PAGE_CENTER) < 28 and (hi - lo) < 700


def _all_math(b):
    runs = b.get("runs") or []
    return bool(runs) and all(r["k"] == "math" for r in runs)


def _has_eq(b):
    return any("=" in (r.get("latex") or "") for r in b.get("runs") or [])


def merge_aligned(blocks):
    """Group consecutive all-math lines into one aligned display equation."""
    out = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b["type"] == "para" and _all_math(b) and _has_eq(b):
            group = [b]
            j = i + 1
            while j < len(blocks):
                nxt = blocks[j]
                if nxt["type"] == "para" and _all_math(nxt) and _has_eq(nxt):
                    group.append(nxt); j += 1
                elif nxt["type"] == "display" and _all_math(nxt):
                    group.append(nxt); j += 1
                else:
                    break
            runs = []
            for k, g in enumerate(group):
                if k:
                    runs.append({"k": "br"})
                runs.extend(g["runs"])
            out.append({"type": "display", "runs": runs})
            i = j
            continue
        out.append(b)
        i += 1
    return out


def build_blocks(lines):
    """Turn lines into semantic blocks."""
    blocks = []
    pending = None       # accumulating paragraph
    skip = set()

    def flush():
        """Emit any paragraph still being accumulated."""
        nonlocal pending
        if pending is not None:
            blocks.append(pending)
            pending = None

    for li, ln in enumerate(lines):
        if li in skip:
            continue
        ws = ln["ws"]
        if not ws:
            continue
        runs = merge_text_runs(line_runs(ln))
        if not runs:
            continue
        alltext = " ".join(w.t for w in ws).strip()
        # headings may contain scripts — merge them back in by x position
        merged = sorted(list(ws) + list(ln.get("scripts", [])), key=lambda w: w.l)
        headtext = " ".join(w.t for w in merged).strip()
        first = ws[0]

        # ---- headings -------------------------------------------------
        if first.bold and HEAD_RE.match(alltext) and len(alltext) > 12:
            m = HEAD_RE.match(alltext)
            blocks.append({"type": "chapter", "num": int(m.group(2)),
                           "title": m.group(3).strip()})
            flush()
            continue
        if first.bold:
            m = SEC_RE.match(alltext)
            if m and len(m.group(2)) > 4:
                num = m.group(1)
                if int(num.split(".")[0]) <= 22:
                    blocks.append({"type": "section", "num": num,
                                   "title": m.group(2).strip()})
                    flush()
                    continue

        # ---- theorem / example / problem -------------------------------
        head = _match_head(alltext)
        if head:
            kind, num, title, cut, tstart, tend, balanced = head
            # base words that make up the title
            text, spans = _word_spans(ws)
            tw = [w for w, (a, b) in zip(ws, spans) if a >= tstart and b <= tend]
            scripts = ln.get("scripts", [])
            if tw and scripts:
                lo = min(w.l for w in tw) - 2
                hi = max(w.r for w in tw) + 2
                extra = [s for s in scripts if lo <= s.l <= hi]
                if extra:
                    title = " ".join(w.t for w in
                                     sorted(tw + extra, key=lambda w: w.l))
            consumed = _words_upto(ws, cut)
            rest = line_runs(ln, ws[consumed:])
            if not balanced:
                # the heading wraps: pull the continuation from later lines
                acc = title
                for lj in range(li + 1, min(li + 4, len(lines))):
                    if lj in skip:
                        continue
                    nxt = " ".join(w.t for w in lines[lj]["ws"]).strip()
                    if not nxt:
                        continue
                    acc += " " + nxt
                    skip.add(lj)
                    if ")" in nxt:
                        break
                m2 = re.search(r"\)\s*[:.]?\s*$", acc)
                if m2:
                    acc = acc[:m2.start()].strip()
                title = acc.strip(" :")
            flush()
            pending = {"type": kind, "num": num, "title": title,
                       "runs": rest, "open": kind in ("theorem", "example"),
                       "indent": first.l, "last": ln["top"]}
        else:
            if first.bold:
                m = SEC_RE.match(alltext)
                if m and len(m.group(2)) > 4:
                    num = m.group(1)
                    if int(num.split(".")[0]) <= 22:
                        blocks.append({"type": "section", "num": num,
                                       "title": m.group(2).strip()})
                        flush()
                        continue
            if TIER_RE.match(alltext):
                blocks.append({"type": "tier", "title": alltext})
                flush()
                continue

            # ---- run-in labels ----------------------------------------
            lab = None
            for kind, rx in LABEL_RES:
                m = rx.match(alltext)
                if m:
                    lab = (kind, rx, m)
                    break
            if lab:
                kind, rx, m = lab
                consumed = _words_upto(ws, m.end())
                rest = line_runs(ln, ws[consumed:])
                flush()
                pending = {"type": kind,
                           "label": m.group(0).rstrip(":").strip(),
                           "runs": rest, "indent": first.l, "last": ln["top"]}
                continue
            if PROOF_OF_RE.match(alltext) and first.bold:
                title = PROOF_OF_RE.match(alltext).group(1)
                title = re.split(r"[:;]", title)[0].strip()
                if len(title) > 90:
                    title = title[:87].rstrip() + "…"
                blocks.append({"type": "proof", "title": title,
                               "runs": runs})
                flush()
                continue

            # ---- display equation -------------------------------------
            if line_is_display(ln, runs):
                flush()
                blocks.append({"type": "display", "runs": runs})
                continue

            # ---- bullets ------------------------------------------------
            if first.t.strip() == "•":
                rest = _strip_prefix(runs, "•")
                blocks.append({"type": "bullet", "runs": rest,
                               "marker": "•"})
                flush()
                continue

            # ---- ordinary paragraph line --------------------------------
            # LaTeX uses a hanging indent: a paragraph's first line sits
            # further left than its continuations, so a shallower indent
            # always starts a new paragraph.
            indent = first.l
            numbered = bool(re.match(r"^\d{1,2}\.\s", first.t))
            if pending is not None and not numbered and \
                    indent >= pending["indent"] - 6:
                pending["runs"] = merge_text_runs(pending["runs"] + runs,
                                                  dehyphenate=True)
                pending["last"] = ln["top"]
                continue
            if pending is not None:
                flush()
            pending = {"type": "para", "runs": runs, "indent": indent,
                       "last": ln["top"]}
    flush()
    blocks = merge_aligned(blocks)
    # drop empty paragraphs
    blocks = [b for b in blocks
              if b["type"] != "para" or
              any((r.get("v") or r.get("latex") or "").strip()
                  for r in b.get("runs") or [])]
    return blocks


HEAD_KINDS = [
    ("theorem", re.compile(r"^\s*Theorem\s+(\d+\.\d+)\s*:"), False),
    ("example", re.compile(r"^\s*Worked Example\s+(\d+\.\d+)\s*\("), True),
    ("problem", re.compile(r"^\s*(?:Ex|Prob)\s+(\d+\.\d+)\s*\("), True),
    ("exam", re.compile(r"^\s*Exam\s+(\d+\.\d+)\s*\("), True),
]


def _match_head(alltext):
    """Identify a theorem / example / problem heading.

    Returns (kind, num, title, end_offset, title_start, title_end, balanced)
    or None.  Offsets are character positions inside ``alltext``.
    """
    for kind, rx, paren in HEAD_KINDS:
        m = rx.match(alltext)
        if not m:
            continue
        num = m.group(1)
        if not paren:
            tstart = m.end()
            title = alltext[tstart:].strip()
            return kind, num, title, len(alltext), tstart, len(alltext), True
        open_at = m.end() - 1
        depth = 0
        close_at = -1
        for i in range(open_at, len(alltext)):
            if alltext[i] == "(":
                depth += 1
            elif alltext[i] == ")":
                depth -= 1
                if depth == 0:
                    close_at = i
                    break
        if close_at < 0:
            tstart = open_at + 1
            title = alltext[tstart:].strip()
            return kind, num, title, len(alltext), tstart, len(alltext), False
        tstart = open_at + 1
        title = alltext[tstart:close_at].strip()
        return kind, num, title, close_at + 1, tstart, close_at, True
    return None


def _matched_words(ws, rx, mode="paren"):
    """How many leading words of the line belong to the heading itself."""
    text = ""
    spans = []
    for w in ws:
        if text:
            text += " "
        spans.append((len(text), len(text) + len(w.t)))
        text += w.t
    m = rx.match(text)
    if not m:
        return len(ws)
    if mode == "line" or m.lastindex is None or m.lastindex < 2:
        cut = len(text)
    else:
        cut = m.end(2) + 1          # include the closing parenthesis
    for i, (a, b) in enumerate(spans):
        if a >= cut:
            return i
    return len(ws)


def _word_spans(ws):
    """Joined text plus the character span of every word."""
    text = ""
    spans = []
    for w in ws:
        if text:
            text += " "
        spans.append((len(text), len(text) + len(w.t)))
        text += w.t
    return text, spans


def _words_upto(ws, cut):
    """Number of leading words that start before the character offset cut."""
    text = ""
    n = 0
    for w in ws:
        if text:
            text += " "
        start = len(text)
        text += w.t
        if start >= cut:
            return n
        n += 1
    return n


def _strip_prefix(runs, prefix):
    """Remove a textual prefix from the front of a run list."""
    if not prefix:
        return runs
    want = len(prefix)
    out = []
    for r in runs:
        if want <= 0:
            out.append(r)
            continue
        if r["k"] == "text":
            v = r["v"]
            take = min(want, len(v))
            r = dict(r)
            r["v"] = v[take:]
            want -= take
            if r["v"].strip():
                out.append(r)
        else:
            out.append(r)
            want = 0
    return out
