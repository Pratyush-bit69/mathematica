"""Reconstruct the Unabridged Mathematics Treatise from positioned PDF text.

Pipeline
--------
items (positioned runs)  ->  words (space split, proportional x)
                         ->  roles (math vs text)  ->  visual lines
                         ->  blocks (para / heading / display / theorem / ...)
                         ->  JSON document

Math spans are turned into a small AST (see mathast.py) that serialises to
either LaTeX (KaTeX) or HTML+Unicode (fallback).
"""
import json
import re
import sys
from collections import Counter, defaultdict

from pdfxml import load
import mathast as MA
from mathast import Run, Sym, Text, Script, Frac, Sqrt, BigOp, Matrix, Brace

MATH_FAMS = {
    "CMSY10", "CMEX10", "CMR10", "CMMI10", "PazoMath",
    "PazoMathBlackboardBold", "MSAM10", "MSBM10",
}
BODY_FAMS = {"URWPalladioL", "URWPalladioL-Roma", "URWPalladioL-Ital"}
SCRIPT_MAX = 13.5
PAGE_CENTER = 459.0          # text block centre in pdftohtml pixel space
TEXT_LEFT = 65.0
TEXT_RIGHT = 853.0


# --------------------------------------------------------------- utilities

def load_outline(path="/tmp/opencode/mathpdf/p13.html"):
    """Chapter/section outline straight from the PDF bookmarks."""
    import html as _html
    with open(path, encoding="utf-8", errors="replace") as fh:
        doc = fh.read()
    i = doc.find('<a name="outline">')
    if i < 0:
        return []
    items = re.findall(r'<li><a href="[^"]*">(.*?)</a>', doc[i:], re.S)
    out = []
    for t in items:
        t = _html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
        if t:
            out.append(t)
    return out


def split_words(item):
    """Split an item's text into words, distributing the x-range."""
    txt = item.text
    if " " not in txt.strip():
        return [(txt.strip(), item.left, item.right, item, False)]
    parts = re.split(r"(\s+)", txt)
    words = []
    for p in parts:
        if not p or p.isspace():
            continue
        words.append(p)
    if not words:
        return []
    weights = []
    for w in words:
        weights.append(sum(char_w(c) for c in w) + 0.55 * max(0, len(w) - 1))
    total = sum(weights) or 1.0
    span = item.right - item.left
    out = []
    x = item.left
    for i, (w, wt) in enumerate(zip(words, weights)):
        ww = span * wt / total
        out.append((w, x, x + ww, item, i > 0))
        x += ww
    return out


_W_CACHE = {}


def char_w(c):
    """Rough Palatino advance width in em units."""
    if c in _W_CACHE:
        return _W_CACHE[c]
    if c == " ":
        w = 0.25
    elif c in "iljI.,;:'|!ft":
        w = 0.30
    elif c in "mwMW":
        w = 0.85
    elif c in "0123456789":
        w = 0.50
    elif c.isupper():
        w = 0.68
    elif c.isalpha():
        w = 0.50
    else:
        w = 0.45
    _W_CACHE[c] = w
    return w


def classify(word, item):
    """Return the role of a word: 'math' | 'text'."""
    fam = item.family
    if fam in MATH_FAMS:
        return "math"
    if item.size <= SCRIPT_MAX:
        return "script"
    if fam == "URWPalladioL-Ital":
        # single letters are math variables; longer runs are italic body text
        return "math" if (len(word) <= 2 and word.isalpha()) else "text"
    return "text"


# ------------------------------------------------------------ math builder

class MW:
    """A math word with position and role."""

    __slots__ = ("t", "l", "r", "size", "role", "fam", "top", "bold", "sp")

    def __init__(self, t, l, r, size, role, fam, top, bold=False, sp=False):
        self.t = t
        self.l = l
        self.r = r
        self.size = size
        self.role = role
        self.fam = fam
        self.top = top
        self.bold = bold
        self.sp = sp

    @property
    def cx(self):
        return (self.l + self.r) / 2.0

    def __repr__(self):
        return f"MW({self.t!r},{self.l},{self.r},sz={self.size},{self.role})"


def group_rows(ws, tol=2.2):
    """Group words into rows by vertical position."""
    rows = []
    for w in sorted(ws, key=lambda w: (w.top, w.l)):
        placed = False
        for row in rows:
            if abs(row["top"] - w.top) <= tol:
                row["top"] = (row["top"] * row["n"] + w.top) / (row["n"] + 1)
                row["ws"].append(w)
                row["n"] += 1
                placed = True
                break
        if not placed:
            rows.append({"top": w.top, "ws": [w], "n": 1})
    for row in rows:
        row["ws"].sort(key=lambda w: w.l)
    rows.sort(key=lambda r: r["top"])
    return rows


def contiguous_groups(ws, gap=1.8):
    """Split a row into x-contiguous groups."""
    groups = []
    cur = []
    for w in ws:
        if cur and w.l - cur[-1].r > gap:
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def gspan(g):
    return (min(x.l for x in g), max(x.r for x in g))


def gcx(g):
    lo, hi = gspan(g)
    return (lo + hi) / 2.0


def build_math(words):
    """Build a math AST from a list of MW."""
    if not words:
        return Run([])
    words = merge_negations(words)
    scripts = [w for w in words if w.size <= SCRIPT_MAX + 0.01]
    bases = [w for w in words if w.size > SCRIPT_MAX + 0.01]
    if not bases:
        bases = list(words)

    base_rows = group_rows(bases, tol=5.0)
    script_rows = group_rows(scripts, tol=2.2)
    row_of = {}
    for i, row in enumerate(base_rows):
        for w in row["ws"]:
            row_of[id(w)] = i

    # ---------- matrices --------------------------------------------------
    mats = _detect_matrices(base_rows, bases)
    mat_words = set()
    for m in mats:
        for row in m["rows"]:
            for w in row:
                mat_words.add(id(w))
        for d in m["delims"]:
            mat_words.add(id(d))
    bases = [w for w in bases if id(w) not in mat_words]
    base_rows = [r for r in base_rows
                 if not any(id(w) in mat_words for w in r["ws"])]
    scripts = [w for w in scripts if id(w) not in mat_words]
    script_rows = group_rows(scripts)

    # ---------- fractions ------------------------------------------------
    fractions = list(find_script_fractions(scripts, bases))
    frac_words = set()
    for num, den, lo, hi in fractions:
        frac_words.update(id(w) for w in num + den)
    # base-sized fractions (display style) — need a clear band
    for i, r1 in enumerate(base_rows):
        for j, r2 in enumerate(base_rows):
            if j <= i:
                continue
            gap = r2["top"] - r1["top"]
            if not (12 <= gap <= 40):
                continue
            for g1 in contiguous_groups(r1["ws"]):
                if len(g1) > 3:
                    continue
                for g2 in contiguous_groups(r2["ws"]):
                    if len(g2) > 3:
                        continue
                    if abs(gcx(g1) - gcx(g2)) > 3.4:
                        continue
                    lo = min(gspan(g1)[0], gspan(g2)[0])
                    hi = max(gspan(g1)[1], gspan(g2)[1])
                    fractions.append((g1, g2, lo, hi))

    # ---------- big-operator limits --------------------------------------
    limits = _find_limits(base_rows, scripts, frac_words)

    # ---------- plain scripts (superscripts / subscripts) ----------------
    attached = {}
    used = set()
    ordered_bases = sorted(bases, key=lambda w: (row_of[id(w)], w.l))
    for bw in ordered_bases:
        if id(bw) in limits:
            continue
        if not _can_take_script(bw):
            continue
        run = []
        cursor = bw.r - 3.0
        for sw in sorted(scripts, key=lambda s: s.l):
            if id(sw) in frac_words or id(sw) in used:
                continue
            if sw.l < cursor - 0.2:
                continue
            if sw.l > bw.r + 32:
                break
            if abs(sw.top - bw.top) > 18:
                continue
            blocked = False
            for b2 in bases:
                if b2 is bw:
                    continue
                if b2.r > cursor - 0.2 and b2.l < sw.l - 0.2:
                    blocked = True
                    break
            if blocked:
                break
            run.append(sw)
            cursor = sw.r
        if not run:
            continue
        for sw in run:
            used.add(id(sw))
        slot = attached.setdefault(id(bw), {"sup": [], "sub": []})
        slot["sup" if run[0].top < bw.top - 0.5 else "sub"].extend(run)

    # ---------- accents (hats, bars, tildes) ----------------------------
    acc_of = {}
    acc_used = set()
    for aw in [w for w in words if w.t in MA.ACCENTS]:
        best = None
        for bw in bases:
            if id(bw) in acc_used:
                continue
            if bw.l - 3 <= aw.cx <= bw.r + 3:
                d = abs(bw.cx - aw.cx)
            elif 0 < aw.l - bw.r <= 16:
                d = abs(aw.l - bw.r) + 4
            else:
                continue
            if best is None or d < best[0]:
                best = (d, bw)
        if best is None:
            continue
        acc_used.add(id(aw))
        acc_of[id(best[1])] = MA.ACCENTS[aw.t][0]

    # ---------- whitespace padding ---------------------------------------
    ordered = sorted(bases, key=lambda w: (row_of.get(id(w), 0), w.l))
    pads = {}
    for i, w in enumerate(ordered):
        nxt = ordered[i + 1] if i + 1 < len(ordered) else None
        pads[id(w)] = (" " if w.sp else "",
                      " " if (nxt is not None and nxt.sp) else "")

    consumed = set(frac_words)
    consumed.update(acc_used)
    for slot in attached.values():
        for ws in slot.values():
            consumed.update(id(w) for w in ws)
    for lim in limits.values():
        consumed.update(id(w) for w in lim["sup"] + lim["sub"])

    node = _assemble(base_rows, bases, fractions, limits, attached,
                     consumed, acc_of, pads)
    if mats:
        node = Run([_matrix_node(m) for m in mats] + list(node.parts))
    return node


def _detect_matrices(base_rows, bases):
    """Find grid-like regions (matrices) surrounded by big delimiters."""
    mats = []
    i = 0
    n = len(base_rows)
    while i < n:
        row = base_rows[i]
        groups = contiguous_groups(row["ws"])
        if len(groups) >= 3 and all(x.size > SCRIPT_MAX for x in row["ws"]):
            j = i
            block = []
            while j < n:
                g = contiguous_groups(base_rows[j]["ws"])
                if len(g) >= 2 and all(x.size > SCRIPT_MAX
                                      for x in base_rows[j]["ws"]):
                    block.append(base_rows[j])
                    j += 1
                else:
                    break
            if len(block) >= 2:
                cols = [gspan(g) for g in contiguous_groups(block[0]["ws"])]
                ok = True
                for brow in block[1:]:
                    gs = contiguous_groups(brow["ws"])
                    if len(gs) != len(cols):
                        ok = False
                        break
                    for (c0, c1), g in zip(cols, gs):
                        lo, hi = gspan(g)
                        if abs(lo - c0) > 7 or abs(hi - c1) > 7:
                            ok = False
                            break
                    if not ok:
                        break
                if ok:
                    left = min(gspan(g)[0] for g in cols)
                    right = max(gspan(g)[1] for g in cols)
                    delims = [w for w in bases
                              if w.fam == "CMEX10" and not w.t and
                              (abs(w.l - left) < 24 or abs(w.l - right) < 24)]
                    mats.append({"rows": block, "cols": cols, "delims": delims})
                    i = j
                    continue
        i += 1
    return mats


def _matrix_node(m):
    cells = []
    for brow in m["rows"]:
        row = []
        for g in contiguous_groups(brow["ws"]):
            row.append(_run_of(g))
        cells.append(row)
    ncol = max(len(r) for r in cells)
    for r in cells:
        while len(r) < ncol:
            r.append(Run([]))
    return Matrix(cells, "bmatrix")


def find_script_fractions(scripts, bases=None):
    """Pair stacked script groups into fractions (numerator over denominator).

    A fraction's numerator and denominator are vertically well separated;
    a superscript and a subscript on the same base are much closer, so the
    minimum gap keeps the two apart.  Two groups belonging to the same base
    word are a super/subscript pair, never a fraction.
    """
    def owner(group):
        if bases is None:
            return None
        best = None
        for b in bases:
            if b.r <= group[0].l + 2.0 and b.r >= group[0].l - 34:
                d = abs(b.r - group[0].l)
                if best is None or d < best[0]:
                    best = (d, id(b))
        return best[1] if best else None

    rows = group_rows(scripts, tol=2.2)
    out = []
    for i, r1 in enumerate(rows):
        for j, r2 in enumerate(rows):
            if j <= i:
                continue
            gap = r2["top"] - r1["top"]
            if not (10 <= gap <= 34):
                continue
            for g1 in contiguous_groups(r1["ws"]):
                for g2 in contiguous_groups(r2["ws"]):
                    if abs(gcx(g1) - gcx(g2)) > 3.6:
                        continue
                    o1, o2 = owner(g1), owner(g2)
                    if o1 is not None and o1 == o2:
                        continue          # super/subscript of one base
                    lo = min(gspan(g1)[0], gspan(g2)[0])
                    hi = max(gspan(g1)[1], gspan(g2)[1])
                    out.append((g1, g2, lo, hi))
    # keep the tightest non-overlapping pairs
    out.sort(key=lambda f: (f[2], f[3] - f[2]))
    kept = []
    for f in out:
        ok = True
        for k in kept:
            if not (f[3] <= k[2] + 1.5 or f[2] >= k[3] - 1.5):
                ok = False
                break
        if ok:
            kept.append(f)
    return kept


BIG_OPS = set("∑∏∫∬∮⋃⋂")


def _find_limits(base_rows, scripts, frac_words):
    """Attach upper/lower limits to large operators."""
    limits = {}
    for row in base_rows:
        for w in row["ws"]:
            if w.t not in BIG_OPS:
                continue
            sup, sub = [], []
            for sw in scripts:
                if id(sw) in frac_words:
                    continue
                if sw.l < w.l - 16 or sw.l > w.r + 16:
                    continue
                if abs(sw.top - w.top) > 16:
                    continue
                if sw.top < w.top - 1:
                    sup.append(sw)
                elif sw.top > w.top + 2:
                    sub.append(sw)
            if sup or sub:
                limits[id(w)] = {"sup": sup, "sub": sub}
    return limits


def merge_negations(words):
    """Fold the slashes LaTeX draws over = and ∈ into ≠ and ∉."""
    out = []
    ws = sorted(words, key=lambda w: (w.top, w.l))
    i = 0
    while i < len(ws):
        w = ws[i]
        nxt = ws[i + 1] if i + 1 < len(ws) else None
        if nxt is not None and abs(nxt.l - w.l) <= 7:
            if w.t in ("̸", "/") and nxt.t == "=":
                out.append(MW("≠", min(w.l, nxt.l), max(w.r, nxt.r),
                              nxt.size, "math", "CMSY10", w.top))
                i += 2
                continue
            if w.t in ("̸", "/") and nxt.t == "∈":
                out.append(MW("∉", min(w.l, nxt.l), max(w.r, nxt.r),
                              nxt.size, "math", "CMSY10", w.top))
                i += 2
                continue
            if w.t == "=" and nxt.t in ("̸", "/"):
                out.append(MW("≠", min(w.l, nxt.l), max(w.r, nxt.r),
                              w.size, "math", "CMSY10", w.top))
                i += 2
                continue
            if w.t == "∈" and nxt.t in ("̸", "/"):
                out.append(MW("∉", min(w.l, nxt.l), max(w.r, nxt.r),
                              w.size, "math", "CMSY10", w.top))
                i += 2
                continue
        out.append(w)
        i += 1
    return out


def _can_take_script(w):
    """Only letters, digits and closing delimiters carry scripts."""
    t = w.t
    if len(t) == 1:
        return t.isalnum() or t in ")]}"
    if len(t) == 2 and t[1] == "." and t[0].isalpha():
        return True
    return bool(re.fullmatch(r"[A-Za-z]{2,}", t))


def _sym_node(w, pad=None):
    t = w.t
    if w.fam == "PazoMathBlackboardBold":
        return Sym(t, "bb")
    if w.fam == "CMSY10" and t.isalpha():
        return Sym(t, "cal")
    if w.fam == "CMMI10":
        return Sym(t, "var")
    if t.lower() in MA.MATH_WORDS and w.fam in ("PazoMath", "CMSY10", "CMR10"):
        return Sym(t, "op")
    if w.fam in ("PazoMath", "CMSY10", "CMR10", "CMEX10"):
        return Sym(t, "sym")
    if re.fullmatch(r"[A-Za-z]{2,}", t):
        lead, trail = pad if pad else ("", "")
        return Text(lead + t + trail)
    if len(t) == 1 and t.isalpha():
        return Sym(t, "var")
    return Sym(t, "sym")


def _node_for(w, attached, pad=None, depth=0):
    """Full node for a word, including any script attached to it."""
    slot = attached.get(id(w))
    if slot and (slot["sup"] or slot["sub"]) and depth < 3:
        sup = _run_of(slot["sup"], attached, None, depth + 1) if slot["sup"] else None
        sub = _run_of(slot["sub"], attached, None, depth + 1) if slot["sub"] else None
        return Script(_sym_node(w, pad), sup, sub)
    return _sym_node(w, pad)


def _detect_matrices(rows, words):
    """Find grid-like regions (matrices)."""
    mats = []
    i = 0
    n = len(rows)
    while i < n:
        # a matrix row has >= 3 groups and is base sized
        r = rows[i]
        groups = contiguous_groups(r["ws"])
        if len(groups) >= 3 and all(x.size > SCRIPT_MAX for x in r["ws"]):
            j = i
            block = []
            while j < n:
                g = contiguous_groups(rows[j]["ws"])
                if len(g) >= 2 and all(x.size > SCRIPT_MAX for x in rows[j]["ws"]):
                    block.append(rows[j])
                    j += 1
                else:
                    break
            if len(block) >= 2:
                # verify column alignment
                cols = [gspan(g) for g in contiguous_groups(block[0]["ws"])]
                ok = True
                for brow in block[1:]:
                    gs = contiguous_groups(brow["ws"])
                    if len(gs) != len(cols):
                        ok = False
                        break
                    for (c0, c1), g in zip(cols, gs):
                        lo, hi = gspan(g)
                        if abs(lo - c0) > 6 or abs(hi - c1) > 6:
                            ok = False
                            break
                    if not ok:
                        break
                if ok:
                    mats.append({"rows": block, "cols": cols})
                    i = j
                    continue
        i += 1
    return mats


TERMINATORS = {",", ";", "=", "]", "}", ":", "!", "?"}


def _radical_node(root, base_words, attached, pads=None):
    """Build a sqrt node: the radicand runs to a balanced group or terminator."""
    cand = sorted([w for w in base_words if w.l >= root.r - 2.0],
                  key=lambda w: w.l)
    rad = []
    depth = 0
    for w in cand:
        t = w.t
        if t == "(":
            depth += 1
            rad.append(w)
            continue
        if t == ")":
            if depth == 0:
                break
            depth -= 1
            rad.append(w)
            if depth == 0:
                break
            continue
        if depth == 0:
            if t in TERMINATORS:
                break
            if t in ("+", "−", "-"):
                # keep the operator only if what follows rises above the axis
                nxt = _next_base(cand, w)
                if nxt is None:
                    break
                slot = attached.get(id(nxt))
                if not (slot and (slot["sup"] or slot["sub"])):
                    break
        rad.append(w)
    if not rad:
        return Sym("√", "sym"), []
    return Sqrt(_run_of(rad, attached, pads)), rad


def _next_base(cand, w):
    for x in cand:
        if x.l > w.r - 0.5:
            return x
    return None


def _assemble(base_rows, bases, fractions, limits, attached, consumed,
               acc_of=None, pads=None):
    """Walk the base rows and build the node tree."""
    acc_of = acc_of or {}
    pads = pads or {}
    frac_at = {}
    for num, den, lo, hi in fractions:
        anchor = None
        for w in bases:
            if w.r <= lo + 3.0 and (anchor is None or w.r > anchor.r):
                anchor = w
        if anchor is None:
            continue
        frac_at.setdefault(id(anchor), (num, den))

    out = []
    for r in base_rows:
        row_nodes = []
        prev_end = None
        for g in contiguous_groups(r["ws"]):
            prev_end = max(x.r for x in g)
            i = 0
            while i < len(g):
                w = g[i]
                if id(w) in consumed:
                    i += 1
                    continue
                if w.t == "√":
                    node, used = _radical_node(w, bases, attached, pads)
                    row_nodes.append(node)
                    for u in used:
                        consumed.add(id(u))
                    consumed.add(id(w))
                    i += 1
                    while i < len(g) and g[i] in used:
                        i += 1
                    continue
                i += 1
                if id(w) in frac_at:
                    num, den = frac_at[id(w)]
                    row_nodes.append(Frac(_run_of(num, attached, pads),
                                          _run_of(den, attached, pads)))
                    continue
                lim = limits.get(id(w))
                if lim:
                    sup = _run_of(lim["sup"], attached, pads) if lim["sup"] else None
                    sub = _run_of(lim["sub"], attached, pads) if lim["sub"] else None
                    row_nodes.append(BigOp(w.t, sup, sub))
                    continue
                if id(w) in acc_of:
                    row_nodes.append(MA.Accent(_node_for(w, attached, pads.get(id(w))),
                                               acc_of[id(w)]))
                    continue
                row_nodes.append(_node_for(w, attached, pads.get(id(w))))
        if row_nodes:
            out.append(Run(row_nodes))
    return Run(out)


def _run_of(group, attached=None, pads=None, depth=0):
    parts = []
    for w in group:
        parts.append(_node_for(w, attached, (pads or {}).get(id(w)), depth))
    return Run(parts)


def _base_node(group, attached, frac_by_band):
    """Build node(s) for a contiguous x-group of base words."""
    parts = []
    for w in group:
        if parts and w.sp:
            parts.append(MA.Spacer())
        slot = attached.get(id(w))
        if slot and (slot["sup"] or slot["sub"]):
            sup = _run_of(slot["sup"], attached) if slot["sup"] else None
            sub = _run_of(slot["sub"], attached) if slot["sub"] else None
            parts.append(Script(_sym_node(w), sup, sub))
        else:
            parts.append(_sym_node(w))
    if len(parts) == 1:
        return parts[0]
    return Run(parts)


def _radical(group, rows, frac_by_band):
    """Build a sqrt node; the radicand runs until a terminator."""
    root = group[0]
    lo, hi = gspan(group)
    # gather following words from the same and adjacent rows
    seq = []
    for r in rows:
        if r["top"] < root.top - 12:
            continue
        for w in r["ws"]:
            if w.l >= root.r - 1:
                seq.append((r, w))
    seq.sort(key=lambda rw: (rw[0]["top"], rw[1].l))
    rad = []
    depth = 0
    for r, w in seq:
        if w is root:
            continue
        if w.size <= SCRIPT_MAX + 0.01 and not rad:
            continue
        if w.t == "(":
            depth += 1
        elif w.t == ")":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and w.t in (",", ";", "=", "]", "}", "→"):
            break
        rad.append(w)
        if depth == 0 and w.t == ")":
            break
    if not rad:
        return Sym("√", "sym"), None
    return Sqrt(_run_of(rad)), None
