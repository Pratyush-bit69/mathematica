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

PDF = os.environ.get("MATHEMATICA_PDF") or os.path.expanduser(
    "~/Downloads/Unabridged_Mathematics_Treatise_Complete.pdf")
XML = "/tmp/opencode/mathpdf/doc.xml"
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "data",
                   "treatise.js")
WORK = "/tmp/opencode/mathpdf"


def ensure_inputs():
    """Regenerate the pdftohtml extracts if they are missing."""
    if os.path.exists(XML) and os.path.exists(os.path.join(WORK, "p13.html")):
        return
    if not os.path.exists(PDF):
        sys.exit(f"source PDF not found: {PDF}\n"
                 f"set MATHEMATICA_PDF=/path/to/"
                 f"Unabridged_Mathematics_Treatise_Complete.pdf")
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
        page_text = " ".join(it.text for it in items)
        if re.search(r"\bPart\s+II\s*:\s*Complete\s+Stage", page_text):
            break               # the video curriculum is not part of the treatise
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

    # ---------------------------------------------------------- corrections
    # The PDF source numbers twenty exams in §22.2 (22.11–22.30), but its
    # outline still says "10 … (22.11 – 22.20)". Make the visible heading
    # match the actual contents.
    for c in chapters:
        if c["num"] == 22:
            for s in c["sections"]:
                if s["num"] == "22.2":
                    s["title"] = ("Final Exam Part B: 20 Advanced Wall Street "
                                  "Quant & PhD AI Proofs (22.11 – 22.30)")

    # A handful of sections begin with a stray numerator/delimiter glyph that
    # the PDF placed on its own line above the paragraph. Drop just that
    # fragment; the substantive paragraph follows immediately.
    leading_junk = {
        "2.3": 1, "3.3": 1, "4.2": 1, "7.3": 1, "8.1": 1,
    }
    for c in chapters:
        for s in c["sections"]:
            n = leading_junk.get(s["num"], 0)
            if n and len(s["blocks"]) > n:
                s["blocks"] = s["blocks"][n:]

    # These two early sections were split across fraction/radical rows in the
    # PDF, leaving the gallery formulas fragmented. Replace them with the
    # source text, typeset cleanly.
    def md_runs(text):
        runs = []
        for part in re.split(r"(\$[^$]+\$)", text):
            if not part:
                continue
            if len(part) > 1 and part[0] == "$" and part[-1] == "$":
                runs.append({"k": "math", "latex": part[1:-1]})
            else:
                runs.append({"k": "text", "v": part})
        return runs

    def para(text):
        return {"type": "para", "runs": md_runs(text)}

    def bullet(text):
        return {"type": "bullet", "runs": md_runs(text)}

    def display(text):
        return {"type": "display", "runs": md_runs(text)}

    def theorem(num, title, text):
        return {"type": "theorem", "num": num, "title": title,
                "runs": md_runs(text), "open": True}

    def proof(title, text):
        return {"type": "proof", "title": title, "runs": md_runs(text)}

    def example(num, title, heading=""):
        return {"type": "example", "num": num, "title": title,
                "runs": md_runs(heading), "open": True}

    def question(text):
        return {"type": "question", "label": "Problem", "runs": md_runs(text)}

    def solution(text):
        return {"type": "solution",
                "label": "Detailed Step-by-Step Solution",
                "runs": md_runs(text)}

    def exam_block(num, title, question, solution):
        return {"type": "exam", "num": num, "title": title,
                "open": False,
                "runs": md_runs(question)}
    overrides = {
        "2.5": [
            example("2.1", "Argand Locus of a Purely Imaginary Quotient"),
            question(r"Let $z=x+iy\in\mathbb{C}$. Find the Cartesian "
                     r"equation and geometric locus of points $z$ such that "
                     r"$\frac{z-1}{z+i}$ is purely imaginary."),
            solution(r"A complex number $w$ is purely imaginary iff "
                     r"$\operatorname{Re}(w)=0$ (with $z\neq -i$). Multiply "
                     r"numerator and denominator by the conjugate of the "
                     r"denominator:"),
            display(r"$\frac{z-1}{z+i}="
                    r"\frac{(x-1)+iy}{x+i(y+1)}\cdot"
                    r"\frac{x-i(y+1)}{x-i(y+1)}="
                    r"\frac{x(x-1)+y(y+1)+i\left[xy-(x-1)(y+1)\right]}"
                    r"{x^{2}+(y+1)^{2}}.$"),
            para(r"Setting the real part equal to zero gives:"),
            display(r"$x^{2}-x+y^{2}+y=0\iff"
                    r"\left(x-\frac{1}{2}\right)^{2}+"
                    r"\left(y+\frac{1}{2}\right)^{2}=\frac{1}{2},"
                    r"\qquad (x,y)\neq(0,-1).$"),
            para(r"Geometrically, this is the circle with diameter endpoints "
                 r"$A(1,0)$ and $B(0,-1)$ (center "
                 r"$\left(\frac{1}{2},-\frac{1}{2}\right)$, radius "
                 r"$\frac{1}{\sqrt{2}}$), punctured at $B(0,-1)$."),

            example("2.2", "Newton's Recurrence for High-Degree Root "
                           "Combination"),
            question(r"If $\alpha$ and $\beta$ are the roots of "
                     r"$x^{2}-6x-2=0$ and "
                     r"$a_{n}=\alpha^{n}-\beta^{n}$ for $n\geq1$, find the "
                     r"exact numerical value of "
                     r"$\frac{a_{10}-2a_{8}}{2a_{9}}$."),
            solution(r"Since $\alpha$ and $\beta$ satisfy "
                     r"$t^{2}-6t-2=0\iff t^{2}-2=6t$, multiply by "
                     r"$\alpha^{8}$ and $\beta^{8}$ respectively:"),
            display(r"$\alpha^{10}-2\alpha^{8}=6\alpha^{9}"
                    r"\qquad\text{and}\qquad"
                    r"\beta^{10}-2\beta^{8}=6\beta^{9}.$"),
            para(r"Subtracting the second equation from the first yields:"),
            display(r"$(\alpha^{10}-\beta^{10})-"
                    r"2(\alpha^{8}-\beta^{8})="
                    r"6(\alpha^{9}-\beta^{9})\implies "
                    r"a_{10}-2a_{8}=6a_{9}\implies "
                    r"\frac{a_{10}-2a_{8}}{2a_{9}}="
                    r"\frac{6a_{9}}{2a_{9}}=3.$"),

            example("2.3", "Location of Roots in a Bounded Interval"),
            question(r"Find the complete set of real values of $m$ for which "
                     r"both roots of the quadratic equation "
                     r"$x^{2}-2mx+m^{2}-1=0$ lie strictly in the interval "
                     r"$(-2,4)$."),
            solution(r"Factor or complete the square directly: "
                     r"$(x-m)^{2}-1=0\implies x=m-1$ and $x=m+1$. (Or "
                     r"apply Location of Roots: $D=4\geq0$, vertex "
                     r"$x_{v}=m\in(-2,4)$, "
                     r"$f(-2)=(m+2)^{2}-1>0$, "
                     r"$f(4)=(m-4)^{2}-1>0$.) Requiring both roots $m-1$ "
                     r"and $m+1$ to lie strictly inside $(-2,4)$ gives:"),
            display(r"$m-1>-2\implies m>-1,\qquad\text{and}\qquad "
                    r"m+1<4\implies m<3.$"),
            para(r"Intersecting the two conditions gives "
                 r"$m\in(-1,3)$."),

            example("2.4", "Wavy-Curve Sign Chart with Even & Odd "
                           "Multiplicities"),
            question(r"Solve the rational inequality "
                     r"$\frac{(x-1)^{3}(x+2)^{4}(x-3)^{5}}"
                     r"{(x+1)^{2}(x-4)}\leq0$ for $x\in\mathbb{R}$."),
            solution(r"Step 1 (Critical Points & Domain): Denominator roots "
                     r"$x=-1$ and $x=4$ are strictly excluded "
                     r"($x\neq-1,4$). Numerator roots $x=-2,1,3$ satisfy "
                     r"equality $=0$ and are included."),
            para(r"Step 2 (Sign Chart from Right to Left): The critical "
                 r"points in order are $-2<-1<1<3<4$:"),
            bullet(r"On $(4,\infty)$: all factors $>0\implies(+)$."),
            bullet(r"Cross $x=4$ (odd multiplicity 1): sign flips to $(-)$ "
                   r"on $[3,4)$."),
            bullet(r"Cross $x=3$ (odd multiplicity 5): sign flips to $(+)$ "
                   r"on $[1,3]$."),
            bullet(r"Cross $x=1$ (odd multiplicity 3): sign flips to $(-)$ "
                   r"on $(-1,1]$ and $(-2,-1)$ (since $x=-1$ has even "
                   r"multiplicity 2, sign remains $(-)$ across $-1$)."),
            bullet(r"Cross $x=-2$ (even multiplicity 4): sign remains $(-)$ "
                   r"on $(-\infty,-2]$."),
            para(r"Combining all negative intervals and including numerator "
                 r"zeros gives "
                 r"$x\in(-\infty,-1)\cup(-1,1]\cup[3,4)$."),

            example("2.5", "Cube Roots of Unity Matrix & Polynomial "
                           "Evaluation"),
            question(r"Let $\omega=e^{i2\pi/3}$ be a complex cube root of "
                     r"unity. Evaluate "
                     r"$S=\sum_{k=1}^{100}\left(\omega^{k}+"
                     r"\omega^{2k}\right)$ and simplify "
                     r"$(1-\omega+\omega^{2})^{5}+"
                     r"(1+\omega-\omega^{2})^{5}$."),
            solution(r"Part 1: Whenever $3\mid k$, "
                     r"$\omega^{k}+\omega^{2k}=1+1=2$; whenever "
                     r"$3\nmid k$, $\omega^{k}+\omega^{2k}=-1$. Over any 3 "
                     r"consecutive integers, the sum is "
                     r"$2+(-1)+(-1)=0$! Since $100=3(33)+1$, the first 99 "
                     r"terms sum to $0$, leaving only $k=100$: "
                     r"$\omega^{100}+\omega^{200}=\omega+\omega^{2}=-1$."),
            para(r"Part 2: Using $1+\omega^{2}=-\omega$ and "
                 r"$1+\omega=-\omega^{2}$:"),
            display(r"$(1-\omega+\omega^{2})^{5}+"
                    r"(1+\omega-\omega^{2})^{5}="
                    r"(-2\omega)^{5}+(-2\omega^{2})^{5}="
                    r"-32(\omega^{5}+\omega^{10})="
                    r"-32(\omega^{2}+\omega)=-32(-1)=32.$"),

            example("2.6", "Double-Modulus Inequality "
                           "|x² − 5x + 4| ≤ 6"),
            question(r"Solve the inequality $|x^{2}-5x+4|\leq6$ for "
                     r"$x\in\mathbb{R}$."),
            solution(r"The inequality $|u|\leq6$ is equivalent to the "
                     r"simultaneous system "
                     r"$-6\leq x^{2}-5x+4\leq6$:"),
            para(r"1. Upper bound: $x^{2}-5x+4\leq6\iff "
                 r"x^{2}-5x-2\leq0\iff x\in"
                 r"\left[\frac{5-\sqrt{33}}{2},"
                 r"\frac{5+\sqrt{33}}{2}\right]$."),
            para(r"2. Lower bound: $x^{2}-5x+4\geq-6\iff "
                 r"x^{2}-5x+10\geq0$. Since discriminant "
                 r"$D=25-40=-15<0$ and leading coefficient is $+1$, this "
                 r"holds for all $x\in\mathbb{R}$!"),
            para(r"Thus the solution set is "
                 r"$\left[\frac{5-\sqrt{33}}{2},"
                 r"\frac{5+\sqrt{33}}{2}\right]$."),
        ],
        "3.3": [
            para(r"1. Ordinary Generating Functions (OGFs) for Constrained "
                 r"Counting & Vandermonde's Identity: To count integer "
                 r"solutions to $x_{1}+x_{2}+\cdots+x_{r}=n$ where each "
                 r"$x_{i}\in S_{i}$, represent each variable's allowed "
                 r"choices as a polynomial $\sum_{k\in S_{i}}z^{k}$. The "
                 r"number of solutions is the coefficient $[z^{n}]$ in the "
                 r"product $\prod_{i=1}^{r}\left(\sum_{k\in S_{i}}z^{k}"
                 r"\right)$! For $x_{i}\geq0$, "
                 r"$\sum_{k=0}^{\infty}z^{k}=(1-z)^{-1}$, so:"),
            display(r"$[z^{n}](1-z)^{-r}=[z^{n}]\sum_{n=0}^{\infty}"
                    r"\binom{n+r-1}{r-1}z^{n}="
                    r"\binom{n+r-1}{r-1}.$"),
            para(r"Similarly, equating $[z^{k}]$ on both sides of "
                 r"$(1+z)^{m}(1+z)^{n}=(1+z)^{m+n}$ immediately proves "
                 r"Vandermonde's Convolution "
                 r"$\sum_{j=0}^{k}\binom{m}{j}\binom{n}{k-j}="
                 r"\binom{m+n}{k}$ without induction!"),
            para(r"2. Finite Difference Operator "
                 r"$\Delta u_{k}=u_{k+1}-u_{k}$ & Falling Factorials "
                 r"$k^{\underline{m}}$: Define the $m$-th falling factorial "
                 r"$k^{\underline{m}}=k(k-1)\cdots(k-m+1)$ and rising "
                 r"factorial $k^{(m)}=k(k+1)\cdots(k+m-1)$. Just as "
                 r"$\frac{d}{dx}(x^{m})=mx^{m-1}$ in continuous calculus, "
                 r"forward differencing obeys:"),
            display(r"$\Delta\left[k(k+1)\cdots(k+m)\right]="
                    r"(k+1)\cdots(k+m+1)-k(k+1)\cdots(k+m)="
                    r"(m+1)k(k+1)\cdots(k+m-1).$"),
            para(r"Summing from $k=1$ to $n$ telescopes immediately into "
                 r"the universal discrete integral:"),
            display(r"$\sum_{k=1}^{n}k(k+1)\cdots(k+m-1)="
                    r"\frac{n(n+1)\cdots(n+m)}{m+1},$"),
            display(r"$\sum_{k=1}^{n}\frac{1}{k(k+1)\cdots(k+m)}="
                    r"\frac{1}{m}\left[\frac{1}{1\cdot2\cdots m}-"
                    r"\frac{1}{(n+1)\cdots(n+m)}\right].$"),
        ],
        "4.2": [
            para(r"1. Block Gaussian Elimination & Schur's Determinant "
                 r"Formula: For any block matrix "
                 r"$M=\begin{pmatrix}A&B\\C&D\end{pmatrix}$ with $A$ "
                 r"invertible, factoring out "
                 r"$\begin{pmatrix}I&0\\CA^{-1}&I\end{pmatrix}$ yields:"),
            display(r"$\begin{pmatrix}A&B\\C&D\end{pmatrix}"
                    r"\begin{pmatrix}I&0\\CA^{-1}&I\end{pmatrix}="
                    r"\begin{pmatrix}A&B\\0&D-CA^{-1}B\end{pmatrix}"
                    r"\implies\det\begin{pmatrix}A&B\\C&D\end{pmatrix}="
                    r"\det(A)\det(D-CA^{-1}B).$"),
            para(r"Applying this to "
                 r"$\begin{pmatrix}I_{m}&-U\\-V^{T}&I_{n}\end{pmatrix}$ "
                 r"immediately proves the Sylvester-Weinstein Determinant "
                 r"Identity $\det(I_{n}-V^{T}U)=\det(I_{m}-UV^{T})$ (and "
                 r"for vectors $u,v$, $\det(I+uv^{T})=1+v^{T}u$)!"),
            para(r"2. Polynomial Division & Cayley-Hamilton Power "
                 r"Reduction: To evaluate a high matrix power $A^{N}$ "
                 r"(e.g., $A^{50}$) for a $k\times k$ matrix with "
                 r"characteristic polynomial "
                 r"$p(\lambda)=\det(\lambda I-A)=0$, divide $\lambda^{N}$ "
                 r"by $p(\lambda)$:"),
            display(r"$\lambda^{N}=q(\lambda)p(\lambda)+r(\lambda),"
                    r"\qquad \deg(r)\leq k-1.$"),
            para(r"Since $p(A)=0$ by Cayley-Hamilton, $A^{N}=r(A)$, where "
                 r"the $k$ coefficients of "
                 r"$r(\lambda)=c_{0}+c_{1}\lambda+\cdots+"
                 r"c_{k-1}\lambda^{k-1}$ are found simply by plugging the "
                 r"$k$ scalar eigenvalues $\lambda_{i}$ into "
                 r"$\lambda_{i}^{N}=r(\lambda_{i})$!"),
        ],
        "5.1": [
            bullet(r"Distance, Section & Shoelace Area Formulas: Between "
                   r"$P(x_{1},y_{1})$ and $Q(x_{2},y_{2})$, "
                   r"$d=\sqrt{(x_{2}-x_{1})^{2}+(y_{2}-y_{1})^{2}}$. The "
                   r"point dividing $PQ$ internally in ratio $m:n$ is "
                   r"$\left(\frac{mx_{2}+nx_{1}}{m+n},"
                   r"\frac{my_{2}+ny_{1}}{m+n}\right)$ (replace $n$ with "
                   r"$-n$ for external division). Area of $\triangle ABC$ "
                   r"is $\Delta=\frac{1}{2}\left|x_{1}(y_{2}-y_{3})+"
                   r"x_{2}(y_{3}-y_{1})+x_{3}(y_{1}-y_{2})\right|$."),
            bullet(r"The Four Classical Centers of $\triangle ABC$ with "
                   r"side lengths $a=BC$, $b=CA$, $c=AB$:"),
            para(r"1. Centroid $G$ (intersection of medians, divides each "
                 r"median in $2:1$): "
                 r"$G=\left(\frac{x_{1}+x_{2}+x_{3}}{3},"
                 r"\frac{y_{1}+y_{2}+y_{3}}{3}\right)$."),
            para(r"2. Incenter $I$ (intersection of internal angle "
                 r"bisectors, center of inscribed circle): "
                 r"$I=\left(\frac{ax_{1}+bx_{2}+cx_{3}}{a+b+c},"
                 r"\frac{ay_{1}+by_{2}+cy_{3}}{a+b+c}\right)$."),
            para(r"3. Circumcenter $O$ (intersection of perpendicular "
                 r"bisectors, equidistant from $A,B,C$): In a right "
                 r"triangle, $O$ is the midpoint of the hypotenuse!"),
            para(r"4. Orthocenter $H$ (intersection of altitudes): In a "
                 r"right triangle, $H$ is the vertex of the $90^{\circ}$ "
                 r"angle! For any non-equilateral triangle, $O,G,H$ lie on "
                 r"the Euler Line with $G$ dividing $OH$ internally in "
                 r"ratio $OG:GH=1:2$, so $H=3G-2O$."),
            bullet(r"All Six Standard Equations of a Straight Line:"),
            para(r"1. Slope-Intercept: $y=mx+c$"),
            para(r"2. Point-Slope: $y-y_{1}=m(x-x_{1})$"),
            para(r"3. Two-Point: "
                 r"$\frac{y-y_{1}}{x-x_{1}}="
                 r"\frac{y_{2}-y_{1}}{x_{2}-x_{1}}$"),
            para(r"4. Intercept Form: $\frac{x}{a}+\frac{y}{b}=1$"),
            para(r"5. Normal Form: $x\cos\alpha+y\sin\alpha=p$ $(p>0)$"),
            para(r"6. Parametric/Distance Form: "
                 r"$\frac{x-x_{1}}{\cos\theta}="
                 r"\frac{y-y_{1}}{\sin\theta}=r$"),
            theorem("5.1",
                    "Acute Angle, Perpendicular Distance, Foot of "
                    "Perpendicular & Mirror Image Proofs",
                    r"1. Acute Angle Between Two Lines with Slopes "
                    r"$m_{1},m_{2}$: "
                    r"$\tan\theta=\left|\frac{m_{1}-m_{2}}"
                    r"{1+m_{1}m_{2}}\right|$ (parallel iff $m_{1}=m_{2}$; "
                    r"perpendicular iff $m_{1}m_{2}=-1$)."),
            para(r"2. Perpendicular Distance, Foot of Perpendicular "
                 r"$M(h,k)$ & Mirror Image $Q(x',y')$ in "
                 r"$ax+by+c=0$: From point $P(x_{1},y_{1})$ to line "
                 r"$L:ax+by+c=0$, the normal vector is $n=(a,b)^{T}$. Any "
                 r"point along the normal through $P$ has coordinates "
                 r"$(x_{1}+\lambda a,y_{1}+\lambda b)$."),
            bullet(r"Foot of Perpendicular $M(h,k)$: Since $M\in L$, "
                   r"$a(x_{1}+\lambda a)+b(y_{1}+\lambda b)+c=0\implies "
                   r"\lambda=-\frac{ax_{1}+by_{1}+c}{a^{2}+b^{2}}$:"),
            display(r"$\frac{h-x_{1}}{a}=\frac{k-y_{1}}{b}="
                    r"-\frac{ax_{1}+by_{1}+c}{a^{2}+b^{2}},\qquad "
                    r"d(P,L)=\|M-P\|_{2}=|\lambda|\sqrt{a^{2}+b^{2}}="
                    r"\frac{|ax_{1}+by_{1}+c|}{\sqrt{a^{2}+b^{2}}}.$"),
            bullet(r"Mirror Image $Q(x',y')$: Since $M$ is the midpoint of "
                   r"$PQ$, $Q=P+2\lambda n$, doubling the right-hand side:"),
            display(r"$\frac{x'-x_{1}}{a}=\frac{y'-y_{1}}{b}="
                    r"-\frac{2(ax_{1}+by_{1}+c)}{a^{2}+b^{2}}."
                    r"\quad\blacksquare$"),
            para(r"3. Angle Bisectors of $a_{1}x+b_{1}y+c_{1}=0$ and "
                 r"$a_{2}x+b_{2}y+c_{2}=0$ (normalized with "
                 r"$c_{1},c_{2}>0$):"),
            display(r"$\frac{a_{1}x+b_{1}y+c_{1}}"
                    r"{\sqrt{a_{1}^{2}+b_{1}^{2}}}=\pm"
                    r"\frac{a_{2}x+b_{2}y+c_{2}}"
                    r"{\sqrt{a_{2}^{2}+b_{2}^{2}}}.$"),
            para(r"Here the $+$ sign gives the bisector of the region "
                 r"containing the origin $(0,0)$. If "
                 r"$a_{1}a_{2}+b_{1}b_{2}>0$, the $-$ sign gives the "
                 r"acute angle bisector and the $+$ sign gives the obtuse "
                 r"angle bisector."),
        ],
        "7.1": [
            bullet(r"The 9 Quadratic & Square-Root Master Formulas "
                   r"(Complete Reference):"),
            display(r"$\int\frac{dx}{x^{2}-a^{2}}="
                    r"\frac{1}{2a}\ln\left|\frac{x-a}{x+a}\right|+C,"
                    r"\qquad \int\frac{dx}{a^{2}-x^{2}}="
                    r"\frac{1}{2a}\ln\left|\frac{a+x}{a-x}\right|+C,$"),
            display(r"$\int\frac{dx}{x^{2}+a^{2}}="
                    r"\frac{1}{a}\arctan\frac{x}{a}+C,\qquad "
                    r"\int\frac{dx}{\sqrt{a^{2}-x^{2}}}="
                    r"\arcsin\frac{x}{a}+C,$"),
            display(r"$\int\frac{dx}{\sqrt{x^{2}\pm a^{2}}}="
                    r"\ln\left|x+\sqrt{x^{2}\pm a^{2}}\right|+C,$"),
            display(r"$\int\sqrt{a^{2}-x^{2}}\,dx="
                    r"\frac{x}{2}\sqrt{a^{2}-x^{2}}+"
                    r"\frac{a^{2}}{2}\arcsin\frac{x}{a}+C,$"),
            display(r"$\int\sqrt{x^{2}\pm a^{2}}\,dx="
                    r"\frac{x}{2}\sqrt{x^{2}\pm a^{2}}\pm"
                    r"\frac{a^{2}}{2}\ln\left|x+\sqrt{x^{2}\pm a^{2}}"
                    r"\right|+C.$"),
            bullet(r"Weierstrass Half-Angle Substitution for "
                   r"$\int\frac{dx}{a+b\cos x+c\sin x}$: Set "
                   r"$t=\tan\frac{x}{2}$, so "
                   r"$dx=\frac{2\,dt}{1+t^{2}}$, "
                   r"$\cos x=\frac{1-t^{2}}{1+t^{2}}$, and "
                   r"$\sin x=\frac{2t}{1+t^{2}}$, converting the integrand "
                   r"into a pure quadratic rational function of $t$!"),
            bullet(r"Algebraic Twin Integrals "
                   r"$\int\frac{x^{2}\pm1}{x^{4}+kx^{2}+1}\,dx$: Divide "
                   r"numerator and denominator by $x^{2}$ to obtain "
                   r"$\frac{1\pm1/x^{2}}{(x\mp1/x)^{2}+(k\pm2)}$, and "
                   r"substitute $u=x\mp\frac{1}{x}$ "
                   r"($du=\left(1\pm\frac{1}{x^{2}}\right)dx$)!"),
            bullet(r"Integration by Parts (ILATE Priority: Inverse, Log, "
                   r"Algebraic, Trig, Exponential): "
                   r"$\int u\,dv=uv-\int v\,du,\qquad "
                   r"\int e^{x}\left[f(x)+f'(x)\right]dx="
                   r"e^{x}f(x)+C.$"),
            theorem("7.1",
                    "King's Property, Leibniz Rule, Wallis' Formula & "
                    "First-Order Linear ODEs",
                    r"1. King's Property & Queen's Property of Definite "
                    r"Integrals:"),
            display(r"$\int_{a}^{b}f(x)\,dx=\int_{a}^{b}f(a+b-x)\,dx,"
                    r"\qquad \int_{0}^{2a}f(x)\,dx="
                    r"\int_{0}^{a}\left[f(x)+f(2a-x)\right]dx.$"),
            para(r"Proof of King's Property: Substitute $u=a+b-x$ "
                 r"($du=-dx$). At $x=a$, $u=b$; at $x=b$, $u=a$. Thus "
                 r"$\int_{a}^{b}f(x)\,dx=-\int_{b}^{a}f(a+b-u)\,du="
                 r"\int_{a}^{b}f(a+b-u)\,du.\quad\blacksquare$"),
            para(r"2. Newton-Leibniz Rule for Differentiating a Definite "
                 r"Integral with Variable Limits:"),
            display(r"$\frac{d}{dx}\left[\int_{\alpha(x)}^{\beta(x)}"
                    r"g(t)\,dt\right]=g(\beta(x))\beta'(x)-"
                    r"g(\alpha(x))\alpha'(x).$"),
            para(r"3. First-Order Linear Differential Equation "
                 r"$\frac{dy}{dx}+P(x)y=Q(x)$: Multiply both sides by the "
                 r"Integrating Factor $IF=e^{\int P(x)\,dx}$. By the "
                 r"product rule, the LHS becomes "
                 r"$\frac{d}{dx}\left[y\cdot e^{\int P(x)\,dx}\right]="
                 r"Q(x)e^{\int P(x)\,dx}$, giving the general solution:"),
            display(r"$y\cdot(IF)=\int Q(x)\cdot(IF)\,dx+C."
                    r"\quad\blacksquare$"),
        ],
        "1.2": [
            para(r"The Cartesian product of sets $A$ and $B$ is "
                 r"$A\times B=\{(a,b):a\in A,\ b\in B\}$. If "
                 r"$|A|=m$ and $|B|=n$, then $|A\times B|=mn$, and any "
                 r"subset $R\subseteq A\times B$ is a binary relation "
                 r"from $A$ to $B$. Hence there are $2^{mn}$ distinct "
                 r"relations from $A$ to $B$."),
            bullet(r"Classification of relations on a set $A$ with "
                   r"$|A|=n$. Represent $R\subseteq A\times A$ by its "
                   r"$n\times n$ adjacency matrix $M_{R}$, where "
                   r"$(M_{R})_{ij}=1$ iff $(a_{i},a_{j})\in R$:"),
            para(r"1. Reflexive: $(a,a)\in R$ for every $a\in A$. All "
                 r"$n$ diagonal entries of $M_{R}$ are $1$, while the "
                 r"remaining $n^{2}-n$ off-diagonal entries are free, "
                 r"giving $2^{n(n-1)}$ reflexive relations."),
            para(r"2. Symmetric: $(a,b)\in R\Rightarrow(b,a)\in R$, so "
                 r"$M_{R}=M_{R}^{T}$. The $n$ diagonal entries and the "
                 r"$\binom{n}{2}$ upper-triangular pairs are free, giving "
                 r"$2^{n(n+1)/2}$ symmetric relations."),
            para(r"3. Reflexive and symmetric: the diagonal is fixed to "
                 r"$1$ and the upper-triangular pairs are free, giving "
                 r"$2^{n(n-1)/2}$ relations."),
            para(r"4. Antisymmetric: $(a,b)\in R$ and $(b,a)\in R$ "
                 r"imply $a=b$. Each diagonal entry has $2$ choices, and "
                 r"each of the $\binom{n}{2}$ unordered off-diagonal "
                 r"pairs has $3$ valid states (neither, only $(i,j)$, or "
                 r"only $(j,i)$), giving "
                 r"$2^{n}3^{n(n-1)/2}$ antisymmetric relations."),
            para(r"5. Transitive: $(a,b)\in R$ and $(b,c)\in R$ imply "
                 r"$(a,c)\in R$."),
            bullet(r"Equivalence relation and equivalence classes: a "
                   r"relation $R$ on $A$ that is reflexive, symmetric, "
                   r"and transitive is an equivalence relation, written "
                   r"$a\sim b$. For each $a\in A$, its equivalence class "
                   r"is $[a]=\{x\in A:(x,a)\in R\}$."),
            bullet(r"Fundamental partition theorem: for any equivalence "
                   r"relation $\sim$ on $A$, two classes $[a]$ and $[b]$ "
                   r"are either identical (when $a\sim b$) or disjoint "
                   r"(when $a\nsim b$), and their union is all of $A$. "
                   r"The number of distinct equivalence relations on an "
                   r"$n$-element set is the Bell number $B_{n}$, with "
                   r"$B_{1}=1$, $B_{2}=2$, $B_{3}=5$, $B_{4}=15$, "
                   r"$B_{5}=52$, obeying "
                   r"$B_{n+1}=\sum_{k=0}^{n}\binom{n}{k}B_{k}$."),
            para(r"Classic exam trap: why a relation can be symmetric and "
                 r"transitive yet not reflexive. Students often try to "
                 r"prove reflexivity by writing "
                 r"$(a,b)\in R\Rightarrow(b,a)\in R\Rightarrow(a,a)\in R$. "
                 r"The flaw is that an element $a\in A$ may not be related "
                 r"to any $b\in A$ at all. For example, on $A=\{1,2,3\}$, "
                 r"the relation "
                 r"$R=\{(1,1),(1,2),(2,1),(2,2)\}$ is symmetric and "
                 r"transitive, yet $(3,3)\notin R$, so it is not "
                 r"reflexive."),
        ],
        "1.3": [
            para(r"A relation $f:A\to B$ is a function iff every "
                 r"$x\in A$ has exactly one image $f(x)\in B$."),
            bullet(r"Modulus (absolute value) function "
                   r"$f(x)=|x|$: defined piecewise as $x$ if $x\geq0$ and "
                   r"$-x$ if $x<0$. Key properties: $|xy|=|x||y|$, "
                   r"$\bigl||x|-|y|\bigr|\leq|x\pm y|\leq|x|+|y|$, "
                   r"$|x|\leq a\iff -a\leq x\leq a$ for $a\geq0$, and "
                   r"$|x|\geq a\iff x\leq-a$ or $x\geq a$."),
            bullet(r"Signum function "
                   r"$\operatorname{sgn}(x)=|x|/x$ for $x\neq0$, with "
                   r"$\operatorname{sgn}(0)=0$. Its domain is "
                   r"$\mathbb{R}$ and its range is $\{-1,0,1\}$."),
            bullet(r"Greatest integer (floor) function $\lfloor x\rfloor$ "
                   r"(also written $[x]$) and fractional part "
                   r"$\{x\}=x-\lfloor x\rfloor$: $\lfloor x\rfloor$ is the "
                   r"largest integer $\leq x$."),
            display(r"$\lfloor x+n\rfloor=\lfloor x\rfloor+n\ (n\in"
                    r"\mathbb{Z}),\qquad "
                    r"\lfloor x\rfloor+\lfloor-x\rfloor="
                    r"\begin{cases}0,&x\in\mathbb{Z},\\-1,&x\notin"
                    r"\mathbb{Z},\end{cases}\qquad \{x\}\in[0,1).$"),
            bullet(r"Master domain rules for a real function $f(x)$:"),
            para(r"1. Denominators must be non-zero: "
                 r"$\frac{1}{g(x)}$ requires $g(x)\neq0$."),
            para(r"2. Even-index radicals must be non-negative: "
                 r"$\sqrt{g(x)}$ requires $g(x)\geq0$, while "
                 r"$\frac{1}{\sqrt{g(x)}}$ requires $g(x)>0$."),
            para(r"3. Logarithms $\log_{b(x)}a(x)$ require argument "
                 r"$a(x)>0$, base $b(x)>0$, and $b(x)\neq1$."),
            para(r"4. Inverse sine and cosine, $\arcsin(g(x))$ and "
                 r"$\arccos(g(x))$, require $-1\leq g(x)\leq1$."),
            bullet(r"Master range algorithms:"),
            para(r"1. Quadratic $y=ax^{2}+bx+c$: complete the square as "
                 r"$y=a\left(x+\frac{b}{2a}\right)^{2}-\frac{D}{4a}$, "
                 r"where $D=b^{2}-4ac$. The range is "
                 r"$\left[-\frac{D}{4a},\infty\right)$ if $a>0$, and "
                 r"$\left(-\infty,-\frac{D}{4a}\right]$ if $a<0$."),
            para(r"2. Rational quadratic "
                 r"$y=\frac{a_{1}x^{2}+b_{1}x+c_{1}}"
                 r"{a_{2}x^{2}+b_{2}x+c_{2}}$: cross-multiply to obtain "
                 r"$(a_{2}y-a_{1})x^{2}+(b_{2}y-b_{1})x+(c_{2}y-c_{1})=0$. "
                 r"Since $x\in\mathbb{R}$, impose the discriminant "
                 r"condition $D(y)\geq0$ and solve for $y$, checking "
                 r"whether any common factor $(x-r)$ was cancelled."),
            para(r"3. Bounded trigonometric form "
                 r"$y=a\cos x+b\sin x+c$: the range is "
                 r"$\left[c-\sqrt{a^{2}+b^{2}},\ "
                 r"c+\sqrt{a^{2}+b^{2}}\right]$."),
        ],
        "3.2": [
            bullet(r"Arithmetic progression (AP): "
                   r"$T_{n}=a+(n-1)d$ and "
                   r"$S_{n}=\frac{n}{2}\left[2a+(n-1)d\right]="
                   r"\frac{n}{2}(a+l)$, where $l$ is the last term."),
            bullet(r"Geometric progression (GP): "
                   r"$T_{n}=ar^{n-1}$, "
                   r"$S_{n}=\frac{a(1-r^{n})}{1-r}$ for $r\neq1$, and "
                   r"$S_{\infty}=\frac{a}{1-r}$ for $|r|<1$."),
            bullet(r"Harmonic progression (HP): the reciprocals "
                   r"$\frac{1}{T_{n}}$ form an AP, so "
                   r"$T_{n}=\frac{1}{a+(n-1)d}$. There is no elementary "
                   r"closed form for a general HP sum."),
            bullet(r"Arithmetico-geometric progression (AGP): "
                   r"$S_{n}=\sum_{k=1}^{n}\left[a+(k-1)d\right]r^{k-1}$. "
                   r"Multiplying by $r$ and subtracting telescopes the "
                   r"series into:"),
            display(r"$S_{n}=\frac{a}{1-r}+"
                    r"\frac{dr(1-r^{n-1})}{(1-r)^{2}}-"
                    r"\frac{\left[a+(n-1)d\right]r^{n}}{1-r},$"),
            display(r"$S_{\infty}=\frac{a}{1-r}+"
                    r"\frac{dr}{(1-r)^{2}}\qquad(|r|<1).$"),
            bullet(r"Power sums and telescoping sums:"),
            display(r"$\sum_{k=1}^{n}k=\frac{n(n+1)}{2},\qquad "
                    r"\sum_{k=1}^{n}k^{2}=\frac{n(n+1)(2n+1)}{6},\qquad "
                    r"\sum_{k=1}^{n}k^{3}=\left[\frac{n(n+1)}{2}\right]^{2}.$"),
            bullet(r"AM-GM-HM inequality: for positive real numbers "
                   r"$x_{1},x_{2},\ldots,x_{n}>0$,"),
            display(r"$\mathrm{AM}=\frac{x_{1}+\cdots+x_{n}}{n}\geq"
                    r"\mathrm{GM}=(x_{1}x_{2}\cdots x_{n})^{1/n}\geq"
                    r"\mathrm{HM}=\frac{n}{\frac{1}{x_{1}}+\cdots+"
                    r"\frac{1}{x_{n}}},$"),
            para(r"with equality if and only if "
                 r"$x_{1}=x_{2}=\cdots=x_{n}$."),
        ],
        "3.1": [
            bullet(r"Weak and strong mathematical induction: to prove a "
                   r"statement $P(n)$ for all $n\geq n_{0}$, first verify "
                   r"the base case $P(n_{0})$. Then assume $P(k)$ holds "
                   r"(or, in strong induction, assume "
                   r"$P(n_{0}),\ldots,P(k)$ all hold) and deduce that "
                   r"$P(k+1)$ must hold."),
            bullet(r"Legendre's formula for the highest power of a prime "
                   r"$p$ dividing $n!$:"),
            display(r"$E_{p}(n!)=\left\lfloor\frac{n}{p}\right\rfloor+"
                    r"\left\lfloor\frac{n}{p^{2}}\right\rfloor+"
                    r"\left\lfloor\frac{n}{p^{3}}\right\rfloor+\cdots.$"),
            bullet(r"Permutations and combinations: the number of ordered "
                   r"$r$-arrangements from $n$ distinct items is "
                   r"$P(n,r)=\frac{n!}{(n-r)!}$, while the number of "
                   r"unordered $r$-selections is "
                   r"$\binom{n}{r}=\frac{n!}{r!(n-r)!}$."),
            para(r"1. Multiset permutations: if $n$ objects contain "
                 r"$n_{1}$ identical objects of type $1$, ..., $n_{k}$ "
                 r"identical objects of type $k$, the number of distinct "
                 r"permutations is "
                 r"$\frac{n!}{n_{1}!n_{2}!\cdots n_{k}!}$."),
            para(r"2. Circular permutations: there are $(n-1)!$ "
                 r"arrangements when clockwise and counterclockwise orders "
                 r"are distinct (for example, people around a table), and "
                 r"$\frac{(n-1)!}{2}$ when they are identified (for "
                 r"example, beads on a necklace)."),
            para(r"3. Stars and bars (beggar's method): the number of "
                 r"non-negative integer solutions of "
                 r"$x_{1}+x_{2}+\cdots+x_{r}=n$ is "
                 r"$\binom{n+r-1}{r-1}$; the number of strictly positive "
                 r"solutions ($x_{i}\geq1$) is "
                 r"$\binom{n-1}{r-1}$."),
            para(r"4. Derangements $D_{n}$ (permutations with no item in "
                 r"its original position): by inclusion-exclusion,"),
            display(r"$D_{n}=n!\sum_{k=0}^{n}\frac{(-1)^{k}}{k!}="
                    r"n!\left(1-\frac{1}{1!}+\frac{1}{2!}-"
                    r"\frac{1}{3!}+\cdots+\frac{(-1)^{n}}{n!}\right)"
                    r"\approx\frac{n!}{e}.$"),
            para(r"Specifically, $D_{1}=0$, $D_{2}=1$, $D_{3}=2$, "
                 r"$D_{4}=9$, $D_{5}=44$, and $D_{6}=265$."),
            theorem("3.1",
                    "Pascal's Identity, Vandermonde's Identity & "
                    "Binomial Theorem (With Proofs)",
                    r"1. Pascal's identity: "
                    r"$\binom{n}{r}+\binom{n}{r-1}=\binom{n+1}{r}$. "
                    r"Combinatorial proof: from $n+1$ people, including a "
                    r"specific person $X$, choosing a committee of size "
                    r"$r$ splits into two disjoint cases. Either $X$ is "
                    r"included, so the remaining $r-1$ members are chosen "
                    r"from $n$ people in $\binom{n}{r-1}$ ways, or $X$ is "
                    r"excluded, so all $r$ members are chosen from $n$ "
                    r"people in $\binom{n}{r}$ ways."),
            para(r"2. Binomial theorem for a positive integer $n$:"),
            display(r"$(x+y)^{n}=\sum_{r=0}^{n}\binom{n}{r}x^{n-r}y^{r},"
                    r"\qquad T_{r+1}=\binom{n}{r}x^{n-r}y^{r}.$"),
            para(r"3. Calculus and Vandermonde binomial-coefficient sums:"),
            display(r"$\sum_{r=0}^{n}\binom{n}{r}=2^{n},\qquad "
                    r"\sum_{r=0}^{n}(-1)^{r}\binom{n}{r}=0,\qquad "
                    r"\sum_{r=1}^{n}r\binom{n}{r}=n2^{n-1},\qquad "
                    r"\sum_{r=0}^{n}\binom{n}{r}^{2}=\binom{2n}{n}.$"),
            proof(r"Proof of $\sum_{r=1}^{n}r\binom{n}{r}=n2^{n-1}$",
                   r"Differentiate $(1+x)^{n}=\sum_{r=0}^{n}\binom{n}{r}"
                   r"x^{r}$ with respect to $x$ to obtain "
                   r"$n(1+x)^{n-1}=\sum_{r=1}^{n}r\binom{n}{r}"
                   r"x^{r-1}$, then evaluate at $x=1$. "
                   r"$\blacksquare$"),
        ],
        "6.1": [
            para(r"We write $\lim_{x\to a}f(x)=L$ if the left-hand limit "
                 r"$\mathrm{LHL}=\lim_{h\to0^{+}}f(a-h)$ and the "
                 r"right-hand limit $\mathrm{RHL}=\lim_{h\to0^{+}}f(a+h)$ "
                 r"both exist, are finite, and are equal: "
                 r"$\mathrm{LHL}=\mathrm{RHL}=L$."),
            theorem("6.1",
                    "Unit-Circle Sandwich Proof of sin x / x → 1 & "
                    "Master Taylor Expansions",
                    r"1. Geometric proof that "
                    r"$\lim_{x\to0}\frac{\sin x}{x}=1$ for $x$ in "
                    r"radians. For $x\in(0,\pi/2)$ on the unit circle, "
                    r"compare the area of $\triangle OAB$, which is "
                    r"$\frac{1}{2}\sin x$, the circular sector $OAB$, "
                    r"which is $\frac{1}{2}x$, and the right tangent "
                    r"triangle $\triangle OAT$, which is "
                    r"$\frac{1}{2}\tan x$:"),
            display(r"$\frac{1}{2}\sin x<\frac{1}{2}x<"
                    r"\frac{1}{2}\tan x\implies 1<"
                    r"\frac{x}{\sin x}<\frac{1}{\cos x}\implies "
                    r"\cos x<\frac{\sin x}{x}<1.$"),
            para(r"Since $\cos(-x)=\cos x$ and "
                 r"$\frac{\sin(-x)}{-x}=\frac{\sin x}{x}$, the inequality "
                 r"holds for all $x\in(-\pi/2,\pi/2)\setminus\{0\}$. "
                 r"Taking $x\to0$, and using $\lim_{x\to0}\cos x=1$, the "
                 r"squeeze theorem forces "
                 r"$\lim_{x\to0}\frac{\sin x}{x}=1$. Consequently:"),
            display(r"$\lim_{x\to0}\frac{1-\cos x}{x^{2}}="
                    r"\lim_{x\to0}\frac{2\sin^{2}(x/2)}{4(x/2)^{2}}="
                    r"\frac{1}{2},\qquad "
                    r"\lim_{x\to0}\frac{\tan x-x}{x^{3}}=\frac{1}{3},"
                    r"\qquad \lim_{x\to0}\frac{x-\sin x}{x^{3}}="
                    r"\frac{1}{6}.$"),
            para(r"2. Master Maclaurin series around $x=0$, the fastest "
                 r"tool for $0/0$ limits:"),
            display(r"$\begin{aligned} e^{x}&=1+x+\frac{x^{2}}{2!}+"
                    r"\frac{x^{3}}{3!}+\cdots, & "
                    r"\ln(1+x)&=x-\frac{x^{2}}{2}+\frac{x^{3}}{3}-"
                    r"\cdots,\\ \sin x&=x-\frac{x^{3}}{3!}+"
                    r"\frac{x^{5}}{5!}-\cdots, & "
                    r"\cos x&=1-\frac{x^{2}}{2!}+\frac{x^{4}}{4!}-"
                    r"\cdots,\\ \tan x&=x+\frac{x^{3}}{3}+"
                    r"\frac{2x^{5}}{15}+\cdots, & "
                    r"(1+x)^{n}&=1+nx+\frac{n(n-1)}{2}x^{2}+\cdots."
                    r"\end{aligned}$"),
            para(r"3. $1^{\infty}$ indeterminate-form shortcut: if "
                 r"$\lim_{x\to a}f(x)=1$ and $\lim_{x\to a}g(x)=\infty$, "
                 r"then"),
            display(r"$\lim_{x\to a}f(x)^{g(x)}=\exp\left(\lim_{x\to a}"
                    r"g(x)\left[f(x)-1\right]\right).$"),
        ],
        "8.1": [
            para(r"One radian is the angle subtended at the center of a "
                 r"circle of radius $r$ by an arc of length $r$: "
                 r"$\pi\ \mathrm{rad}=180^{\circ}$, arc length "
                 r"$s=r\theta$, and sector area "
                 r"$A=\frac{1}{2}r^{2}\theta=\frac{1}{2}rs$."),
            bullet(r"Pythagorean and reciprocal identities:"),
            display(r"$\sin^{2}\theta+\cos^{2}\theta=1,\qquad "
                    r"1+\tan^{2}\theta=\sec^{2}\theta,\qquad "
                    r"1+\cot^{2}\theta=\csc^{2}\theta,$"),
            display(r"$(\sec\theta-\tan\theta)(\sec\theta+\tan\theta)=1.$"),
            bullet(r"Compound-angle formulas:"),
            display(r"$\sin(A\pm B)=\sin A\cos B\pm\cos A\sin B,$"),
            display(r"$\cos(A\pm B)=\cos A\cos B\mp\sin A\sin B,\qquad "
                    r"\tan(A\pm B)=\frac{\tan A\pm\tan B}"
                    r"{1\mp\tan A\tan B}.$"),
            display(r"$\sin(A+B)\sin(A-B)=\sin^{2}A-\sin^{2}B="
                    r"\cos^{2}B-\cos^{2}A,$"),
            display(r"$\cos(A+B)\cos(A-B)=\cos^{2}A-\sin^{2}B.$"),
            bullet(r"Double, triple, and Weierstrass half-angle identities "
                   r"with $t=\tan(\theta/2)$:"),
            display(r"$\sin2\theta=2\sin\theta\cos\theta="
                    r"\frac{2t}{1+t^{2}},\qquad "
                    r"\cos2\theta=\cos^{2}\theta-\sin^{2}\theta="
                    r"2\cos^{2}\theta-1=1-2\sin^{2}\theta="
                    r"\frac{1-t^{2}}{1+t^{2}},$"),
            display(r"$\tan2\theta=\frac{2t}{1-t^{2}},$"),
            display(r"$\sin3\theta=3\sin\theta-4\sin^{3}\theta="
                    r"4\sin\theta\sin(60^{\circ}-\theta)"
                    r"\sin(60^{\circ}+\theta),$"),
            display(r"$\cos3\theta=4\cos^{3}\theta-3\cos\theta="
                    r"4\cos\theta\cos(60^{\circ}-\theta)"
                    r"\cos(60^{\circ}+\theta).$"),
            bullet(r"Product-to-sum and sum-to-product identities:"),
            display(r"$2\sin A\cos B=\sin(A+B)+\sin(A-B),$"),
            display(r"$2\cos A\cos B=\cos(A+B)+\cos(A-B),\qquad "
                    r"2\sin A\sin B=\cos(A-B)-\cos(A+B).$"),
            display(r"$\sin C\pm\sin D=2\sin\frac{C\pm D}{2}"
                    r"\cos\frac{C\mp D}{2},$"),
            display(r"$\cos C+\cos D=2\cos\frac{C+D}{2}"
                    r"\cos\frac{C-D}{2},\qquad "
                    r"\cos C-\cos D=-2\sin\frac{C+D}{2}"
                    r"\sin\frac{C-D}{2}.$"),
            theorem("8.1",
                    "Exact Golden-Ratio Value of sin 18°, Telescoping "
                    "Cosine Product & Triangle Identities",
                    r"1. Exact derivation of "
                    r"$\sin18^{\circ}=\frac{\sqrt{5}-1}{4}$ and "
                    r"$\cos36^{\circ}=\frac{\sqrt{5}+1}{4}$. Let "
                    r"$\theta=18^{\circ}$, so "
                    r"$5\theta=90^{\circ}$ and "
                    r"$2\theta=90^{\circ}-3\theta$. Taking sines of both "
                    r"sides gives "
                    r"$\sin2\theta=\cos3\theta$, hence "
                    r"$2\sin\theta\cos\theta="
                    r"4\cos^{3}\theta-3\cos\theta$."),
            para(r"Divide by $\cos\theta=\cos18^{\circ}\neq0$ and replace "
                 r"$\cos^{2}\theta=1-\sin^{2}\theta$:"),
            display(r"$2\sin\theta=4(1-\sin^{2}\theta)-3\implies "
                    r"4\sin^{2}\theta+2\sin\theta-1=0$"),
            display(r"$\implies \sin18^{\circ}="
                    r"\frac{-2+\sqrt{4+16}}{8}="
                    r"\frac{\sqrt{5}-1}{4}>0.$"),
            para(r"Then "
                 r"$\cos36^{\circ}=1-2\sin^{2}18^{\circ}="
                 r"1-2\left(\frac{6-2\sqrt{5}}{16}\right)="
                 r"\frac{\sqrt{5}+1}{4}$. $\blacksquare$"),
            para(r"2. Telescoping dyadic cosine product: multiplying and "
                 r"dividing by $2^{n}\sin\theta$ repeatedly applies "
                 r"$2\sin(2^{k}\theta)\cos(2^{k}\theta)="
                 r"\sin(2^{k+1}\theta)$, giving"),
            display(r"$\prod_{k=0}^{n-1}\cos(2^{k}\theta)="
                    r"\cos\theta\cos2\theta\cos4\theta\cdots"
                    r"\cos(2^{n-1}\theta)=\frac{\sin(2^{n}\theta)}"
                    r"{2^{n}\sin\theta}.$"),
            para(r"3. Conditional identities in $\triangle ABC$ with "
                 r"$A+B+C=\pi$, and the sine, cosine, and Napier laws:"),
            display(r"$\tan A+\tan B+\tan C=\tan A\tan B\tan C,$"),
            display(r"$\sin2A+\sin2B+\sin2C="
                    r"4\sin A\sin B\sin C,$"),
            display(r"$\frac{a}{\sin A}=\frac{b}{\sin B}="
                    r"\frac{c}{\sin C}=2R,\qquad "
                    r"\cos A=\frac{b^{2}+c^{2}-a^{2}}{2bc},$"),
            display(r"$\Delta=\sqrt{s(s-a)(s-b)(s-c)}=rs="
                    r"\frac{abc}{4R}.$"),
        ],
        "8.2": [
            bullet(r"General solutions of trigonometric equations, with "
                   r"$n\in\mathbb{Z}$:"),
            display(r"$\sin\theta=\sin\alpha\iff "
                    r"\theta=n\pi+(-1)^{n}\alpha,\qquad "
                    r"\cos\theta=\cos\alpha\iff "
                    r"\theta=2n\pi\pm\alpha,$"),
            display(r"$\tan\theta=\tan\alpha\iff \theta=n\pi+\alpha,$"),
            display(r"$\sin^{2}\theta=\sin^{2}\alpha\iff "
                    r"\cos^{2}\theta=\cos^{2}\alpha\iff "
                    r"\tan^{2}\theta=\tan^{2}\alpha\iff "
                    r"\theta=n\pi\pm\alpha.$"),
            bullet(r"Principal-value branches and identities of inverse "
                   r"trigonometric functions:"),
            para(r"1. $\arcsin:[-1,1]\to\left[-\frac{\pi}{2},"
                 r"\frac{\pi}{2}\right]$, "
                 r"$\arctan:\mathbb{R}\to\left(-\frac{\pi}{2},"
                 r"\frac{\pi}{2}\right)$, and "
                 r"$\operatorname{arccsc}:(-\infty,-1]\cup[1,\infty)\to"
                 r"\left[-\frac{\pi}{2},\frac{\pi}{2}\right]\setminus"
                 r"\{0\}$ are odd: $f(-x)=-f(x)$."),
            para(r"2. $\arccos:[-1,1]\to[0,\pi]$, "
                 r"$\operatorname{arccot}:\mathbb{R}\to(0,\pi)$, and "
                 r"$\operatorname{arcsec}:(-\infty,-1]\cup[1,\infty)\to"
                 r"[0,\pi]\setminus\left\{\frac{\pi}{2}\right\}$ obey the "
                 r"$\pi$-symmetry $f(-x)=\pi-f(x)$."),
            para(r"3. Complementary-sum identities:"),
            display(r"$\arcsin x+\arccos x=\frac{\pi}{2},\qquad "
                    r"\arctan x+\operatorname{arccot}x=\frac{\pi}{2},"
                    r"\qquad \operatorname{arcsec}x+"
                    r"\operatorname{arccsc}x=\frac{\pi}{2}.$"),
            para(r"4. Complete piecewise formula for "
                 r"$\arctan x+\arctan y$ with $x,y>0$:"),
            display(r"$\arctan x+\arctan y=\begin{cases}"
                    r"\arctan\left(\frac{x+y}{1-xy}\right),&xy<1,\\[4pt]"
                    r"\frac{\pi}{2},&xy=1,\\[4pt]"
                    r"\pi+\arctan\left(\frac{x+y}{1-xy}\right),&xy>1,"
                    r"\end{cases}$"),
            display(r"$\arctan x-\arctan y="
                    r"\arctan\left(\frac{x-y}{1+xy}\right).$"),
            para(r"5. Double-angle inverse trigonometric formulas:"),
            display(r"$2\arctan x=\arctan\left(\frac{2x}{1-x^{2}}\right)"
                    r"\ (|x|<1)=\arcsin\left(\frac{2x}{1+x^{2}}\right)"
                    r"\ (|x|\leq1)=\arccos\left(\frac{1-x^{2}}{1+x^{2}}"
                    r"\right)\ (x\geq0).$"),
        ],
        "9.1": [
            para(r"For $\vec r=x\hat i+y\hat j+z\hat k$, the magnitude is "
                 r"$|\vec r|=\sqrt{x^{2}+y^{2}+z^{2}}$, and the direction "
                 r"cosines "
                 r"$l=\cos\alpha=\frac{x}{|\vec r|}$, "
                 r"$m=\cos\beta=\frac{y}{|\vec r|}$, "
                 r"$n=\cos\gamma=\frac{z}{|\vec r|}$ satisfy:"),
            display(r"$l^{2}+m^{2}+n^{2}=1\iff \cos^{2}\alpha+"
                    r"\cos^{2}\beta+\cos^{2}\gamma=1\iff "
                    r"\sin^{2}\alpha+\sin^{2}\beta+\sin^{2}\gamma=2.$"),
            bullet(r"Dot (scalar) product and projection: "
                   r"$\vec a\cdot\vec b=|\vec a||\vec b|\cos\theta="
                   r"a_{1}b_{1}+a_{2}b_{2}+a_{3}b_{3}$. The scalar "
                   r"projection of $\vec a$ on $\vec b$ is "
                   r"$\frac{\vec a\cdot\vec b}{|\vec b|}$, and the vector "
                   r"projection is "
                   r"$\frac{\vec a\cdot\vec b}{|\vec b|^{2}}\vec b$."),
            bullet(r"Cross (vector) product and Lagrange's identity:"),
            display(r"$\vec a\times\vec b=|\vec a||\vec b|\sin\theta\,"
                    r"\hat n=\begin{vmatrix}\hat i&\hat j&\hat k\\"
                    r"a_{1}&a_{2}&a_{3}\\b_{1}&b_{2}&b_{3}"
                    r"\end{vmatrix}.$"),
            display(r"$|\vec a\times\vec b|^{2}+(\vec a\cdot\vec b)^{2}="
                    r"|\vec a|^{2}|\vec b|^{2},\qquad "
                    r"\operatorname{Area}(\triangle ABC)=\frac{1}{2}"
                    r"\left|\overrightarrow{AB}\times"
                    r"\overrightarrow{AC}\right|.$"),
            bullet(r"Scalar triple product "
                   r"$[\vec a\ \vec b\ \vec c]=\vec a\cdot(\vec b\times"
                   r"\vec c)$ and vector triple product (BAC-CAB rule):"),
            display(r"$V_{\text{parallelepiped}}="
                    r"\left|[\vec a\ \vec b\ \vec c]\right|,\qquad "
                    r"V_{\text{tetrahedron}}=\frac{1}{6}"
                    r"\left|[\vec a\ \vec b\ \vec c]\right|,$"),
            display(r"$\vec a\times(\vec b\times\vec c)="
                    r"(\vec a\cdot\vec c)\vec b-"
                    r"(\vec a\cdot\vec b)\vec c.$"),
            theorem("9.1",
                    "Shortest Distance Between Skew Lines in 3D & Plane "
                    "Projection Formulas",
                    r"1. Complete derivation of the shortest distance "
                    r"between the skew lines "
                    r"$\vec r=\vec a_{1}+\lambda\vec b_{1}$ and "
                    r"$\vec r=\vec a_{2}+\mu\vec b_{2}$. The line of "
                    r"shortest distance is perpendicular to both direction "
                    r"vectors, so its unit direction is "
                    r"$\hat n=\frac{\vec b_{1}\times\vec b_{2}}"
                    r"{|\vec b_{1}\times\vec b_{2}|}$. Projecting the "
                    r"connecting vector $\vec a_{2}-\vec a_{1}$ onto "
                    r"$\hat n$ gives"),
            display(r"$d_{\text{skew}}=\left|(\vec a_{2}-\vec a_{1})"
                    r"\cdot\hat n\right|="
                    r"\frac{\left|(\vec a_{2}-\vec a_{1})\cdot"
                    r"(\vec b_{1}\times\vec b_{2})\right|}"
                    r"{|\vec b_{1}\times\vec b_{2}|}.$"),
            para(r"The two 3D lines intersect (are coplanar) iff "
                 r"$(\vec a_{2}-\vec a_{1})\cdot(\vec b_{1}\times"
                 r"\vec b_{2})=0$."),
            para(r"2. 3D plane equations, distance, foot of perpendicular "
                 r"$M$, and mirror image $Q$. For the plane "
                 r"$ax+by+cz+d=0$ and point $P(x_{1},y_{1},z_{1})$:"),
            display(r"$d(P,\Pi)=\frac{|ax_{1}+by_{1}+cz_{1}+d|}"
                    r"{\sqrt{a^{2}+b^{2}+c^{2}}},$"),
            display(r"$\frac{h-x_{1}}{a}=\frac{k-y_{1}}{b}="
                    r"\frac{l-z_{1}}{c}="
                    r"-\frac{ax_{1}+by_{1}+cz_{1}+d}{a^{2}+b^{2}+c^{2}}.$"),
            para(r"For the mirror image $Q(x',y',z')$, double the "
                 r"right-hand side of the foot-of-perpendicular formula."),
        ],
        "10.1": [
            bullet(r"Mean deviation about the mean $\bar x$ or median "
                   r"$M$:"),
            display(r"$\mathrm{MD}=\frac{1}{N}\sum_{i=1}^{n}"
                    r"f_{i}|x_{i}-A|,\qquad A=\bar x\ \text{or}\ M,"
                    r"\qquad N=\sum_{i=1}^{n}f_{i}.$"),
            para(r"Note that $\sum|x_{i}-A|$ is minimized when $A$ is the "
                 r"median, whereas $\sum(x_{i}-A)^{2}$ is minimized when "
                 r"$A=\bar x$."),
            bullet(r"Population variance $\sigma^{2}$, standard deviation "
                   r"$\sigma$, and coefficient of variation "
                   r"$\mathrm{CV}$:"),
            display(r"$\sigma^{2}=\frac{1}{N}\sum_{i=1}^{n}"
                    r"f_{i}(x_{i}-\bar x)^{2}="
                    r"\frac{1}{N}\sum_{i=1}^{n}f_{i}x_{i}^{2}-"
                    r"\bar x^{2},\qquad "
                    r"\mathrm{CV}=\frac{\sigma}{\bar x}\times100\%.$"),
            bullet(r"Effect of a linear change of origin and scale: if "
                   r"$y_{i}=ax_{i}+b$, then "
                   r"$\bar y=a\bar x+b$, "
                   r"$\sigma_{Y}^{2}=a^{2}\sigma_{X}^{2}$, and "
                   r"$\sigma_{Y}=|a|\sigma_{X}$. Adding a constant shift "
                   r"$b$ has zero effect on variance."),
            bullet(r"Combined (pooled) mean and variance of two groups "
                   r"$(n_{1},\bar x_{1},\sigma_{1}^{2})$ and "
                   r"$(n_{2},\bar x_{2},\sigma_{2}^{2})$:"),
            display(r"$\bar x_{12}=\frac{n_{1}\bar x_{1}+"
                    r"n_{2}\bar x_{2}}{n_{1}+n_{2}},\qquad "
                    r"\sigma_{12}^{2}=\frac{n_{1}(\sigma_{1}^{2}+"
                    r"d_{1}^{2})+n_{2}(\sigma_{2}^{2}+d_{2}^{2})}"
                    r"{n_{1}+n_{2}},$"),
            display(r"$d_{i}=\bar x_{i}-\bar x_{12}.$"),
            theorem("10.1",
                    "Conditional Probability, Independence, Law of Total "
                    "Probability & Bayes' Theorem",
                    r"1. Conditional probability and the multiplication "
                    r"rule: for events $A,B$ with $P(B)>0$,"),
            display(r"$P(A\mid B)=\frac{P(A\cap B)}{P(B)}"
                    r"\implies P(A\cap B)=P(B)P(A\mid B)="
                    r"P(A)P(B\mid A).$"),
            para(r"2. Independent events: $A$ and $B$ are independent iff "
                 r"$P(A\cap B)=P(A)P(B)$. If $A\perp B$, then "
                 r"$A\perp B^{c}$, $A^{c}\perp B$, and "
                 r"$A^{c}\perp B^{c}$:"),
            display(r"$P(A^{c}\cap B^{c})=1-P(A\cup B)="
                    r"1-P(A)-P(B)+P(A)P(B)="
                    r"(1-P(A))(1-P(B))=P(A^{c})P(B^{c}).$"),
            para(r"3. Law of total probability and Bayes' theorem: let "
                 r"$\{E_{1},E_{2},\ldots,E_{n}\}$ be a partition of the "
                 r"sample space $\Omega$, so "
                 r"$E_{i}\cap E_{j}=\varnothing$ for $i\neq j$, "
                 r"$\bigcup_{i=1}^{n}E_{i}=\Omega$, and "
                 r"$P(E_{i})>0$. For any observable event $A$ with "
                 r"$P(A)>0$:"),
            display(r"$P(A)=\sum_{j=1}^{n}P(E_{j})P(A\mid E_{j}),$"),
            display(r"$P(E_{k}\mid A)=\frac{P(E_{k})P(A\mid E_{k})}"
                    r"{\sum_{j=1}^{n}P(E_{j})P(A\mid E_{j})}.$"),
            para(r"4. Binomial distribution $X\sim\mathrm{Bin}(n,p)$ with "
                 r"$q=1-p$:"),
            display(r"$P(X=r)=\binom{n}{r}p^{r}q^{n-r}\quad"
                    r"(r=0,1,\ldots,n),\qquad "
                    r"\mathbb{E}[X]=np,\qquad "
                    r"\operatorname{Var}(X)=npq.$"),
        ],
        "11.2": [
            bullet(r"Geometric and arithmetico-geometric series: "
                   r"multiplying $S_{n}=\sum_{k=0}^{n-1}ar^{k}$ by "
                   r"$(1-r)$ telescopes the sum into"),
            display(r"$\sum_{k=0}^{n-1}ar^{k}=\frac{a(1-r^{n})}{1-r}"
                    r"\quad(r\neq1),\qquad "
                    r"\sum_{k=0}^{\infty}ar^{k}=\frac{a}{1-r}"
                    r"\quad(|r|<1),$"),
            display(r"$\sum_{k=1}^{\infty}kr^{k}="
                    r"\frac{r}{(1-r)^{2}}\quad(|r|<1).$"),
            bullet(r"AM-GM inequality (volatility drag): since "
                   r"$(\sqrt{x}-\sqrt{y})^{2}\geq0$, we have "
                   r"$\frac{x+y}{2}\geq\sqrt{xy}$. In finance, a $+50\%$ "
                   r"gain (multiply by $1.5$) followed by a $-50\%$ loss "
                   r"(multiply by $0.5$) has arithmetic average $0\%$, "
                   r"but compounded wealth $1.5\times0.5=0.75$, a "
                   r"$-25\%$ volatility drag."),
            bullet(r"Cauchy-Schwarz inequality: for any vectors "
                   r"$u,v\in\mathbb{R}^{n}$, "
                   r"$|\langle u,v\rangle|\leq\|u\|_{2}\|v\|_{2}$, "
                   r"which guarantees that the cosine similarity "
                   r"$\cos\theta=\frac{u^{T}v}{\|u\|_{2}\|v\|_{2}}$ lies "
                   r"in $[-1,1]$."),
            bullet(r"Convexity and Jensen's inequality: for any convex "
                   r"function $f$ with $f''(x)\geq0$, the expected output "
                   r"is at least the function of the expected input:"),
            display(r"$\mathbb{E}\left[f(X)\right]\geq "
                    r"f\left(\mathbb{E}[X]\right).$"),
            bullet(r"Euler's formula and discrete Fourier roots of unity: "
                   r"power-series expansion gives Euler's formula"),
            display(r"$e^{i\theta}=\cos\theta+i\sin\theta,\qquad "
                    r"\left(e^{i\theta}\right)^{n}="
                    r"\cos(n\theta)+i\sin(n\theta),$"),
            display(r"$\sum_{k=0}^{N-1}e^{i2\pi mk/N}=0"
                    r"\quad(m\not\equiv0\pmod N).$"),
        ],
        "12.1": [
            bullet(r"Taylor's formula with exact Lagrange remainder: every "
                   r"smooth function can be approximated locally by a "
                   r"polynomial whose error is governed by the "
                   r"$(n+1)$-th derivative at an intermediate point "
                   r"$\xi$:"),
            display(r"$f(x)=\sum_{k=0}^{n}\frac{f^{(k)}(a)}{k!}"
                    r"(x-a)^{k}+\frac{f^{(n+1)}(\xi)}{(n+1)!}"
                    r"(x-a)^{n+1}.$"),
            para(r"Four essential Maclaurin series around $x=0$:"),
            display(r"$e^{x}=1+x+\frac{x^{2}}{2!}+"
                    r"\frac{x^{3}}{3!}+\cdots,\qquad "
                    r"\ln(1+x)=x-\frac{x^{2}}{2}+"
                    r"\frac{x^{3}}{3}-\cdots,$"),
            display(r"$(1+x)^{\alpha}=1+\alpha x+"
                    r"\frac{\alpha(\alpha-1)}{2}x^{2}+\cdots.$"),
            bullet(r"Polar proof of the Gaussian integral "
                   r"$I=\int_{-\infty}^{\infty}e^{-x^{2}}dx=\sqrt{\pi}$: "
                   r"square the integral into $\mathbb{R}^{2}$ with "
                   r"$x^{2}+y^{2}=r^{2}$ and $dx\,dy=r\,dr\,d\theta$:"),
            display(r"$I^{2}=\iint_{\mathbb{R}^{2}}"
                    r"e^{-(x^{2}+y^{2})}dx\,dy="
                    r"\int_{0}^{2\pi}\int_{0}^{\infty}"
                    r"re^{-r^{2}}dr\,d\theta="
                    r"2\pi\left[-\frac{1}{2}e^{-r^{2}}\right]_{0}^{\infty}"
                    r"=\pi,$"),
            display(r"$\implies I=\int_{-\infty}^{\infty}e^{-x^{2}}dx="
                    r"\sqrt{\pi}.$"),
            bullet(r"Leibniz's rule (differentiating under the integral "
                   r"sign):"),
            display(r"$\frac{d}{d\theta}\int_{a(\theta)}^{b(\theta)}"
                    r"f(x,\theta)\,dx=f(b(\theta),\theta)b'(\theta)-"
                    r"f(a(\theta),\theta)a'(\theta)+"
                    r"\int_{a(\theta)}^{b(\theta)}"
                    r"\frac{\partial f(x,\theta)}{\partial\theta}\,dx.$"),
        ],
        "13.1": [
            para(r"The $\frac{\sqrt{0}}{2},\frac{\sqrt{1}}{2},"
                 r"\frac{\sqrt{2}}{2},\frac{\sqrt{3}}{2},"
                 r"\frac{\sqrt{4}}{2}$ benchmark table: at "
                 r"$0,\frac{\pi}{6}(30^{\circ}),\frac{\pi}{4}(45^{\circ}),"
                 r"\frac{\pi}{3}(60^{\circ}),\frac{\pi}{2}(90^{\circ})$, "
                 r"$\sin\theta$ counts up "
                 r"$\frac{\sqrt{0}}{2}=0,\frac{1}{2},"
                 r"\frac{\sqrt{2}}{2},\frac{\sqrt{3}}{2},1$, while "
                 r"$\cos\theta$ counts down in reverse."),
            para(r"Deriving all addition, double-angle, and "
                 r"power-reduction identities from "
                 r"$e^{i(\alpha+\beta)}=e^{i\alpha}e^{i\beta}$:"),
            display(r"$\cos(\alpha\pm\beta)=\cos\alpha\cos\beta\mp"
                    r"\sin\alpha\sin\beta,\qquad "
                    r"\sin(\alpha\pm\beta)=\sin\alpha\cos\beta\pm"
                    r"\cos\alpha\sin\beta.$"),
            para(r"Setting $\beta=\alpha$ yields "
                 r"$\cos2\alpha=\cos^{2}\alpha-\sin^{2}\alpha="
                 r"2\cos^{2}\alpha-1=1-2\sin^{2}\alpha$ and "
                 r"$\sin2\alpha=2\sin\alpha\cos\alpha$, which invert "
                 r"into the power-reduction formulas:"),
            display(r"$\cos^{2}\alpha=\frac{1+\cos2\alpha}{2},\qquad "
                    r"\sin^{2}\alpha=\frac{1-\cos2\alpha}{2}.$"),
            para(r"Inverse trigonometric derivatives:"),
            display(r"$\frac{d}{dx}\arcsin x=\frac{1}{\sqrt{1-x^{2}}},"
                    r"\qquad \frac{d}{dx}\arccos x="
                    r"-\frac{1}{\sqrt{1-x^{2}}},\qquad "
                    r"\frac{d}{dx}\arctan x=\frac{1}{1+x^{2}}.$"),
            para(r"Fourier series orthogonality on $[-\pi,\pi]$:"),
            display(r"$\int_{-\pi}^{\pi}\cos(mx)\cos(nx)\,dx="
                    r"\pi\delta_{mn},\qquad "
                    r"\int_{-\pi}^{\pi}\sin(mx)\sin(nx)\,dx="
                    r"\pi\delta_{mn},$"),
            display(r"$\int_{-\pi}^{\pi}\sin(mx)\cos(nx)\,dx=0.$"),
        ],
        "14.2": [
            para(r"1. Courant-Fischer min-max variational "
                 r"characterization of eigenvalues: for any symmetric "
                 r"matrix $A\in\mathbb{R}^{n\times n}$ with eigenvalues "
                 r"$\lambda_{1}\geq\lambda_{2}\geq\cdots\geq\lambda_{n}$, "
                 r"the $k$-th eigenvalue is characterized without "
                 r"reference to the characteristic polynomial by"),
            display(r"$\lambda_{k}(A)=\max_{\dim(U)=k}\ "
                    r"\min_{x\in U\setminus\{0\}}"
                    r"\frac{x^{T}Ax}{x^{T}x}="
                    r"\min_{\dim(V)=n-k+1}\ "
                    r"\max_{x\in V\setminus\{0\}}"
                    r"\frac{x^{T}Ax}{x^{T}x}.$"),
            para(r"This immediately proves Cauchy's interlacing theorem "
                 r"for principal submatrices and Weyl's monotonicity "
                 r"theorem "
                 r"$\lambda_{k}(A+B)\geq\lambda_{k}(A)+"
                 r"\lambda_{\min}(B)$."),
            para(r"2. First-principles proof of "
                 r"$\nabla_{X}\ln\det(X)=X^{-T}$: using the first-order "
                 r"determinant expansion "
                 r"$\det(I+E)=1+\operatorname{Tr}(E)+o(\|E\|)$, perturb "
                 r"$X\succ0$ by $\Delta X$:"),
            display(r"$\ln\det(X+\Delta X)-\ln\det(X)="
                    r"\ln\det\left(I+X^{-1}\Delta X\right)="
                    r"\operatorname{Tr}\left(X^{-1}\Delta X\right)+"
                    r"o(\|\Delta X\|),$"),
            display(r"$=\left\langle X^{-T},\Delta X\right\rangle_{F}+"
                    r"o(\|\Delta X\|)\implies "
                    r"\nabla_{X}\ln\det(X)=X^{-T}.$"),
        ],
        "11.1": [
            para(r"In machine learning, a binary classifier outputs a raw "
                 r"real score (logit) $z\in(-\infty,\infty)$ and maps it "
                 r"smoothly into a probability $p\in(0,1)$ via the logistic "
                 r"sigmoid bijection:"),
            display(r"$p=\sigma(z)=\frac{1}{1+e^{-z}}"
                    r"\quad\Longleftrightarrow\quad "
                    r"z=\sigma^{-1}(p)=\ln\left(\frac{p}{1-p}\right),$"),
            para(r"where $\sigma^{-1}(p)$ is the logit, or log-odds. "
                 r"Notice the symmetry identity:"),
            display(r"$1-\sigma(z)=\frac{e^{-z}}{1+e^{-z}}="
                    r"\sigma(-z).$"),
            para(r"Why naive softmax overflows and how the log-sum-exp "
                 r"(LSE) trick fixes it: when evaluating "
                 r"$\mathrm{LSE}(z_{1},\ldots,z_{K})="
                 r"\ln\left(\sum_{j=1}^{K}e^{z_{j}}\right)$ for large "
                 r"logits such as $z=[1000,1001,999]$, computing "
                 r"$e^{1001}$ directly overflows 64-bit floating-point "
                 r"arithmetic ($>10^{308}$). Factoring out the maximum "
                 r"logit $c=\max_{j}z_{j}$ shifts every exponent to "
                 r"$z_{j}-c\leq0$:"),
            display(r"$\mathrm{LSE}(z_{1},\ldots,z_{K})="
                    r"\ln\left(e^{c}\sum_{j=1}^{K}e^{z_{j}-c}\right)="
                    r"c+\ln\left(\sum_{j=1}^{K}e^{z_{j}-c}\right),"
                    r"\qquad c=\max_{1\leq j\leq K}z_{j}.$"),
        ],
        "14.1": [
            bullet(r"Orthogonal projection and ordinary least squares "
                   r"(OLS): minimizing $\|Xw-y\|_{2}^{2}$ projects $y$ "
                   r"orthogonally onto the column space $C(X)$, so the "
                   r"residual $y-X\hat w$ is orthogonal to $C(X)$:"),
            display(r"$X^{T}(y-X\hat w)=0\implies "
                    r"\hat w=(X^{T}X)^{-1}X^{T}y,\qquad "
                    r"\hat y=Py=X(X^{T}X)^{-1}X^{T}y.$"),
            bullet(r"The 5-second $2\times2$ eigenvalue formula and the "
                   r"spectral theorem: for any $2\times2$ matrix $A$, "
                   r"$\lambda^{2}-\operatorname{tr}(A)\lambda+\det(A)=0$. "
                   r"Every real symmetric matrix $S=S^{T}$ has real "
                   r"eigenvalues and orthonormal eigenvectors $Q$:"),
            display(r"$S=Q\Lambda Q^{T}=\sum_{i=1}^{n}"
                    r"\lambda_{i}q_{i}q_{i}^{T}.$"),
            bullet(r"SVD and the Eckart-Young low-rank approximation: "
                   r"every matrix $A\in\mathbb{R}^{m\times n}$ factors as "
                   r"$A=U\Sigma V^{T}=\sum_{i=1}^{r}\sigma_{i}"
                   r"u_{i}v_{i}^{T}$, and the best rank-$k$ approximation "
                   r"$A_{k}=\sum_{i=1}^{k}\sigma_{i}u_{i}v_{i}^{T}$ has "
                   r"Frobenius error"),
            display(r"$\|A-A_{k}\|_{F}=\left(\sum_{i=k+1}^{r}"
                    r"\sigma_{i}^{2}\right)^{1/2}.$"),
            bullet(r"Positive definite matrices, Cholesky "
                   r"($\Sigma=LL^{T}$), and matrix calculus:"),
            display(r"$\nabla_{x}(a^{T}x)=a,\qquad "
                    r"\nabla_{x}(x^{T}\Sigma x)=2\Sigma x"
                    r"\ (\Sigma=\Sigma^{T}),$"),
            display(r"$\nabla_{W}\operatorname{tr}(A^{T}W)=A,\qquad "
                    r"\nabla_{\Sigma}\ln\det(\Sigma)=\Sigma^{-1}.$"),
        ],
        "4.1": [
            bullet(r"Matrix multiplication and transpose: for "
                   r"$A\in\mathbb{R}^{m\times n}$ and "
                   r"$B\in\mathbb{R}^{n\times p}$, "
                   r"$(AB)_{ij}=\sum_{k=1}^{n}A_{ik}B_{kj}$. Generally "
                   r"$AB\neq BA$, $(AB)^{T}=B^{T}A^{T}$, and "
                   r"$\operatorname{Tr}(AB)="
                   r"\operatorname{Tr}(BA)="
                   r"\sum_{i,k}A_{ik}B_{ki}$."),
            bullet(r"Gallery of special square matrices:"),
            para(r"1. Symmetric ($A^{T}=A$) and skew-symmetric "
                 r"($A^{T}=-A$): every diagonal entry of a skew-symmetric "
                 r"matrix is zero ($a_{ii}=-a_{ii}\implies a_{ii}=0$)."),
            para(r"2. Idempotent (projection): $A^{2}=A$ (eigenvalues in "
                 r"$\{0,1\}$, $\det A\in\{0,1\}$)."),
            para(r"3. Involutory (reflection): $A^{2}=I\iff A^{-1}=A$ "
                 r"($\det A=\pm1$)."),
            para(r"4. Nilpotent: $A^{k}=0$ for some integer $k\geq1$ "
                 r"($\det A=0$, $\operatorname{Tr}(A)=0$, and $I-A$ is "
                 r"always invertible with "
                 r"$(I-A)^{-1}=I+A+A^{2}+\cdots+A^{k-1}$)."),
            para(r"5. Orthogonal: $A^{T}A=AA^{T}=I\iff A^{-1}=A^{T}$ "
                 r"($\det A=\pm1$; preserves lengths "
                 r"$\|Ax\|_{2}=\|x\|_{2}$)."),
            theorem("4.1",
                    "Unique Symmetric/Skew-Symmetric Split, Adjoint "
                    "Master Identity & System Consistency",
                    r"1. Unique decomposition of any square matrix $A$: "
                    r"every $A\in\mathbb{R}^{n\times n}$ is uniquely "
                    r"expressible as $A=P+Q$, where "
                    r"$P=\frac{1}{2}(A+A^{T})$ is symmetric and "
                    r"$Q=\frac{1}{2}(A-A^{T})$ is skew-symmetric."),
            proof(r"Proof of uniqueness",
                  r"If $A=P_{1}+Q_{1}$ with $P_{1}^{T}=P_{1}$ and "
                  r"$Q_{1}^{T}=-Q_{1}$, taking transposes gives "
                  r"$A^{T}=P_{1}-Q_{1}$. Adding and subtracting yields "
                  r"$P_{1}=\frac{1}{2}(A+A^{T})$ and "
                  r"$Q_{1}=\frac{1}{2}(A-A^{T})$. $\blacksquare$"),
            para(r"2. Fundamental adjoint theorem (order $n$): let "
                 r"$C_{ij}=(-1)^{i+j}M_{ij}$ be the cofactor of $a_{ij}$ "
                 r"and $\operatorname{adj}(A)=[C_{ij}]^{T}$. Since "
                 r"$\sum_{k=1}^{n}a_{ik}C_{jk}=(\det A)\delta_{ij}$ "
                 r"(expanding by alien cofactors gives a determinant with "
                 r"two identical rows, hence $0$), we obtain the master "
                 r"identity"),
            display(r"$A\operatorname{adj}(A)="
                    r"\operatorname{adj}(A)A=|A|I_{n}.$"),
            para(r"Taking determinants of both sides of "
                 r"$A\operatorname{adj}(A)=|A|I_{n}$ (using "
                 r"$|kI_{n}|=k^{n}$) proves"),
            display(r"$|A|\cdot|\operatorname{adj}(A)|=|A|^{n}\implies "
                    r"|\operatorname{adj}(A)|=|A|^{n-1},\qquad "
                    r"|\operatorname{adj}(\operatorname{adj}(A))|="
                    r"|A|^{(n-1)^{2}}.$"),
            display(r"$\operatorname{adj}(A)=|A|A^{-1},\qquad "
                    r"\operatorname{adj}(\operatorname{adj}(A))="
                    r"|A|^{n-2}A.$"),
            para(r"3. Consistency of linear systems $Ax=b$ (matrix and "
                 r"Cramer's method):"),
            para(r"Case 1 ($|A|\neq0$): unique solution "
                 r"$x=A^{-1}b$, or by Cramer's rule "
                 r"$x_{j}=\frac{\Delta_{j}}{\Delta}$."),
            para(r"Case 2 ($|A|=0$ and $(\operatorname{adj}A)b\neq0$, "
                 r"i.e., some $\Delta_{j}\neq0$): inconsistent, no "
                 r"solution."),
            para(r"Case 3 ($|A|=0$ and $(\operatorname{adj}A)b=0$ and "
                 r"$\operatorname{rank}(A)="
                 r"\operatorname{rank}([A|b])<n$): consistent with "
                 r"infinitely many solutions."),
        ],
        "6.2": [
            bullet(r"Continuity at $x=a$: "
                   r"$\lim_{x\to a^{-}}f(x)="
                   r"\lim_{x\to a^{+}}f(x)=f(a)$."),
            bullet(r"Differentiability at $x=a$: the left-hand derivative "
                   r"and right-hand derivative"),
            display(r"$\mathrm{LHD}=\lim_{h\to0^{+}}"
                    r"\frac{f(a-h)-f(a)}{-h},\qquad "
                    r"\mathrm{RHD}=\lim_{h\to0^{+}}"
                    r"\frac{f(a+h)-f(a)}{h}$"),
            para(r"are finite and equal. Theorem: every function "
                 r"differentiable at $x=a$ is continuous at $x=a$, since "
                 r"$f(x)-f(a)=\frac{f(x)-f(a)}{x-a}(x-a)\to "
                 r"f'(a)\cdot0=0$. The converse is false (for example, "
                 r"$f(x)=|x|$ is continuous at $0$ with $\mathrm{LHD}=-1"
                 r"\neq\mathrm{RHD}=+1$)."),
            bullet(r"Parametric second-derivative trap alert: if "
                   r"$x=x(t)$ and $y=y(t)$, then "
                   r"$\frac{dy}{dx}=\frac{\dot y}{\dot x}$, and by the "
                   r"chain rule"),
            display(r"$\frac{d^{2}y}{dx^{2}}="
                    r"\frac{d}{dx}\left(\frac{dy}{dx}\right)="
                    r"\frac{\frac{d}{dt}\left(\frac{dy}{dx}\right)}"
                    r"{dx/dt}="
                    r"\frac{\dot x\ddot y-\dot y\ddot x}{\dot x^{3}}.$"),
            para(r"Never write $\frac{\ddot y}{\ddot x}$; that is not the "
                 r"second derivative with respect to $x$."),
            bullet(r"Rolle's theorem and Lagrange's mean value theorem "
                   r"(MVT): if $f$ is continuous on $[a,b]$ and "
                   r"differentiable on $(a,b)$, then there exists "
                   r"$c\in(a,b)$ such that"),
            display(r"$f'(c)=\frac{f(b)-f(a)}{b-a}.$"),
            para(r"The instantaneous tangent slope equals the chord "
                 r"slope. If in addition $f(a)=f(b)$, Rolle's theorem "
                 r"guarantees $f'(c)=0$."),
        ],
        "1.5": [
            para(r"Instead of memorizing Venn-diagram formulas or "
                 r"guessing functional inverses by trial and error, "
                 r"advanced mathematics relies on two universal algebraic "
                 r"tools."),
            para(r"1. Boolean indicator-function algebra (proving any set "
                 r"identity in three lines). For any subset $A\subseteq "
                 r"U$, define its indicator function "
                 r"$1_{A}:U\to\{0,1\}$ by $1_{A}(x)=1$ if $x\in A$ and "
                 r"$0$ if $x\notin A$. Because $0^{2}=0$ and $1^{2}=1$, "
                 r"indicators are idempotent ($1_{A}^{2}=1_{A}$) and "
                 r"convert set operations into ordinary polynomial "
                 r"arithmetic:"),
            display(r"$1_{A\cap B}=1_{A}1_{B},\qquad "
                    r"1_{A^{c}}=1-1_{A},\qquad "
                    r"1_{A\setminus B}=1_{A}(1-1_{B}),$"),
            display(r"$1_{A\triangle B}=(1_{A}-1_{B})^{2}="
                    r"1_{A}+1_{B}-2\,1_{A}1_{B}.$"),
            para(r"For the union $A_{1}\cup\cdots\cup A_{n}$, the "
                 r"complement is $A_{1}^{c}\cap\cdots\cap A_{n}^{c}$, so"),
            display(r"$1-1_{A_{1}\cup\cdots\cup A_{n}}="
                    r"\prod_{i=1}^{n}(1-1_{A_{i}})="
                    r"1-\sum_{i}1_{A_{i}}+\sum_{i<j}1_{A_{i}}1_{A_{j}}-"
                    r"\sum_{i<j<k}1_{A_{i}}1_{A_{j}}1_{A_{k}}+\cdots+"
                    r"(-1)^{n}1_{A_{1}}\cdots1_{A_{n}}.$"),
            para(r"Summing over all $x\in U$ (where "
                 r"$\sum_{x\in U}1_{S}(x)=|S|$) immediately proves the "
                 r"general $n$-set principle of inclusion-exclusion."),
            para(r"2. Canonical quotient decomposition of any function. "
                 r"Every function $f:A\to B$ defines a natural equivalence "
                 r"relation on its domain via "
                 r"$x_{1}\sim_{f}x_{2}\iff f(x_{1})=f(x_{2})$. "
                 r"Collapsing each equivalence class $[x]$ (the level set "
                 r"or fiber $f^{-1}(\{y\})$) to a single point in the "
                 r"quotient set $A/{\sim_{f}}$ factors $f$ uniquely as"),
            display(r"$f=\iota\circ\tilde f\circ\pi,$"),
            para(r"where $\pi:A\to A/{\sim_{f}}$ is surjective, "
                 r"$\tilde f:A/{\sim_{f}}\to\operatorname{Range}(f)$ is a "
                 r"bijection, and "
                 r"$\iota:\operatorname{Range}(f)\hookrightarrow B$ is "
                 r"injective. This explains why restricting the domain to "
                 r"a single monotonic branch (so each fiber has size $1$) "
                 r"and restricting the codomain to "
                 r"$\operatorname{Range}(f)$ makes any function "
                 r"invertible."),
        ],
        "5.4": [
            para(r"1. Joachimsthal's unified proof of $T=0$, "
                 r"$SS_{1}=T^{2}$, and $T=S_{1}$ for every conic. Write "
                 r"any general second-degree conic in symmetric matrix "
                 r"form $S(\tilde x)=\tilde x^{T}Q\tilde x=0$, where "
                 r"$\tilde x=(x,y,1)^{T}$, and define the bilinear "
                 r"polarized form "
                 r"$T(\tilde x,\tilde x_{1})=\tilde x^{T}Q\tilde x_{1}$. "
                 r"A point dividing the segment from $P(\tilde x_{1})$ to "
                 r"$R(\tilde x_{2})$ in ratio $\lambda:1$ has coordinates "
                 r"$\tilde x=\frac{\tilde x_{1}+\lambda\tilde x_{2}}"
                 r"{1+\lambda}$. Substituting $\tilde x$ into "
                 r"$S(\tilde x)=0$ yields Joachimsthal's quadratic in "
                 r"$\lambda$:"),
            display(r"$\lambda^{2}S(\tilde x_{2})+"
                    r"2\lambda T(\tilde x_{2},\tilde x_{1})+"
                    r"S(\tilde x_{1})=0.$"),
            para(r"Every classical tangent and chord theorem follows in "
                 r"one line from the roots $\lambda_{1},\lambda_{2}$ of "
                 r"this single quadratic:"),
            bullet(r"Tangent at $\tilde x_{1}$ on the conic "
                   r"($S(\tilde x_{1})=0$): both intersection roots "
                   r"coincide at $\lambda=0$ iff the coefficient of "
                   r"$\lambda$ vanishes, giving $T(\tilde x,"
                   r"\tilde x_{1})=0$."),
            bullet(r"Pair of tangents from an external point "
                   r"$\tilde x_{1}$: the line $PR$ is tangent to the "
                   r"conic iff Joachimsthal's quadratic has equal roots "
                   r"($D_{\lambda}=0$), so"),
            display(r"$4T(\tilde x,\tilde x_{1})^{2}-"
                    r"4S(\tilde x)S(\tilde x_{1})=0\iff SS_{1}=T^{2}.$"),
            bullet(r"Chord bisected at midpoint $\tilde x_{1}$: the two "
                   r"endpoints correspond to $\lambda_{1}+\lambda_{2}=0$ "
                   r"(equal and opposite ratios $\pm1$). Equivalently, if "
                   r"$\tilde x_{2}=\tilde x_{1}+r\vec d$, the linear "
                   r"coefficient condition $T(\vec d,\tilde x_{1})=0$ is "
                   r"the same as $T(\tilde x,\tilde x_{1})=S(\tilde x_{1})$, "
                   r"i.e., $T=S_{1}$."),
            para(r"2. Homogenization of a conic with a straight line: to "
                 r"find the pair of straight lines joining the origin "
                 r"$(0,0)$ to the two intersection points of the conic "
                 r"$ax^{2}+2hxy+by^{2}+2gx+2fy+c=0$ and the line "
                 r"$lx+my-n=0$, multiply the degree-$1$ terms by "
                 r"$\frac{lx+my}{n}$ and the constant $c$ by "
                 r"$\left(\frac{lx+my}{n}\right)^{2}$:"),
            display(r"$ax^{2}+2hxy+by^{2}+(2gx+2fy)"
                    r"\left(\frac{lx+my}{n}\right)+c"
                    r"\left(\frac{lx+my}{n}\right)^{2}=0.$"),
            para(r"The two lines are perpendicular ($90^{\circ}$ at the "
                 r"origin) iff (coefficient of $x^{2}$) + (coefficient of "
                 r"$y^{2}$) $=0$."),
        ],
        "5.3": [
            para(r"A conic section is the locus of a point $P$ whose "
                 r"distance from a fixed point $S$ (the focus) bears a "
                 r"constant ratio $e$ (the eccentricity) to its "
                 r"perpendicular distance from a fixed line $L$ (the "
                 r"directrix): $SP=e\cdot PM$."),
            bullet(r"Standard equations (opening to the right; rotate for "
                   r"other axes):"),
            display(r"$\text{Parabola}: y^{2}=4ax\quad(a>0),"
                    r"\qquad \text{Ellipse}: \frac{x^{2}}{a^{2}}+"
                    r"\frac{y^{2}}{b^{2}}=1\quad(a>b),$"),
            display(r"$\text{Hyperbola}: \frac{x^{2}}{a^{2}}-"
                    r"\frac{y^{2}}{b^{2}}=1.$"),
            bullet(r"Eccentricity:"),
            display(r"$\text{Parabola}: e=1,\qquad "
                    r"\text{Ellipse}: e=\sqrt{1-\frac{b^{2}}{a^{2}}},"
                    r"\qquad \text{Hyperbola}: "
                    r"e=\sqrt{1+\frac{b^{2}}{a^{2}}}.$"),
            bullet(r"Vertices and foci:"),
            display(r"$\text{Parabola}: (0,0);\ (a,0),$"),
            display(r"$\text{Ellipse: }(\pm a,0);\ (\pm ae,0),\qquad "
                    r"\text{Hyperbola: }(\pm a,0);\ (\pm ae,0).$"),
            bullet(r"Directrices:"),
            display(r"$\text{Parabola}: x=-a,\qquad "
                    r"\text{Ellipse}: x=\pm\frac{a}{e},\qquad "
                    r"\text{Hyperbola}: x=\pm\frac{a}{e}.$"),
            bullet(r"Latus rectum:"),
            display(r"$\text{Parabola}: 4a"
                    r"\ (\text{ends }(a,\pm2a)),\qquad "
                    r"\text{Ellipse}: \frac{2b^{2}}{a},\qquad "
                    r"\text{Hyperbola}: \frac{2b^{2}}{a}.$"),
            bullet(r"Parametric coordinates:"),
            display(r"$\text{Parabola}: (at^{2},2at),\qquad "
                    r"\text{Ellipse}: (a\cos\theta,b\sin\theta),$"),
            display(r"$\text{Hyperbola}: (a\sec\theta,b\tan\theta).$"),
            bullet(r"Tangent of slope $m$:"),
            display(r"$\text{Parabola}: y=mx+\frac{a}{m},$"),
            display(r"$\text{Ellipse}: y=mx\pm\sqrt{a^{2}m^{2}+b^{2}},"
                    r"\qquad "
                    r"\text{Hyperbola}: y=mx\pm"
                    r"\sqrt{a^{2}m^{2}-b^{2}}.$"),
            bullet(r"Director circle (locus of perpendicular tangents):"),
            display(r"$\text{Parabola}: x=-a,\qquad "
                    r"\text{Ellipse}: x^{2}+y^{2}=a^{2}+b^{2},$"),
            display(r"$\text{Hyperbola}: x^{2}+y^{2}=a^{2}-b^{2}"
                    r"\ (a>b).$"),
            bullet(r"Focal property:"),
            display(r"$\text{Parabola}: SP=x_{1}+a,\qquad "
                    r"\text{Ellipse}: SP+S'P=2a,$"),
            display(r"$\text{Hyperbola}: |SP-S'P|=2a.$"),
        ],
        "8.3": [
            para(r"1. Euler's complex-exponential proof of the Dirichlet "
                 r"trigonometric series: instead of telescoping "
                 r"$\sum_{k=1}^{n}\cos(k\theta)$ and "
                 r"$\sum_{k=1}^{n}\sin(k\theta)$ separately with "
                 r"product-to-sum tricks, combine them into a single "
                 r"geometric series in $z=e^{i\theta}$:"),
            display(r"$C_{n}+iS_{n}=\sum_{k=1}^{n}e^{ik\theta}="
                    r"e^{i\theta}\frac{e^{in\theta}-1}{e^{i\theta}-1}="
                    r"e^{i(n+1)\theta/2}\frac{\sin(n\theta/2)}"
                    r"{\sin(\theta/2)}.$"),
            para(r"Taking real and imaginary parts gives both sums in one "
                 r"line:"),
            display(r"$\sum_{k=1}^{n}\cos(k\theta)="
                    r"\frac{\sin(n\theta/2)}{\sin(\theta/2)}"
                    r"\cos\left(\frac{(n+1)\theta}{2}\right),$"),
            display(r"$\sum_{k=1}^{n}\sin(k\theta)="
                    r"\frac{\sin(n\theta/2)}{\sin(\theta/2)}"
                    r"\sin\left(\frac{(n+1)\theta}{2}\right).$"),
            para(r"2. Complex argument method for multi-term inverse "
                 r"tangent sums: since $\arg(a+ib)=\arctan(b/a)$ for "
                 r"$a>0$, multiplying complex numbers adds their "
                 r"inverse-tangent angles automatically:"),
            display(r"$\sum_{k=1}^{n}\arctan\left(\frac{y_{k}}{x_{k}}\right)="
                    r"\arg\prod_{k=1}^{n}(x_{k}+iy_{k})\pmod{\pi}.$"),
            para(r"For example, to prove "
                 r"$\arctan\frac{1}{2}+\arctan\frac{1}{5}+"
                 r"\arctan\frac{1}{8}=\frac{\pi}{4}$, simply multiply"),
            display(r"$(2+i)(5+i)(8+i)=(9+7i)(8+i)="
                    r"65+65i=65(1+i),$"),
            para(r"whose argument is $\arctan(1)=\frac{\pi}{4}$."),
        ],
        "12.2": [
            para(r"1. Why backpropagation computes "
                 r"$\nabla_{\theta}L\in\mathbb{R}^{P}$ in a constant "
                 r"multiple of forward-pass cost: for a composition of "
                 r"$L$ layers $f=f_{L}\circ f_{L-1}\circ\cdots\circ "
                 r"f_{1}:\mathbb{R}^{P}\to\mathbb{R}$, the total Jacobian "
                 r"is $J=J_{L}J_{L-1}\cdots J_{1}$."),
            bullet(r"Forward-mode (JVP): propagates a tangent vector "
                   r"$v\in\mathbb{R}^{P}$ left-to-right as "
                   r"$J_{L}(J_{L-1}(\cdots(J_{1}v)))$, requiring $P$ "
                   r"separate passes to obtain all $P$ partial "
                   r"derivatives."),
            bullet(r"Reverse-mode (backpropagation / VJP): propagates a "
                   r"scalar output sensitivity $\bar y=1\in"
                   r"\mathbb{R}^{1\times1}$ right-to-left as "
                   r"$(((\bar yJ_{L})J_{L-1})\cdots J_{1})$. Every "
                   r"intermediate product is a row vector (never a full "
                   r"matrix-matrix product), yielding the entire "
                   r"$P$-dimensional gradient in a single backward "
                   r"pass."),
        ],
        "1.1": [
            para(r"A set is a well-defined, unordered collection of "
                 r"distinct objects called elements. If $x$ belongs to "
                 r"$A$, we write $x\in A$; otherwise $x\notin A$. Sets are "
                 r"represented in roster form (listing elements explicitly, "
                 r"for example $A=\{2,3,5,7\}$) or set-builder form "
                 r"(specifying a defining predicate $P(x)$, for example "
                 r"$A=\{x\in\mathbb{N}:x\ \text{is prime and}\ x<10\}$)."),
            bullet(r"Standard number systems: "
                   r"$\mathbb{N}=\{1,2,3,\ldots\}$ (naturals), "
                   r"$\mathbb{W}=\{0,1,2,\ldots\}$ (whole numbers), "
                   r"$\mathbb{Z}=\{0,\pm1,\pm2,\ldots\}$ (integers), "
                   r"$\mathbb{Q}=\{p/q:p,q\in\mathbb{Z},\ q\neq0\}$ "
                   r"(rationals), $\mathbb{R}\setminus\mathbb{Q}$ "
                   r"(irrationals), $\mathbb{R}$ (reals), and "
                   r"$\mathbb{C}$ (complex numbers). They satisfy "
                   r"$\mathbb{N}\subset\mathbb{W}\subset\mathbb{Z}\subset"
                   r"\mathbb{Q}\subset\mathbb{R}\subset\mathbb{C}$."),
            bullet(r"Empty set, subsets, and power set: the empty set "
                   r"$\varnothing=\{\}$ has zero elements. $A$ is a subset "
                   r"of $B$ ($A\subseteq B$) iff every $x\in A$ also lies "
                   r"in $B$. Two sets are equal iff $A\subseteq B$ and "
                   r"$B\subseteq A$. The power set $\mathcal{P}(A)$ is "
                   r"the set of all subsets of $A$. If $|A|=n$, every "
                   r"element has two independent choices (included or "
                   r"excluded), so"),
            display(r"$|\mathcal{P}(A)|=2^{n},\qquad "
                    r"\text{proper subsets}=2^{n}-1,\qquad "
                    r"\text{nonempty proper subsets}=2^{n}-2.$"),
            bullet(r"Set operations: given a universal set $U$ and "
                   r"subsets $A,B\subseteq U$,"),
            display(r"$A\cup B=\{x:x\in A\ \text{or}\ x\in B\},$"),
            display(r"$A\cap B=\{x:x\in A\ \text{and}\ x\in B\},\qquad "
                    r"A\setminus B=\{x\in A:x\notin B\}=A\cap B^{c}.$"),
            para(r"The symmetric difference "
                 r"$A\triangle B=(A\setminus B)\cup(B\setminus A)="
                 r"(A\cup B)\setminus(A\cap B)$ contains the elements in "
                 r"exactly one of $A$ or $B$."),
            theorem("1.1",
                    "De Morgan's Laws & Principle of Inclusion-Exclusion "
                    "(With Formal Proofs)",
                    r"1. De Morgan's laws: for any subsets $A,B\subseteq "
                    r"U$,"),
            display(r"$(A\cup B)^{c}=A^{c}\cap B^{c},\qquad "
                    r"(A\cap B)^{c}=A^{c}\cup B^{c}.$"),
            proof(r"Proof of $(A\cup B)^{c}=A^{c}\cap B^{c}$",
                  r"Let $x\in U$. By the logical equivalence of negation "
                  r"over disjunction, $\lnot(P\lor Q)\iff(\lnot P)\land"
                  r"(\lnot Q)$: "
                  r"$x\in(A\cup B)^{c}\iff\lnot(x\in A\cup B)\iff"
                  r"\lnot(x\in A\ \text{or}\ x\in B)\iff x\notin A"
                  r"\ \text{and}\ x\notin B\iff x\in A^{c}\cap B^{c}$. "
                  r"$\blacksquare$"),
            para(r"2. Two-set and three-set inclusion-exclusion "
                 r"principle: for finite sets $A,B,C$,"),
            display(r"$|A\cup B|=|A|+|B|-|A\cap B|,$"),
            display(r"$|A\triangle B|=|A|+|B|-2|A\cap B|,$"),
            display(r"$|A\cup B\cup C|=|A|+|B|+|C|-|A\cap B|-"
                    r"|B\cap C|-|C\cap A|+|A\cap B\cap C|.$"),
            proof(r"Proof of the 3-set formula",
                  r"Group $B\cup C$ as a single set $D$. Then "
                  r"$|A\cup(B\cup C)|=|A|+|B\cup C|-|A\cap(B\cup C)|"
                  r"=|A|+|B|+|C|-|B\cap C|-|(A\cap B)\cup(A\cap C)|"
                  r"=|A|+|B|+|C|-|B\cap C|-|A\cap B|-|A\cap C|+"
                  r"|A\cap B\cap C|$. $\blacksquare$"),
            para(r"The number of elements lying in exactly one of "
                 r"$A,B,C$ is"),
            display(r"$|A\ \text{only}|+|B\ \text{only}|+|C\ \text{only}|"
                    r"=|A|+|B|+|C|-2(|A\cap B|+|B\cap C|+|C\cap A|)+"
                    r"3|A\cap B\cap C|.$"),
        ],
        "10.2": [
            para(r"1. Moment generating function (MGF) derivation of "
                 r"binomial moments: instead of differentiating "
                 r"combinatorial sums to find $\mathbb{E}[X]$ and "
                 r"$\operatorname{Var}(X)$ for "
                 r"$X\sim\mathrm{Bin}(n,p)$, compute the MGF "
                 r"$M_{X}(t)=\mathbb{E}[e^{tX}]$ and the cumulant "
                 r"generating function $K_{X}(t)=\ln M_{X}(t)$:"),
            display(r"$M_{X}(t)=\sum_{r=0}^{n}\binom{n}{r}"
                    r"(pe^{t})^{r}q^{n-r}=(q+pe^{t})^{n},$"),
            display(r"$K_{X}(t)=n\ln(q+pe^{t}).$"),
            para(r"Differentiating $K_{X}(t)$ at $t=0$ gives the mean and "
                 r"variance in two lines:"),
            display(r"$\mathbb{E}[X]=K_{X}'(0)="
                    r"\left.\frac{npe^{t}}{q+pe^{t}}\right|_{t=0}=np,$"),
            display(r"$\operatorname{Var}(X)=K_{X}''(0)="
                    r"\left.\frac{npqe^{t}}{(q+pe^{t})^{2}}\right|_{t=0}"
                    r"=npq.$"),
            para(r"2. Eve's law (law of total variance) proof of the "
                 r"pooled two-group variance: for any random variable "
                 r"$X$ and group indicator $G\in\{1,2\}$ with group "
                 r"weights $w_{i}=\frac{n_{i}}{n_{1}+n_{2}}$, conditional "
                 r"means $\mu_{i}=\mathbb{E}[X\mid G=i]$, and conditional "
                 r"variances $\sigma_{i}^{2}="
                 r"\operatorname{Var}(X\mid G=i)$,"),
            display(r"$\operatorname{Var}(X)="
                    r"\underbrace{\mathbb{E}[\operatorname{Var}(X\mid G)]}_{"
                    r"\text{within-group variance}}+"
                    r"\underbrace{\operatorname{Var}(\mathbb{E}[X\mid G])}_{"
                    r"\text{between-group variance}}="
                    r"\sum_{i}w_{i}\sigma_{i}^{2}+"
                    r"\sum_{i}w_{i}(\mu_{i}-\mu)^{2},$"),
            display(r"$=\frac{n_{1}(\sigma_{1}^{2}+d_{1}^{2})+"
                    r"n_{2}(\sigma_{2}^{2}+d_{2}^{2})}{n_{1}+n_{2}},"
                    r"\qquad d_{i}=\mu_{i}-\mu.$"),
        ],
        "6.3": [
            bullet(r"Tangent, normal, subtangent, and subnormal at "
                   r"$P(x_{0},y_{0})$ with slope $m=f'(x_{0})$:"),
            display(r"$\text{Tangent}: y-y_{0}=m(x-x_{0}),\qquad "
                    r"\text{Normal}: y-y_{0}=-\frac{1}{m}(x-x_{0}),$"),
            display(r"$L_{\text{subtan}}=\left|\frac{y_{0}}{m}\right|,"
                    r"\qquad L_{\text{subnorm}}=|y_{0}m|.$"),
            bullet(r"Angle of intersection of two curves: the angle "
                   r"between $C_{1}$ and $C_{2}$ at a common point $P$ is "
                   r"the angle between their tangents at $P$:"),
            display(r"$\tan\theta=\left|\frac{m_{1}-m_{2}}"
                    r"{1+m_{1}m_{2}}\right|.$"),
            para(r"The curves cut orthogonally iff $m_{1}m_{2}=-1$."),
            bullet(r"First, second, and higher-order derivative tests for "
                   r"maxima and minima: at a stationary point "
                   r"$f'(x^{*})=0$, if $f''(x^{*})>0$ then $x^{*}$ is a "
                   r"strict local minimum, and if $f''(x^{*})<0$ then "
                   r"$x^{*}$ is a strict local maximum. If "
                   r"$f'(x^{*})=f''(x^{*})=\cdots=f^{(k-1)}(x^{*})=0$ and "
                   r"$f^{(k)}(x^{*})\neq0$, then $x^{*}$ is an extremum "
                   r"when $k$ is even and a point of inflection when $k$ "
                   r"is odd."),
        ],
        "6.4": [
            para(r"1. Why Peano Taylor asymptotics beat repeated L'H\^opital "
                 r"differentiation: when a limit "
                 r"$\lim_{x\to0}\frac{N(x)}{D(x)}$ involves products and "
                 r"compositions, such as "
                 r"$\frac{\tan x-\sin x}{x^{3}}$, and $D(x)\sim cx^{k}$, "
                 r"applying L'H\^opital's rule $k$ times produces an "
                 r"explosion of product-rule terms. Instead, expand only "
                 r"up to degree $k$ using Peano's remainder "
                 r"$o(x^{k})$:"),
            display(r"$\tan x-\sin x=\left(x+\frac{x^{3}}{3}+"
                    r"o(x^{3})\right)-\left(x-\frac{x^{3}}{6}+"
                    r"o(x^{3})\right)=\frac{x^{3}}{2}+o(x^{3}),$"),
            para(r"which reduces any $0/0$ limit to matching polynomial "
                 r"coefficients in two lines."),
            para(r"2. Systematic construction of Rolle's auxiliary "
                 r"function via integrating factors: to prove that a "
                 r"differential relation $f'(c)+g'(c)f(c)=0$ has a root "
                 r"$c\in(a,b)$ using Rolle's theorem, multiply by the "
                 r"integrating factor $e^{g(x)}$:"),
            display(r"$\phi(x)=e^{g(x)}f(x)\implies "
                    r"\phi'(x)=e^{g(x)}\left[f'(x)+g'(x)f(x)\right].$"),
            para(r"For example, to prove Lagrange's mean value theorem on "
                 r"$[a,b]$, subtract the chord line "
                 r"$L(x)=f(a)+\frac{f(b)-f(a)}{b-a}(x-a)$ and define "
                 r"$\phi(x)=f(x)-L(x)$. Then $\phi(a)=\phi(b)=0$, so "
                 r"Rolle's theorem gives "
                 r"$\phi'(c)=f'(c)-\frac{f(b)-f(a)}{b-a}=0$."),
        ],
        "15.1": [
            bullet(r"Six workhorse distributions: (1) Binomial "
                   r"$\mathrm{Bin}(n,p)$ with $\mathbb{E}[X]=np$ and "
                   r"$\operatorname{Var}(X)=np(1-p)$; (2) Poisson "
                   r"$\mathrm{Pois}(\lambda)$ with "
                   r"$P(K=k)=\frac{\lambda^{k}e^{-\lambda}}{k!}$ and "
                   r"$\mathbb{E}[K]=\operatorname{Var}(K)=\lambda$; "
                   r"(3) Exponential$(\lambda)$ with "
                   r"$p(t)=\lambda e^{-\lambda t}$, "
                   r"$\mathbb{E}[T]=\frac{1}{\lambda}$, and "
                   r"$\operatorname{Var}(T)=\frac{1}{\lambda^{2}}$; "
                   r"(4) Gaussian $\mathcal{N}(\mu,\sigma^{2})$ with MGF "
                   r"$M_{X}(t)=\exp\left(\mu t+\frac{1}{2}\sigma^{2}t^{2}\right)$; "
                   r"(5) log-normal, where "
                   r"$\ln S\sim\mathcal{N}(\mu,\sigma^{2})\implies "
                   r"\mathbb{E}[S]=e^{\mu+\sigma^{2}/2}$; and (6) Student-"
                   r"$t_{\nu}$ with $\operatorname{Var}=\frac{\nu}{\nu-2}$ "
                   r"for $\nu>2$."),
            bullet(r"Portfolio variance, law of total variance, and "
                   r"central limit theorem:"),
            display(r"$\operatorname{Var}(aX+bY)=a^{2}\operatorname{Var}(X)+"
                    r"b^{2}\operatorname{Var}(Y)+2ab\,\operatorname{Cov}(X,Y),$"),
            display(r"$\operatorname{Var}(X)="
                    r"\mathbb{E}[\operatorname{Var}(X\mid Z)]+"
                    r"\operatorname{Var}(\mathbb{E}[X\mid Z]).$"),
            display(r"$\frac{\sqrt{n}(\bar X_{n}-\mu)}{\sigma}"
                    r"\ \xrightarrow{d}\ \mathcal{N}(0,1),\qquad "
                    r"\bar X_{n}\approx\mathcal{N}\left(\mu,"
                    r"\frac{\sigma^{2}}{n}\right).$"),
            bullet(r"Shannon entropy, cross-entropy, KL divergence, and "
                   r"the VAE ELBO:"),
            display(r"$H(P)=-\sum_{x}P(x)\ln P(x),\qquad "
                    r"D_{\mathrm{KL}}(P\|Q)="
                    r"\sum_{x}P(x)\ln\frac{P(x)}{Q(x)}="
                    r"H(P,Q)-H(P)\geq0,$"),
            display(r"$\ln p_{\theta}(x)\geq "
                    r"\mathbb{E}_{q_{\phi}(z|x)}"
                    r"\left[\ln p_{\theta}(x\mid z)\right]-"
                    r"D_{\mathrm{KL}}\left(q_{\phi}(z\mid x)\|p(z)\right).$"),
        ],
        "16.1": [
            bullet(r"$L$-smoothness, strong convexity, and optimizers: if "
                   r"$\mu I\preceq\nabla^{2}f(w)\preceq LI$, gradient "
                   r"descent $w_{t+1}=w_{t}-\eta\nabla f(w_{t})$ requires "
                   r"$\eta<\frac{2}{L}$ for stability. AdamW normalizes "
                   r"each coordinate by its root-mean-square gradient "
                   r"$\hat v_{t}$ with decoupled weight decay:"),
            display(r"$m_{t}=\beta_{1}m_{t-1}+(1-\beta_{1})g_{t},\qquad "
                    r"v_{t}=\beta_{2}v_{t-1}+(1-\beta_{2})g_{t}^{2},$"),
            display(r"$w_{t+1}=(1-\eta\lambda)w_{t}-\eta"
                    r"\frac{\hat m_{t}}{\sqrt{\hat v_{t}}+\varepsilon}.$"),
            bullet(r"KKT conditions and Lasso soft-thresholding: "
                   r"minimizing $\frac{1}{2}(w-w_{\mathrm{OLS}})^{2}+"
                   r"\lambda|w|$ via subgradients "
                   r"$0\in w-w_{\mathrm{OLS}}+\lambda\partial|w|$ yields"),
            display(r"$w^{*}=S_{\lambda}(w_{\mathrm{OLS}})="
                    r"\operatorname{sign}(w_{\mathrm{OLS}})"
                    r"\max(|w_{\mathrm{OLS}}|-\lambda,0).$"),
            bullet(r"Markowitz portfolio theory and the Kelly criterion:"),
            display(r"$w_{\mathrm{GMV}}=\frac{\Sigma^{-1}\mathbf{1}}"
                    r"{\mathbf{1}^{T}\Sigma^{-1}\mathbf{1}},\qquad "
                    r"w_{\mathrm{Sharpe}}\propto "
                    r"\Sigma^{-1}(\mu-r_{f}\mathbf{1}),$"),
            display(r"$f_{\mathrm{Kelly}}=\Sigma^{-1}"
                    r"(\mu-r_{f}\mathbf{1}).$"),
        ],
        "16.2": [
            para(r"1. Why gradient descent converges linearly under the "
                 r"Polyak-Łojasiewicz inequality (even without convexity): "
                 r"suppose $f$ is $L$-smooth, so"),
            display(r"$f(w_{t+1})\leq f(w_{t})+"
                    r"\langle\nabla f(w_{t}),w_{t+1}-w_{t}\rangle+"
                    r"\frac{L}{2}\|w_{t+1}-w_{t}\|_{2}^{2},$"),
            para(r"and satisfies the PL condition "
                 r"$\frac{1}{2}\|\nabla f(w)\|_{2}^{2}\geq"
                 r"\mu\left(f(w)-f^{*}\right)$ with $\mu>0$. With step "
                 r"size $\eta=\frac{1}{L}$, substituting "
                 r"$w_{t+1}-w_{t}=-\frac{1}{L}\nabla f(w_{t})$ gives the "
                 r"descent lemma"),
            display(r"$f(w_{t+1})-f^{*}\leq f(w_{t})-f^{*}-"
                    r"\frac{1}{2L}\|\nabla f(w_{t})\|_{2}^{2}\leq "
                    r"\left(1-\frac{\mu}{L}\right)\left(f(w_{t})-f^{*}\right),$"),
            display(r"$\implies f(w_{T})-f^{*}\leq "
                    r"\left(1-\frac{1}{\kappa}\right)^{T}"
                    r"\left(f(w_{0})-f^{*}\right),\qquad "
                    r"\kappa=\frac{L}{\mu}.$"),
        ],
        "17.1": [
            bullet(r"Itô's lemma: for an Itô diffusion "
                   r"$dX_{t}=\mu_{t}dt+\sigma_{t}dW_{t}$ and any smooth "
                   r"$f(X_{t},t)$, expanding to second order via Taylor's "
                   r"theorem and substituting "
                   r"$(dX_{t})^{2}=\sigma_{t}^{2}(dW_{t})^{2}="
                   r"\sigma_{t}^{2}dt$ yields"),
            display(r"$df(X_{t},t)=\left(\frac{\partial f}{\partial t}+"
                    r"\mu_{t}\frac{\partial f}{\partial x}+"
                    r"\frac{1}{2}\sigma_{t}^{2}\frac{\partial^{2}f}{"
                    r"\partial x^{2}}\right)dt+\sigma_{t}\frac{"
                    r"\partial f}{\partial x}dW_{t}.$"),
            bullet(r"Exact geometric Brownian motion (GBM) solution: "
                   r"applying Itô's lemma to $\ln S_{t}$ for "
                   r"$dS_{t}=\mu S_{t}dt+\sigma S_{t}dW_{t}$ gives "
                   r"$d(\ln S_{t})=\left(\mu-\frac{1}{2}\sigma^{2}\right)dt"
                   r"+\sigma dW_{t}$, so"),
            display(r"$S_{T}=S_{0}\exp\left[\left(\mu-\frac{1}{2}"
                    r"\sigma^{2}\right)T+\sigma W_{T}\right].$"),
            bullet(r"Black-Scholes-Merton PDE and closed-form option "
                   r"formulas, with $\tau=T-t$:"),
            display(r"$\frac{\partial V}{\partial t}+rS\frac{"
                    r"\partial V}{\partial S}+\frac{1}{2}\sigma^{2}S^{2}"
                    r"\frac{\partial^{2}V}{\partial S^{2}}-rV=0,$"),
            display(r"$C(S,t)=SN(d_{1})-Ke^{-r\tau}N(d_{2}),\qquad "
                    r"P(S,t)=Ke^{-r\tau}N(-d_{2})-SN(-d_{1}),$"),
            display(r"$d_{1,2}=\frac{\ln(S/K)+(r\pm\frac{1}{2}"
                    r"\sigma^{2})\tau}{\sigma\sqrt{\tau}}.$"),
        ],
        "17.2": [
            para(r"1. Why the physical drift $\mu$ vanishes completely "
                 r"from the Black-Scholes equation: in the physical "
                 r"measure $\mathbb{P}$, "
                 r"$dS_{t}=\mu S_{t}dt+\sigma S_{t}dW_{t}^{\mathbb{P}}$. "
                 r"By Itô's lemma on $V(S_{t},t)$, the physical drift of "
                 r"$dV$ contains $\mu S_{t}\frac{\partial V}{"
                 r"\partial S}dt$, while the physical drift of the "
                 r"delta-hedge $\Delta_{t}dS_{t}$ contains "
                 r"$\mu S_{t}\Delta_{t}dt$. Choosing "
                 r"$\Delta_{t}=\frac{\partial V}{\partial S}$ cancels "
                 r"both $dW_{t}^{\mathbb{P}}$ and the $\mu S_{t}dt$ "
                 r"terms simultaneously."),
            para(r"Thus two investors who disagree wildly on whether a "
                 r"stock's expected return $\mu$ is $+30\%$ or $-20\%$ "
                 r"must still agree on the exact same option price "
                 r"$V(S_{0},0)$ if they agree on volatility $\sigma$."),
        ],
        "19.1": [
            bullet(r"Scaled dot-product self-attention and variance proof:"),
            display(r"$\operatorname{Attention}(Q,K,V)=\operatorname{softmax}"
                    r"\left(\frac{QK^{T}+M}{\sqrt{d_{k}}}\right)V,$"),
            para(r"If the entries of $q$ and $k$ have mean $0$ and variance "
                 r"$1$ independently, then "
                 r"$\operatorname{Var}(q^{T}k)=\sum_{l=1}^{d_{k}}"
                 r"\operatorname{Var}(q_{l}k_{l})=d_{k}$, so "
                 r"$\operatorname{Var}\left(\frac{q^{T}k}{\sqrt{d_{k}}}\right)=1$."),
            bullet(r"The full softmax Jacobian matrix: for "
                   r"$p=\operatorname{softmax}(z)$,"),
            display(r"$J_{\mathrm{softmax}}(z)=\frac{\partial p}{"
                    r"\partial z}=\operatorname{diag}(p)-pp^{T},\qquad "
                    r"J_{\mathrm{softmax}}g=p\odot g-(p^{T}g)\mathbf{1}.$"),
            bullet(r"FlashAttention online softmax rescaling: for two "
                   r"blocks with maxima $m_{1}$, $m_{2}$ and "
                   r"$m=\max(m_{1},m_{2})$,"),
            display(r"$\ell_{\mathrm{new}}=e^{m_{1}-m}\ell_{1}+"
                    r"e^{m_{2}-m}\ell_{2},$"),
            display(r"$O_{\mathrm{new}}=\frac{e^{m_{1}-m}\ell_{1}O_{1}+"
                    r"e^{m_{2}-m}\ell_{2}O_{2}}{\ell_{\mathrm{new}}}.$"),
        ],
        "19.2": [
            para(r"1. Why attention logits must be scaled by "
                 r"$\frac{1}{\sqrt{d_{k}}}$: suppose query "
                 r"$q\in\mathbb{R}^{d_{k}}$ and key "
                 r"$k\in\mathbb{R}^{d_{k}}$ have independent zero-mean, "
                 r"unit-variance entries. Then each product $q_{i}k_{i}$ "
                 r"has mean $0$ and variance "
                 r"$\mathbb{E}[q_{i}^{2}]\mathbb{E}[k_{i}^{2}]=1$, so "
                 r"their dot product has variance"),
            display(r"$\operatorname{Var}(q^{T}k)="
                    r"\sum_{i=1}^{d_{k}}\operatorname{Var}(q_{i}k_{i})="
                    r"d_{k}\implies "
                    r"\mathrm{SD}(q^{T}k)=\sqrt{d_{k}}.$"),
            para(r"Without dividing by $\sqrt{d_{k}}$, for "
                 r"$d_{k}=128$ the dot products reach magnitude around "
                 r"$\pm 20$, pushing $\operatorname{softmax}(z)$ into "
                 r"saturation where one entry is about $1$ and all others "
                 r"are about $0$, driving the Jacobian "
                 r"$\operatorname{diag}(p)-pp^{T}$ to $0$ (vanishing "
                 r"attention gradients). Dividing by $\sqrt{d_{k}}$ "
                 r"restores unit variance "
                 r"$\operatorname{Var}\left(\frac{q^{T}k}{\sqrt{d_{k}}}\right)=1$ "
                 r"across all head dimensions."),
        ],
        "18.1": [
            bullet(r"Newton-Raphson implied volatility and centered "
                   r"finite differences:"),
            display(r"$\sigma_{k+1}=\sigma_{k}-"
                    r"\frac{C_{BS}(\sigma_{k})-C_{\mathrm{mkt}}}"
                    r"{\mathcal{V}(\sigma_{k})},\qquad "
                    r"f'(x)\approx\frac{f(x+h)-f(x-h)}{2h},$"),
            display(r"$f''(x)\approx"
                    r"\frac{f(x+h)-2f(x)+f(x-h)}{h^{2}}.$"),
            bullet(r"Euler-Maruyama versus Milstein SDE steps:"),
            display(r"$X_{n+1}^{\mathrm{Milstein}}=X_{n}+\mu(X_{n})\Delta t+"
                    r"\sigma(X_{n})\Delta W_{n}+\frac{1}{2}\sigma(X_{n})"
                    r"\sigma'(X_{n})\left[(\Delta W_{n})^{2}-\Delta t\right].$"),
            bullet(r"Variance-reduced Monte Carlo: antithetic variates "
                   r"$\frac{1}{2}[g(Z)+g(-Z)]$ eliminate odd-order Taylor "
                   r"terms; control variates at "
                   r"$\beta^{*}="
                   r"\frac{\operatorname{Cov}(Y,C)}{\operatorname{Var}(C)}$ "
                   r"achieve"),
            display(r"$\operatorname{Var}(Y^{*})="
                    r"\operatorname{Var}(Y)(1-\rho_{YC}^{2}).$"),
        ],
        "18.2": [
            para(r"1. Von Neumann amplification factor $G(k)$ for "
                 r"explicit and Crank-Nicolson grids: substitute a "
                 r"discrete Fourier mode $V_{j}^{n}=G^{n}e^{ikj\Delta x}$ "
                 r"into the heat equation "
                 r"$\frac{\partial V}{\partial\tau}=\frac{1}{2}"
                 r"\sigma^{2}\frac{\partial^{2}V}{\partial x^{2}}$ with "
                 r"mesh ratio $\alpha=\frac{\sigma^{2}\Delta\tau}"
                 r"{2(\Delta x)^{2}}$:"),
            display(r"$G_{\mathrm{explicit}}(k)=1-4\alpha\sin^{2}"
                    r"\left(\frac{k\Delta x}{2}\right),\qquad "
                    r"G_{\mathrm{CN}}(k)="
                    r"\frac{1-2\alpha\sin^{2}(k\Delta x/2)}"
                    r"{1+2\alpha\sin^{2}(k\Delta x/2)}.$"),
            para(r"Stability requires $|G(k)|\leq1$ for all frequencies "
                 r"$k$. For the explicit scheme, the highest frequency "
                 r"$\sin^{2}(k\Delta x/2)=1$ requires "
                 r"$1-4\alpha\geq-1\iff\alpha\leq\frac{1}{2}$, whereas "
                 r"Crank-Nicolson has $|G_{\mathrm{CN}}(k)|<1$ for every "
                 r"$\alpha>0$ (unconditional $L^{2}$ stability)."),
        ],
        "21.1": [
            bullet(r"Merton (1976) jump-diffusion series, with "
                   r"$k=\mathbb{E}[J-1]$ and $\lambda'=\lambda(1+k)$:"),
            display(r"$C_{\mathrm{Merton}}(S_{0},K,T)="
                    r"\sum_{n=0}^{\infty}\frac{e^{-\lambda'T}"
                    r"(\lambda'T)^{n}}{n!}"
                    r"C_{BS}(S_{0},K,T,r_{n},\sigma_{n}).$"),
            bullet(r"Heston (1993) stochastic volatility and Dupire "
                   r"(1994) local volatility:"),
            display(r"$dS_{t}=rS_{t}dt+\sqrt{v_{t}}S_{t}dW_{t}^{S},\qquad "
                    r"dv_{t}=\kappa(\theta-v_{t})dt+\xi"
                    r"\sqrt{v_{t}}dW_{t}^{v},$"),
            display(r"$\sigma_{\mathrm{loc}}^{2}(K,T)="
                    r"\frac{\frac{\partial C}{\partial T}+rK"
                    r"\frac{\partial C}{\partial K}}{"
                    r"\frac{1}{2}K^{2}\frac{\partial^{2}C}{"
                    r"\partial K^{2}}}.$"),
            bullet(r"Vasicek and CIR short-rate yield curves: for "
                   r"$dr_{t}=\kappa(\theta-r_{t})dt+\sigma dW_{t}^{Q}$,"),
            display(r"$B(\tau)=\frac{1-e^{-\kappa\tau}}{\kappa},\qquad "
                    r"P(t,T)=A(t,T)e^{-B(\tau)r_{t}}.$"),
        ],
        "21.2": [
            para(r"1. How Dupire's equation emerges from the forward "
                 r"Fokker-Planck equation and Breeden-Litzenberger: let "
                 r"$\psi(K,T)$ be the risk-neutral transition density of "
                 r"$S_{T}$ evaluated at $S_{T}=K$. By Breeden-"
                 r"Litzenberger, $\psi(K,T)=e^{rT}\frac{\partial^{2}C}"
                 r"{\partial K^{2}}$, and integrating by parts gives"),
            display(r"$\int_{K}^{\infty}(S-K)\psi(S,T)\,dS="
                    r"e^{rT}C(K,T),\qquad "
                    r"\int_{K}^{\infty}\psi(S,T)\,dS="
                    r"-e^{rT}\frac{\partial C}{\partial K}.$"),
            para(r"Substituting these into the forward Fokker-Planck "
                 r"equation $\frac{\partial\psi}{\partial T}=rK"
                 r"\frac{\partial\psi}{\partial K}+"
                 r"\frac{1}{2}\sigma_{\mathrm{loc}}^{2}(K,T)K^{2}"
                 r"\frac{\partial^{2}\psi}{\partial K^{2}}$ and "
                 r"integrating twice with respect to $K$ yields Dupire's "
                 r"forward PDE:"),
            display(r"$\frac{\partial C}{\partial T}=-rK"
                    r"\frac{\partial C}{\partial K}+"
                    r"\frac{1}{2}\sigma_{\mathrm{loc}}^{2}(K,T)K^{2}"
                    r"\frac{\partial^{2}C}{\partial K^{2}},$"),
            display(r"$\implies \sigma_{\mathrm{loc}}^{2}(K,T)="
                    r"\frac{\frac{\partial C}{\partial T}+rK"
                    r"\frac{\partial C}{\partial K}}{"
                    r"\frac{1}{2}K^{2}\frac{\partial^{2}C}{"
                    r"\partial K^{2}}}.$"),
        ],
        "20.1": [
            bullet(r"Policy gradient theorem (log-derivative trick) and "
                   r"PPO surrogate:"),
            display(r"$\nabla_{\theta}J(\theta)=\mathbb{E}_{\pi_{\theta}}"
                    r"\left[\sum_{t=0}^{T}\nabla_{\theta}"
                    r"\ln\pi_{\theta}(a_{t}\mid s_{t})\hat A_{t}\right],$"),
            display(r"$L^{\mathrm{CLIP}}(\theta)=\mathbb{E}_{t}\left["
                    r"\min\left(r_{t}(\theta)\hat A_{t},"
                    r"\operatorname{clip}(r_{t}(\theta),1-\varepsilon,"
                    r"1+\varepsilon)\hat A_{t}\right)\right].$"),
            bullet(r"Almgren-Chriss (2001) optimal execution via the "
                   r"Euler-Lagrange equation: minimizing expected "
                   r"temporary-impact cost plus $\lambda$ times inventory "
                   r"variance"),
            display(r"$J[x]=\int_{0}^{T}\left[\eta\,\dot x(t)^{2}+"
                    r"\lambda\sigma^{2}x(t)^{2}\right]dt,$"),
            display(r"$\implies \ddot x(t)=\kappa^{2}x(t),\qquad "
                    r"x^{*}(t)=X_{0}\frac{\sinh(\kappa(T-t))}"
                    r"{\sinh(\kappa T)},\qquad "
                    r"\kappa=\sqrt{\frac{\lambda\sigma^{2}}{\eta}}.$"),
        ],
        "20.2": [
            para(r"1. Deriving the HJB equation from dynamic programming "
                 r"and Itô's lemma: for controlled state dynamics "
                 r"$dx_{t}=b(x_{t},u_{t})dt+\sigma(x_{t},u_{t})dW_{t}$ and "
                 r"value function "
                 r"$V(t,x)=\sup_{u}\mathbb{E}_{t}\left[\int_{t}^{T}"
                 r"L(s,x_{s},u_{s})ds+\Phi(x_{T})\right]$, Bellman's "
                 r"principle over $[t,t+dt]$ gives"),
            display(r"$V(t,x)=\sup_{u}\mathbb{E}\left[L(t,x,u)dt+"
                    r"V(t+dt,x_{t+dt})\right].$"),
            para(r"Expanding $dV=V(t+dt,x_{t+dt})-V(t,x)$ via Itô's "
                 r"lemma and dividing by $dt$ yields the Hamilton-Jacobi-"
                 r"Bellman PDE"),
            display(r"$\frac{\partial V}{\partial t}+\sup_{u\in U}"
                    r"\left\{L(t,x,u)+b(x,u)^{T}\nabla_{x}V+"
                    r"\frac{1}{2}\operatorname{Tr}\left["
                    r"\sigma(x,u)\sigma(x,u)^{T}\nabla_{x}^{2}V"
                    r"\right]\right\}=0,$"),
            display(r"$V(T,x)=\Phi(x).$"),
        ],
        "15.2": [
            para(r"1. The Cramér-Chernoff exponential moment method: "
                 r"Markov's inequality $P(X\geq a)\leq"
                 r"\frac{\mathbb{E}[X]}{a}$ gives weak polynomial tail "
                 r"bounds, whereas Chernoff bounding gives sharp "
                 r"exponential bounds. Applying Markov's inequality to the "
                 r"strictly increasing exponential $e^{sX}$ with $s>0$ and "
                 r"optimizing over the free parameter $s$ yields"),
            display(r"$P(X\geq t)=P(e^{sX}\geq e^{st})\leq "
                    r"\inf_{s>0}e^{-st}\mathbb{E}[e^{sX}]="
                    r"\exp\left(-\sup_{s>0}\left[st-\ln M_{X}(s)\right]\right)="
                    r"\exp\left(-I^{*}(t)\right),$"),
            para(r"where $I^{*}(t)$ is the Fenchel conjugate (Cramér rate "
                 r"function) of the cumulant generating function. For a "
                 r"$\sigma^{2}$-sub-Gaussian zero-mean variable with "
                 r"$\ln M_{X}(s)\leq\frac{1}{2}s^{2}\sigma^{2}$, "
                 r"optimizing $st-\frac{1}{2}s^{2}\sigma^{2}$ at "
                 r"$s^{*}=t/\sigma^{2}$ immediately proves"),
            display(r"$P(X\geq t)\leq"
                    r"\exp\left(-\frac{t^{2}}{2\sigma^{2}}\right).$"),
        ],
        "11.3": [
            para(r"1. Fenchel-Moreau biconjugation theorem "
                 r"($f^{**}=f$): why does dual optimization recover the "
                 r"exact primal function when $f$ is closed and convex? "
                 r"Geometrically, a closed convex function $f(x)$ is the "
                 r"pointwise supremum of all affine hyperplanes "
                 r"$y^{T}x-\alpha$ lying below its epigraph. The smallest "
                 r"intercept $\alpha$ for a given slope $y$ such that "
                 r"$y^{T}x-\alpha\leq f(x)$ for all $x$ is"),
            display(r"$\alpha=\sup_{x}\left(y^{T}x-f(x)\right)="
                    r"f^{*}(y).$"),
            para(r"Taking the envelope over all slopes $y$ reconstructs "
                 r"$f(x)=\sup_{y}(x^{T}y-f^{*}(y))=f^{**}(x)$."),
            para(r"2. Cauchy's bound and Routh-Hurwitz root "
                 r"localization: for any monic polynomial "
                 r"$P(z)=z^{n}+a_{n-1}z^{n-1}+\cdots+a_{0}=0$, all "
                 r"complex roots lie inside the disk "
                 r"$|z|\leq 1+\max_{k}|a_{k}|$, since for "
                 r"$|z|>1+M$ with $M=\max_{k}|a_{k}|$,"),
            display(r"$|z^{n}|>M\sum_{k=0}^{n-1}|z|^{k}="
                    r"M\frac{|z|^{n}-1}{|z|-1}>"
                    r"\left|\sum_{k=0}^{n-1}a_{k}z^{k}\right|.$"),
        ],
        "9.3": [
            para(r"1. Identity decomposition into parallel and "
                 r"perpendicular vector components: for any unit vector "
                 r"$\hat u$ ($|\hat u|=1$) and any vector "
                 r"$v\in\mathbb{R}^{3}$, applying BAC-CAB to "
                 r"$\hat u\times(v\times\hat u)$ gives the orthogonal "
                 r"decomposition"),
            display(r"$v=\underbrace{(v\cdot\hat u)\hat u}_{v_{\parallel}}+"
                    r"\underbrace{\hat u\times(v\times\hat u)}_{v_{\perp}},"
                    r"\qquad |v_{\perp}|=|v\times\hat u|.$"),
            para(r"Rotating around axis $\hat u$ by angle $\theta$, "
                 r"$v_{\parallel}$ stays fixed while $v_{\perp}$ rotates "
                 r"in the plane $\hat u^{\perp}$, immediately yielding "
                 r"Rodrigues' 3D rotation formula"),
            display(r"$v_{\mathrm{rot}}=(v\cdot\hat u)\hat u+"
                    r"\cos\theta\left[v-(v\cdot\hat u)\hat u\right]+"
                    r"\sin\theta\,(\hat u\times v).$"),
            para(r"2. Linear programming weak and strong duality theorem: "
                 r"every primal LP "
                 r"$\max\{c^{T}x:Ax\leq b,\ x\geq0\}$ has a dual LP "
                 r"$\min\{b^{T}y:A^{T}y\geq c,\ y\geq0\}$. For any "
                 r"feasible $(x,y)$,"),
            display(r"$c^{T}x\leq (y^{T}A)x=y^{T}(Ax)\leq b^{T}y.$"),
            para(r"At optimality, $c^{T}x^{*}=b^{T}y^{*}$ with "
                 r"complementary slackness "
                 r"$y_{i}^{*}(b_{i}-(Ax^{*})_{i})=0$ and "
                 r"$x_{j}^{*}((A^{T}y^{*})_{j}-c_{j})=0$."),
        ],
        "5.2": [
            bullet(r"Standard, general, and diameter equations: center "
                   r"$(h,k)$ and radius $r$, "
                   r"$(x-h)^{2}+(y-k)^{2}=r^{2}$. The general form "
                   r"$S(x,y)=x^{2}+y^{2}+2gx+2fy+c=0$ has center "
                   r"$(-g,-f)$ and radius "
                   r"$r=\sqrt{g^{2}+f^{2}-c}$, requiring "
                   r"$g^{2}+f^{2}\geq c$. The circle on the diameter "
                   r"from $(x_{1},y_{1})$ to $(x_{2},y_{2})$ is"),
            display(r"$(x-x_{1})(x-x_{2})+"
                    r"(y-y_{1})(y-y_{2})=0.$"),
            bullet(r"Intercepts on the coordinate axes: the $x$-intercept "
                   r"length is $2\sqrt{g^{2}-c}$, and the $y$-intercept "
                   r"length is $2\sqrt{f^{2}-c}$."),
            bullet(r"The $T$, $S$, $S_{1}$ master-operator formalism: for "
                   r"$S\equiv x^{2}+y^{2}+2gx+2fy+c=0$ and point "
                   r"$P(x_{1},y_{1})$, define $S_{1}=S(x_{1},y_{1})$ and "
                   r"the polarized linear form "
                   r"$T\equiv xx_{1}+yy_{1}+g(x+x_{1})+f(y+y_{1})+c$:"),
            para(r"1. Position of $P$: inside iff $S_{1}<0$; on the "
                 r"circle iff $S_{1}=0$; outside iff $S_{1}>0$."),
            para(r"2. Length of tangent from external point $P$: "
                 r"$L=\sqrt{S_{1}}$."),
            para(r"3. Tangent at point $P$ on the circle: $T=0$. The "
                 r"slope-form tangent to $x^{2}+y^{2}=r^{2}$ is "
                 r"$y=mx\pm r\sqrt{1+m^{2}}$."),
            para(r"4. Chord of contact of tangents from external point "
                 r"$P$: $T=0$."),
            para(r"5. Chord with given midpoint $P(x_{1},y_{1})$: "
                 r"$T=S_{1}$."),
            para(r"6. Pair of tangents from external point $P$: "
                 r"$SS_{1}=T^{2}$."),
            para(r"7. Director circle (locus of perpendicular tangents): "
                 r"$x^{2}+y^{2}=2r^{2}$."),
            para(r"8. Condition of orthogonality of two circles ($90^{\circ}$ "
                 r"intersection): $r_{1}^{2}+r_{2}^{2}=d^{2}$, equivalently "
                 r"$2g_{1}g_{2}+2f_{1}f_{2}=c_{1}+c_{2}$."),
        ],
        "1.4": [
            para(r"Let $f:A\to B$ with $|A|=m$ and $|B|=n$:"),
            bullet(r"Injective (one-one): $f(x_{1})=f(x_{2})\implies "
                   r"x_{1}=x_{2}$ (analytically, for differentiable $f$, "
                   r"$f'(x)\geq0$ everywhere or $f'(x)\leq0$ everywhere). "
                   r"The number of injective functions is "
                   r"$P(n,m)=\frac{n!}{(n-m)!}$ if $n\geq m$, and $0$ if "
                   r"$n<m$."),
            bullet(r"Surjective (onto): $\operatorname{Range}(f)=B$, "
                   r"meaning for every $y\in B$ there exists $x\in A$ "
                   r"with $f(x)=y$. By inclusion-exclusion (removing "
                   r"functions that miss at least one codomain element), "
                   r"the exact number of onto functions is"),
            display(r"$N_{\mathrm{onto}}(m\to n)="
                    r"\sum_{k=0}^{n}(-1)^{k}\binom{n}{k}(n-k)^{m}="
                    r"n!\,S(m,n),$"),
            para(r"where $S(m,n)$ is the Stirling number of the second "
                 r"kind."),
            bullet(r"Bijective (one-one and onto) and inverse functions: "
                   r"$f:A\to B$ is invertible iff it is a bijection "
                   r"(there are $n!$ such bijections when $m=n$). Its "
                   r"inverse $f^{-1}:B\to A$ satisfies "
                   r"$f^{-1}(f(x))=x$ and $f(f^{-1}(y))=y$. "
                   r"Geometrically, the graph of $y=f^{-1}(x)$ is the "
                   r"reflection of $y=f(x)$ across the line $y=x$."),
            bullet(r"Composition and the shoe-sock inverse rule: for "
                   r"$f:A\to B$ and $g:B\to C$, "
                   r"$(g\circ f)(x)=g(f(x))$. If both are bijections, "
                   r"then $(g\circ f)^{-1}=f^{-1}\circ g^{-1}$."),
            bullet(r"Even-odd decomposition theorem: every function "
                   r"$f:\mathbb{R}\to\mathbb{R}$ on a symmetric domain "
                   r"decomposes uniquely into an even part "
                   r"$f_{e}(-x)=f_{e}(x)$ and an odd part "
                   r"$f_{o}(-x)=-f_{o}(x)$:"),
            display(r"$f(x)=\underbrace{\frac{f(x)+f(-x)}{2}}_{f_{e}(x)}+"
                    r"\underbrace{\frac{f(x)-f(-x)}{2}}_{f_{o}(x)}.$"),
        ],
        "12.3": [
            example("12.1", "Mental-Math Square Roots via 2nd-Order "
                            "Taylor Series"),
            question(r"Use the second-order Taylor expansion of "
                     r"$\sqrt{1+x}$ around $x=0$ to approximate "
                     r"$\sqrt{1.08}$."),
            solution(r"With $\alpha=\frac{1}{2}$, "
                     r"$(1+x)^{1/2}\approx 1+\frac{x}{2}-\frac{x^{2}}{8}$. "
                     r"Plugging in $x=0.08$,"),
            display(r"$\sqrt{1.08}\approx 1+\frac{0.08}{2}-"
                    r"\frac{(0.08)^{2}}{8}="
                    r"1+0.04-0.0008=1.0392,$"),
            para(r"which matches the exact value $1.039230\ldots$"),

            example("12.2", "Complete Numerical Backpropagation Pass"),
            question(r"A neuron computes $z=wx+b$ with $x=2$, $w=0.5$, "
                     r"$b=-1$, applies the sigmoid $a=\sigma(z)$, and "
                     r"measures the loss $L=\frac{1}{2}(a-y)^{2}$ for "
                     r"target $y=1$. Compute $\frac{\partial L}{"
                     r"\partial w}$."),
            solution(r"Forward pass: "
                     r"$z=0.5(2)-1=0$, so $a=\sigma(0)=0.5$ and "
                     r"$L=\frac{1}{2}(0.5-1)^{2}=0.125$."),
            para(r"Backward pass by the chain rule:"),
            display(r"$\frac{\partial L}{\partial w}="
                    r"(a-y)\sigma(z)\left(1-\sigma(z)\right)x="
                    r"(-0.5)(0.25)(2)=-0.25.$"),

            example("12.3", "Delta-Gamma Option Taylor Approximation"),
            question(r"A call option at $S=\text{Rs. }100$ costs "
                     r"$C=\text{Rs. }8.00$, with $\Delta=\frac{"
                     r"\partial C}{\partial S}=0.60$ and "
                     r"$\Gamma=\frac{\partial^{2}C}{\partial S^{2}}=0.04$. "
                     r"Estimate $C(105)$."),
            solution(r"By the second-order Taylor expansion,"),
            display(r"$C(S+\Delta S)\approx C(S)+\Delta(\Delta S)+"
                    r"\frac{1}{2}\Gamma(\Delta S)^{2}="
                    r"8.00+0.60(5)+\frac{1}{2}(0.04)(5^{2})="
                    r"8.00+3.00+0.50=\text{Rs. }11.50.$"),

            example("12.4", "Multivariable Critical Point & Hessian "
                            "Verification"),
            question(r"Find the minimum of "
                     r"$f(x,y)=x^{2}-2xy+3y^{2}-4x+2y+10$ and verify it "
                     r"via the Hessian matrix."),
            solution(r"Setting "
                     r"$\nabla f=\left[2x-2y-4,\ -2x+6y+2\right]^{T}="
                     r"[0,0]^{T}$ gives $x-y=2$ and $4y=2$, hence "
                     r"$(x^{*},y^{*})=(2.5,0.5)$. The Hessian is"),
            display(r"$H=\begin{pmatrix}2&-2\\-2&6\end{pmatrix},"
                    r"\qquad H_{11}=2>0,\qquad "
                    r"\det(H)=12-4=8>0,$"),
            para(r"confirming a strict global minimum."),

            example("12.5", "Breeden-Litzenberger Implied PDF via "
                            "Leibniz's Rule"),
            question(r"Given the discounted call price "
                     r"$C(K)=e^{-rT}\int_{K}^{\infty}(S-K)p(S)\,dS$, "
                     r"apply Leibniz's rule twice with respect to strike "
                     r"$K$ to extract the market-implied density $p(K)$."),
            solution(r"Differentiating once with respect to the lower "
                     r"limit $a(K)=K$,"),
            display(r"$\frac{\partial C}{\partial K}="
                    r"-e^{-rT}\int_{K}^{\infty}p(S)\,dS.$"),
            para(r"Differentiating a second time gives"),
            display(r"$\frac{\partial^{2}C}{\partial K^{2}}="
                    r"e^{-rT}p(K)\implies "
                    r"p(K)=e^{rT}\frac{\partial^{2}C}{\partial K^{2}}.$"),
        ],
        "13.3": [
            example("13.1", "Exact cos(15°) and sin(75°) Without "
                            "Calculator"),
            question(r"Compute $\cos(15^{\circ})$ and "
                     r"$\sin(75^{\circ})$ in exact radical form using "
                     r"$15^{\circ}=45^{\circ}-30^{\circ}$."),
            solution(r"By the angle subtraction formula,"),
            display(r"$\cos(45^{\circ}-30^{\circ})="
                    r"\cos45^{\circ}\cos30^{\circ}+"
                    r"\sin45^{\circ}\sin30^{\circ}="
                    r"\frac{\sqrt{6}+\sqrt{2}}{4}.$"),
            para(r"Since $\sin(75^{\circ})=\cos(15^{\circ})$, both are "
                 r"equal to $\frac{\sqrt{6}+\sqrt{2}}{4}$."),

            example("13.2", "Phase-Shift Wave Peak Finder"),
            question(r"Combine $x(t)=5\cos(3t)-12\sin(3t)$ into a single "
                     r"cosine wave and find its maximum value."),
            solution(r"The amplitude is the Pythagorean hypotenuse "
                     r"$R=\sqrt{5^{2}+(-12)^{2}}=\sqrt{169}=13$, so"),
            display(r"$x(t)=13\cos(3t+\phi),$"),
            para(r"with maximum value $+13$."),

            example("13.3", "Power-Reduction Integral"),
            question(r"Evaluate $\int_{0}^{\pi}\sin^{2}(3x)\,dx$."),
            solution(r"Using $\sin^{2}(3x)=\frac{1-\cos(6x)}{2}$,"),
            display(r"$\int_{0}^{\pi}\sin^{2}(3x)\,dx="
                    r"\int_{0}^{\pi}\frac{1-\cos(6x)}{2}\,dx="
                    r"\left[\frac{x}{2}-\frac{\sin(6x)}{12}\right]_{0}^{\pi}="
                    r"\frac{\pi}{2}.$"),

            example("13.4", "Transformer Sinusoidal Positional Encoding "
                            "Matrix"),
            question(r"Show that advancing position "
                     r"$\mathrm{pos}\to\mathrm{pos}+k$ in "
                     r"$PE(\mathrm{pos})=[\sin(\omega"
                     r"\mathrm{pos}),\cos(\omega\mathrm{pos})]^{T}$ is a "
                     r"linear $2\times2$ orthogonal rotation "
                     r"$M_{k}$ independent of "
                     r"$\mathrm{pos}$."),
            solution(r"By the angle addition formulas,"),
            display(r"$\begin{pmatrix}\sin(\omega"
                    r"(\mathrm{pos}+k))\\\cos(\omega"
                    r"(\mathrm{pos}+k))\end{pmatrix}="
                    r"\begin{pmatrix}\cos(\omega k)&\sin(\omega k)\\"
                    r"-\sin(\omega k)&\cos(\omega k)"
                    r"\end{pmatrix}"
                    r"\begin{pmatrix}\sin(\omega"
                    r"\mathrm{pos})\\\cos(\omega\mathrm{pos})"
                    r"\end{pmatrix},$"),
            para(r"which is precisely "
                 r"$PE(\mathrm{pos}+k)=M_{k}PE(\mathrm{pos})$."),

            example("13.5", "LSTM / GELU Hyperbolic Tanh Derivative"),
            question(r"If a neuron has forward activation "
                     r"$a=\tanh(z)=0.60$, compute "
                     r"$\frac{da}{dz}$."),
            solution(r"Using $\frac{d}{dz}\tanh z=1-\tanh^{2}z$,"),
            display(r"$\frac{da}{dz}=1-a^{2}=1-(0.60)^{2}=0.64.$"),
        ],
        "14.3": [
            example("14.1", "2×2 Inverse & Linear System"),
            question(r"Invert $A=\begin{pmatrix}4&1\\2&3\end{pmatrix}$ and "
                     r"solve $Ax=\begin{pmatrix}9\\12\end{pmatrix}$."),
            solution(r"Since $\det(A)=4(3)-1(2)=10$, swapping the diagonal "
                     r"entries and negating the off-diagonals gives"),
            display(r"$A^{-1}=\frac{1}{10}"
                    r"\begin{pmatrix}3&-1\\-2&4\end{pmatrix}.$"),
            para(r"Hence"),
            display(r"$x=A^{-1}b=\frac{1}{10}"
                    r"\begin{pmatrix}3&-1\\-2&4\end{pmatrix}"
                    r"\begin{pmatrix}9\\12\end{pmatrix}="
                    r"\frac{1}{10}\begin{pmatrix}15\\30\end{pmatrix}="
                    r"\begin{pmatrix}1.5\\3.0\end{pmatrix}.$"),

            example("14.2", "Orthogonal Projection onto a Line"),
            question(r"Project $y=\begin{pmatrix}3\\4\end{pmatrix}$ onto "
                     r"the line spanned by $a=\begin{pmatrix}1\\2\end{pmatrix}$ "
                     r"and verify the error vector is orthogonal to "
                     r"$a$."),
            solution(r"The projection coefficient is "
                     r"$\frac{a^{T}y}{a^{T}a}=\frac{1(3)+2(4)}{1^{2}+2^{2}}="
                     r"\frac{11}{5}$, so"),
            display(r"$\hat y=\frac{a^{T}y}{a^{T}a}a="
                    r"\frac{11}{5}\begin{pmatrix}1\\2\end{pmatrix}="
                    r"\begin{pmatrix}2.2\\4.4\end{pmatrix}.$"),
            para(r"The residual is "
                 r"$y-\hat y=\begin{pmatrix}0.8\\-0.4\end{pmatrix}$, and "
                 r"$a^{T}(y-\hat y)=1(0.8)+2(-0.4)=0$, confirming "
                 r"orthogonality."),

            example("14.3", "Singular Values & Frobenius Norm"),
            question(r"Find the singular values $\sigma_{1},\sigma_{2}$ and "
                     r"Frobenius norm of "
                     r"$A=\begin{pmatrix}3&0\\4&0\end{pmatrix}$."),
            solution(r"Compute"),
            display(r"$A^{T}A=\begin{pmatrix}25&0\\0&0\end{pmatrix},$"),
            para(r"whose eigenvalues are $25$ and $0$, so "
                 r"$\sigma_{1}=5$, $\sigma_{2}=0$, and"),
            display(r"$\|A\|_{F}=\sqrt{3^{2}+4^{2}}="
                    r"\sqrt{\sigma_{1}^{2}+\sigma_{2}^{2}}=5.$"),

            example("14.4", "Cholesky Factorization Σ = LLᵀ"),
            question(r"Compute the lower-triangular Cholesky factor "
                     r"$L$ of $\Sigma=\begin{pmatrix}4&6\\6&25\end{pmatrix}$."),
            solution(r"Write "
                     r"$L=\begin{pmatrix}l_{11}&0\\l_{21}&l_{22}\end{pmatrix}$. "
                     r"From $l_{11}^{2}=4$, $l_{11}l_{21}=6$, and "
                     r"$l_{21}^{2}+l_{22}^{2}=25$, we get "
                     r"$l_{11}=2$, $l_{21}=3$, and"),
            display(r"$l_{22}=\sqrt{25-9}=4\implies L="
                    r"\begin{pmatrix}2&0\\3&4\end{pmatrix}.$"),

            example("14.5", "Quadratic Minimization via Matrix Calculus"),
            question(r"Minimize "
                     r"$f(x)=\frac{1}{2}x^{T}\begin{pmatrix}4&0\\0&2\end{pmatrix}"
                     r"x-\begin{pmatrix}8\\6\end{pmatrix}^{T}x$."),
            solution(r"Setting the gradient to zero gives"),
            display(r"$\nabla_{x}f="
                    r"\begin{pmatrix}4&0\\0&2\end{pmatrix}x-"
                    r"\begin{pmatrix}8\\6\end{pmatrix}=0,$"),
            para(r"so $4x_{1}=8$ and $2x_{2}=6$, hence "
                 r"$x^{*}=\begin{pmatrix}2\\3\end{pmatrix}$."),
        ],
        "19.3": [
            example("19.1", "2-Token Causal Self-Attention by Hand"),
            question(r"For $Q=K=\begin{pmatrix}1&0\\1&0\end{pmatrix}$ "
                     r"($d_{k}=1$) and "
                     r"$V=\begin{pmatrix}10&20\\30&40\end{pmatrix}$, compute "
                     r"the causally masked attention output $O$."),
            solution(r"The masked score matrix is"),
            display(r"$S=\begin{pmatrix}1&-\infty\\1&1\end{pmatrix},$"),
            para(r"whose row-wise softmax is"),
            display(r"$A=\begin{pmatrix}1&0\\0.5&0.5\end{pmatrix},$"),
            para(r"and then"),
            display(r"$O=AV="
                    r"\begin{pmatrix}1&0\\0.5&0.5\end{pmatrix}"
                    r"\begin{pmatrix}10&20\\30&40\end{pmatrix}="
                    r"\begin{pmatrix}10&20\\20&30\end{pmatrix}.$"),

            example("19.2", "RMSNorm Forward Pass"),
            question(r"Apply RMSNorm ($\varepsilon=0$, $\gamma=1$) to "
                     r"$x=[1,2,2,3]^{T}$."),
            solution(r"Compute"),
            display(r"$\mathrm{RMS}(x)=\sqrt{\frac{1^{2}+2^{2}+2^{2}+3^{2}}{4}}="
                    r"\sqrt{4.5}\approx2.1213,$"),
            para(r"so"),
            display(r"$\hat x=\frac{x}{2.1213}\approx"
                    r"[0.471,\ 0.943,\ 0.943,\ 1.414]^{T}.$"),

            example("19.3", "Softmax Vector-Jacobian Product"),
            question(r"Given $p=[0.5,0.3,0.2]^{T}$ and upstream gradient "
                     r"$g=[2,0,-1]^{T}$, compute "
                     r"$\frac{\partial L}{\partial z}=J_{\mathrm{softmax}}g$."),
            solution(r"First, "
                     r"$p^{T}g=0.5(2)+0.3(0)+0.2(-1)=0.80$. Hence"),
            display(r"$J_{\mathrm{softmax}}g=p\odot(g-0.80\mathbf{1})="
                    r"[0.60,\ -0.24,\ -0.36]^{T}.$"),

            example("19.4", "LoRA Parameter Compression on 4096 × 4096 "
                           "Weight Matrix"),
            question(r"Compare the parameter count of "
                     r"$W\in\mathbb{R}^{4096\times4096}$ with rank-16 "
                     r"LoRA matrices $B\in\mathbb{R}^{4096\times16}$ and "
                     r"$A\in\mathbb{R}^{16\times4096}$."),
            solution(r"The full matrix has "
                     r"$4096^{2}=16{,}777{,}216$ parameters. LoRA "
                     r"$BA$ has"),
            display(r"$2\times4096\times16=131{,}072$ parameters,$"),
            para(r"which is $0.78\%$ of the full size, $128\times$ "
                 r"smaller."),

            example("19.5", "FlashAttention 2-Tile Online Softmax Update"),
            question(r"Combine Tile 1 with "
                     r"$z^{(1)}=[1,2]$ ($m_{1}=2$, "
                     r"$\ell_{1}=e^{-1}+1$) and Tile 2 with "
                     r"$z^{(2)}=[4,3]$ ($m_{2}=4$, "
                     r"$\ell_{2}=1+e^{-1}$)."),
            solution(r"The global maximum is $m=4$, so"),
            display(r"$\ell_{\mathrm{new}}=e^{2-4}(e^{-1}+1)+"
                    r"e^{4-4}(1+e^{-1})="
                    r"e^{-3}+e^{-2}+1+e^{-1}="
                    r"\sum_{i=1}^{4}e^{z_{i}-4},$"),
            para(r"which is the exact online-softmax denominator without "
                 r"materializing the full row."),
        ],
        "1.6": [
            example("1.1", "Three-Set Inclusion-Exclusion Survey "
                           "Optimization"),
            question(r"In a cohort of 200 engineering students, 120 code in "
                     r"Python (P), 90 in C++ (C), 70 in Rust (R), 50 in both "
                     r"P and C, 40 in both C and R, 30 in both P and R, and "
                     r"20 in all three languages. Find: (a) how many code "
                     r"in at least one language, (b) how many code in none, "
                     r"(c) how many code in Python only, and (d) how many "
                     r"code in exactly one language."),
            solution(r"(a) By the three-set principle of "
                     r"inclusion-exclusion,"),
            display(r"$|P\cup C\cup R|=120+90+70-(50+40+30)+20=180.$"),
            para(r"(b) Coding in none: "
                 r"$|(P\cup C\cup R)^{c}|=200-180=20$."),
            para(r"(c) Python only:"),
            display(r"$|P\setminus(C\cup R)|=|P|-|P\cap C|-|P\cap R|+"
                    r"|P\cap C\cap R|=120-50-30+20=60.$"),
            para(r"(d) Similarly, "
                 r"$|C\ \mathrm{only}|=90-50-40+20=20$ and "
                 r"$|R\ \mathrm{only}|=70-40-30+20=20$. Hence exactly one "
                 r"language: $60+20+20=100$."),

            example("1.2", "Proving an Equivalence Relation on Ordered "
                           "Pairs"),
            question(r"Let $A=\mathbb{N}\times\mathbb{N}$ and define "
                     r"$R$ on $A$ by "
                     r"$(a,b)R(c,d)\iff ad(b+c)=bc(a+d)$. Prove that "
                     r"$R$ is an equivalence relation on $A$."),
            solution(r"Divide both sides of $ad(b+c)=bc(a+d)$ by the "
                     r"positive integer $abcd>0$:"),
            display(r"$\frac{b+c}{bc}=\frac{a+d}{ad}\iff"
                    r"\frac{1}{b}+\frac{1}{c}=\frac{1}{a}+\frac{1}{d}\iff"
                    r"\frac{1}{a}-\frac{1}{b}=\frac{1}{c}-\frac{1}{d}.$"),
            para(r"Define $g(x,y)=\frac{1}{x}-\frac{1}{y}$. Then "
                 r"$(a,b)R(c,d)\iff g(a,b)=g(c,d)$."),
            bullet(r"Reflexive: $g(a,b)=g(a,b)$, so $(a,b)R(a,b)$ for "
                   r"all $(a,b)\in A$."),
            bullet(r"Symmetric: $g(a,b)=g(c,d)\implies g(c,d)=g(a,b)$, "
                   r"so $(c,d)R(a,b)$."),
            bullet(r"Transitive: if $g(a,b)=g(c,d)$ and "
                   r"$g(c,d)=g(e,f)$, then $g(a,b)=g(e,f)$, so "
                   r"$(a,b)R(e,f)$."),
            para(r"Hence $R$ is an equivalence relation."),

            example("1.3", "Domain & Range of a Rational Quadratic Function"),
            question(r"Find the exact domain and range of "
                     r"$f(x)=\frac{x^{2}-x+1}{x^{2}+x+1}$."),
            solution(r"Domain: the denominator "
                     r"$x^{2}+x+1=\left(x+\frac{1}{2}\right)^{2}+"
                     r"\frac{3}{4}>0$ for every $x\in\mathbb{R}$, so "
                     r"$\operatorname{Domain}(f)=\mathbb{R}$."),
            para(r"Range: set $y=\frac{x^{2}-x+1}{x^{2}+x+1}$ and "
                 r"cross-multiply:"),
            display(r"$(y-1)x^{2}+(y+1)x+(y-1)=0.$"),
            para(r"If $y=1$, this gives $2x=0$, so $x=0$ is feasible. "
                 r"For $y\neq1$, the quadratic in $x$ must have "
                 r"non-negative discriminant:"),
            display(r"$(y+1)^{2}-4(y-1)^{2}\geq0\iff "
                    r"(3-y)(3y-1)\geq0\iff (y-3)(3y-1)\leq0.$"),
            para(r"Thus $y\in\left[\frac{1}{3},3\right]$, and "
                 r"$\operatorname{Range}(f)=\left[\frac{1}{3},3\right]$."),

            example("1.4", "Bijection Proof & Inverse of a Quadratic Mapping"),
            question(r"Prove that $f:[1,\infty)\to[2,\infty)$ defined by "
                     r"$f(x)=x^{2}-2x+3$ is a bijection, find "
                     r"$f^{-1}(y)$, and solve $f(x)=f^{-1}(x)$."),
            solution(r"Complete the square: "
                     r"$f(x)=(x-1)^{2}+2$."),
            para(r"Injectivity on $[1,\infty)$: if $f(x_{1})=f(x_{2})$, "
                 r"then $(x_{1}-1)^{2}=(x_{2}-1)^{2}$. Since both "
                 r"$x_{i}-1\geq0$, this gives $x_{1}=x_{2}$."),
            para(r"Surjectivity onto $[2,\infty)$ and the inverse: for "
                 r"any $y\geq2$, solve $(x-1)^{2}+2=y$; taking the "
                 r"non-negative root gives"),
            display(r"$f^{-1}(y)=1+\sqrt{y-2}.$"),
            para(r"Finally, $f(x)=f^{-1}(x)$ lies on the diagonal "
                 r"$y=x$:"),
            display(r"$x^{2}-2x+3=x\iff x^{2}-3x+3=0,\qquad "
                    r"D=9-12=-3<0,$"),
            para(r"so there is no real solution."),

            example("1.5", "Functional Equation via Linear System Elimination"),
            question(r"If a function $f:\mathbb{R}\setminus\{0\}\to"
                     r"\mathbb{R}$ satisfies "
                     r"$2f(x)+3f(1/x)=x^{2}-4$ for all $x\neq0$, find "
                     r"the explicit formula for $f(x)$ and evaluate "
                     r"$f(2)$."),
            solution(r"Replace $x$ by $1/x$ to obtain a second equation:"),
            display(r"$2f(x)+3f(1/x)=x^{2}-4,\qquad "
                    r"3f(x)+2f(1/x)=\frac{1}{x^{2}}-4.$"),
            para(r"Eliminating $f(1/x)$ gives"),
            display(r"$5f(x)=\frac{3}{x^{2}}-2x^{2}-4\implies "
                    r"f(x)=\frac{3}{5x^{2}}-\frac{2x^{2}}{5}-"
                    r"\frac{4}{5}.$"),
            para(r"At $x=2$,"),
            display(r"$f(2)=\frac{3}{20}-\frac{8}{5}-\frac{4}{5}="
                    r"-\frac{9}{4}.$"),

            example("1.6", "Greatest Integer & Fractional Part Equation"),
            question(r"Solve the equation $4\{x\}=x+\lfloor x\rfloor$ for "
                     r"all real $x\in\mathbb{R}$."),
            solution(r"Write $x=\lfloor x\rfloor+\{x\}=n+\{x\}$ with "
                     r"$n\in\mathbb{Z}$ and $0\leq\{x\}<1$. Then"),
            display(r"$4\{x\}=2n+\{x\}\implies 3\{x\}=2n\implies "
                    r"\{x\}=\frac{2n}{3}.$"),
            para(r"The constraint $0\leq\frac{2n}{3}<1$ gives "
                 r"$0\leq n<\frac{3}{2}$, so $n\in\{0,1\}$."),
            para(r"For $n=0$, $\{x\}=0$, so $x=0$. For $n=1$, "
                 r"$\{x\}=\frac{2}{3}$, so $x=1+\frac{2}{3}=\frac{5}{3}$."),
            display(r"$x\in\left\{0,\frac{5}{3}\right\}.$"),
        ],
        "3.4": [
            example("3.1", "Mathematical Induction Proof of Divisibility"),
            question(r"Prove by the principle of mathematical induction "
                     r"that $P(n)$: $10^{2n-1}+1$ is divisible by $11$ "
                     r"for all $n\in\mathbb{N}$."),
            solution(r"Base case $n=1$: "
                     r"$10^{1}+1=11$, divisible by $11$."),
            para(r"Inductive hypothesis: assume "
                 r"$10^{2k-1}+1=11m$ for some $m\in\mathbb{Z}$, so "
                 r"$10^{2k-1}=11m-1$."),
            para(r"Inductive step, $n=k+1$:"),
            display(r"$10^{2(k+1)-1}+1=10^{2k+1}+1=100\cdot10^{2k-1}+1="
                    r"100(11m-1)+1=1100m-99=11(100m-9),$"),
            para(r"which is a multiple of $11$. By PMI, $P(n)$ holds for "
                 r"all $n\in\mathbb{N}$."),

            example("3.2", "Dictionary Rank with Repeated Letters"),
            question(r"Find the exact alphabetical dictionary rank of the "
                     r"word COCHIN and the word SMALL when all "
                     r"permutations of their letters are arranged in "
                     r"alphabetical order."),
            solution(r"COCHIN: the alphabetical order is "
                     r"$C,C,H,I,N,O$. Every word starting with "
                     r"$CC,CH,CI,CN$ comes before the $CO$ block, and each "
                     r"such block has $4! = 24$ words, so "
                     r"$4\times24=96$ words precede the $CO$ block. "
                     r"The first word in the $CO$ block is COCHIN itself."),
            display(r"$\operatorname{rank}(\mathrm{COCHIN})=96+1=97.$"),
            para(r"SMALL: the alphabetical order is $A,L,L,M,S$. Count "
                 r"the words before SMALL:"),
            bullet(r"Starting with A: $\frac{4!}{2!}=12$ words."),
            bullet(r"Starting with L: $4!=24$ words."),
            bullet(r"Starting with M: $\frac{4!}{2!}=12$ words."),
            bullet(r"Starting with SA: $\frac{3!}{2!}=3$ words."),
            bullet(r"Starting with SL: $3!=6$ words."),
            display(r"$\operatorname{rank}(\mathrm{SMALL})="
                    r"12+24+12+3+6+1=58.$"),

            example("3.3", "Constant Term & Numerically Greatest Term in "
                           "Binomial Expansion"),
            question(r"(a) Find the term independent of $x$ in "
                     r"$\left(\frac{3}{2}x^{2}-\frac{1}{3x}\right)^{9}$. "
                     r"(b) Find the numerically greatest term in "
                     r"$(2+3x)^{9}$ when $x=\frac{2}{3}$."),
            solution(r"(a) The general term is "
                     r"$T_{r+1}=\binom{9}{r}\left(\frac{3}{2}x^{2}\right)^{9-r}"
                     r"\left(-\frac{1}{3x}\right)^{r}$. Setting the power of "
                     r"$x$ to zero, $18-3r=0$, gives $r=6$:"),
            display(r"$T_{7}=\binom{9}{6}\left(\frac{3}{2}\right)^{3}"
                    r"\left(\frac{1}{3}\right)^{6}=\frac{7}{18}.$"),
            para(r"(b) Write "
                 r"$(2+3x)^{9}=\left(2+2\right)^{9}$ because $x="
                 r"\frac{2}{3}$. The ratio of consecutive terms is"),
            display(r"$\frac{T_{r+1}}{T_{r}}=\frac{10-r}{r}.$"),
            para(r"This is greater than $1$ for $r<5$ and equal to $1$ "
                 r"at $r=5$. Hence the binomial coefficients increase up "
                 r"to $r=4,5$, and the numerically greatest terms are the "
                 r"5th and 6th terms, both equal to "
                 r"$\binom{9}{4}2^{9}=64{,}512$."),

            example("3.4", "Method of Telescoping Differences for Fractional "
                           "Series"),
            question(r"Find the closed-form sum of the first $n$ terms and "
                     r"the infinite sum of "
                     r"$S_{n}=\sum_{k=1}^{n}\frac{1}{k(k+1)(k+2)}$."),
            solution(r"Since $(k+2)-k=2$,"),
            display(r"$\frac{1}{k(k+1)(k+2)}="
                    r"\frac{1}{2}\left[\frac{1}{k(k+1)}-"
                    r"\frac{1}{(k+1)(k+2)}\right].$"),
            para(r"Summing telescopes all intermediate terms:"),
            display(r"$S_{n}=\frac{1}{2}\left[\frac{1}{1\cdot2}-"
                    r"\frac{1}{(n+1)(n+2)}\right]="
                    r"\frac{1}{4}-\frac{1}{2(n+1)(n+2)}.$"),
            display(r"$S_{\infty}=\lim_{n\to\infty}S_{n}="
                    r"\frac{1}{4}.$"),

            example("3.5", "AM-GM Inequality with Weighted Splitting"),
            question(r"If $x,y>0$ and $x^{2}y^{3}=108$, find the minimum "
                     r"possible value of $3x+2y$."),
            solution(r"Split $3x$ into two equal parts $\frac{3x}{2}$, "
                 r"$\frac{3x}{2}$ and $2y$ into three equal parts "
                 r"$\frac{2y}{3}$, $\frac{2y}{3}$, $\frac{2y}{3}$. "
                 r"By AM-GM,"),
            display(r"$\frac{3x+2y}{5}\geq "
                    r"\left[\left(\frac{3x}{2}\right)^{2}"
                    r"\left(\frac{2y}{3}\right)^{3}\right]^{1/5}="
                    r"(72)^{1/5},$"),
            para(r"with equality when "
                 r"$\frac{3x}{2}=\frac{2y}{3}$, i.e. $9x=4y$. Hence the "
                 r"minimum is $5\sqrt[5]{72}$."),

            example("3.6", "Derangements & Hat-Check Probability"),
            question(r"Six letters are placed at random into six addressed "
                     r"envelopes. Find (a) the number of ways no letter "
                     r"goes into its right envelope, and (b) the number of "
                     r"ways exactly two letters go into their right "
                     r"envelopes."),
            solution(r"(a) The derangement number of $6$ objects is"),
            display(r"$D_{6}=6!\left(1-1+\frac{1}{2!}-\frac{1}{3!}+"
                    r"\frac{1}{4!}-\frac{1}{5!}+\frac{1}{6!}\right)=265.$"),
            para(r"(b) Choose the two correctly placed letters in "
                 r"$\binom{6}{2}$ ways, and derange the remaining four "
                 r"letters in $D_{4}=9$ ways:"),
            display(r"$\binom{6}{2}\times9=15\times9=135.$"),
        ],
        "4.3": [
            example("4.1", "Vandermonde & Cyclic Determinant Factorization"),
            question(r"Without expanding directly, factor completely the "
                     r"determinant $\Delta = \det \begin{pmatrix} "
                     r"1 & a & a^{3} \\ 1 & b & b^{3} \\ 1 & c & c^{3} "
                     r"\end{pmatrix}$."),
            solution(r"Apply the row operations $R_{2} \to R_{2} - R_{1}$ and "
                     r"$R_{3} \to R_{3} - R_{1}$, then factor $b - a$ from "
                     r"row 2 and $c - a$ from row 3, using "
                     r"$x^{3} - y^{3} = (x - y)(x^{2} + xy + y^{2})$:"),
            display(r"$\Delta = \det \begin{pmatrix} "
                    r"1 & a & a^{3} \\ 0 & b - a & b^{3} - a^{3} \\ "
                    r"0 & c - a & c^{3} - a^{3} \end{pmatrix} = "
                    r"(b - a)(c - a) \det \begin{pmatrix} "
                    r"1 & a & a^{3} \\ 0 & 1 & b^{2} + ab + a^{2} \\ "
                    r"0 & 1 & c^{2} + ac + a^{2} \end{pmatrix}.$"),
            para(r"Expand along the first column (only the top-left entry "
                 r"survives) and evaluate the remaining $2 \times 2$ "
                 r"determinant:"),
            display(r"$\Delta = (b - a)(c - a) "
                    r"\left[(c^{2} + ac + a^{2}) - (b^{2} + ab + a^{2})\right] = "
                    r"(b - a)(c - a) \left[(c^{2} - b^{2}) + a(c - b)\right] = "
                    r"(b - a)(c - a)(c - b)(a + b + c).$"),
            para(r"Since $(b - a)(c - b) = (a - b)(b - c)$, the determinant "
                 r"factors completely as:"),
            display(r"$\Delta = (a - b)(b - c)(c - a)(a + b + c).$"),

            example("4.2", "Cayley-Hamilton Theorem for Inverse & Matrix Powers"),
            question(r"For $A = \begin{pmatrix} 1 & 0 & 2 \\ 0 & 2 & 1 \\ "
                     r"2 & 0 & 3 \end{pmatrix}$, verify that "
                     r"$A^{3} - 6A^{2} + 7A + 2I = 0$, and hence find "
                     r"$A^{-1}$."),
            solution(r"Compute the characteristic polynomial "
                     r"$\det(A - \lambda I)$ by expanding along the second "
                     r"column (only the $(2,2)$ entry is non-zero):"),
            display(r"$\det(A - \lambda I) = (2 - \lambda) "
                    r"\det \begin{pmatrix} 1 - \lambda & 2 \\ 2 & 3 - \lambda "
                    r"\end{pmatrix} = (2 - \lambda)\left[(1 - \lambda)(3 - \lambda) - 4\right] = "
                    r"(2 - \lambda)(\lambda^{2} - 4\lambda - 1) = "
                    r"-\lambda^{3} + 6\lambda^{2} - 7\lambda - 2.$"),
            para(r"The characteristic equation is therefore "
                 r"$\lambda^{3} - 6\lambda^{2} + 7\lambda + 2 = 0$, so by the "
                 r"Cayley-Hamilton Theorem $A$ satisfies its own "
                 r"characteristic equation:"),
            display(r"$A^{3} - 6A^{2} + 7A + 2I = 0.$"),
            para(r"Since $\det(A) = -2 \neq 0$, $A$ is invertible. Multiply "
                 r"the Cayley-Hamilton identity by $A^{-1}$ and rearrange:"),
            display(r"$A^{2} - 6A + 7I + 2A^{-1} = 0 \implies "
                    r"2A^{-1} = -A^{2} + 6A - 7I.$"),
            para(r"Now $A^{2} = \begin{pmatrix} 5 & 0 & 8 \\ 2 & 4 & 5 \\ "
                 r"8 & 0 & 13 \end{pmatrix}$ and $6A = \begin{pmatrix} "
                 r"6 & 0 & 12 \\ 0 & 12 & 6 \\ 12 & 0 & 18 \end{pmatrix}$, "
                 r"so:"),
            display(r"$2A^{-1} = -\begin{pmatrix} 5 & 0 & 8 \\ 2 & 4 & 5 \\ "
                    r"8 & 0 & 13 \end{pmatrix} "
                    r"+ \begin{pmatrix} 6 & 0 & 12 \\ 0 & 12 & 6 \\ "
                    r"12 & 0 & 18 \end{pmatrix} "
                    r"- 7\begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ "
                    r"0 & 0 & 1 \end{pmatrix} "
                    r"= \begin{pmatrix} -6 & 0 & 4 \\ -2 & 1 & 1 \\ "
                    r"4 & 0 & -2 \end{pmatrix},$"),
            display(r"$A^{-1} = \frac{1}{2}\begin{pmatrix} -6 & 0 & 4 \\ "
                    r"-2 & 1 & 1 \\ 4 & 0 & -2 \end{pmatrix} "
                    r"= \begin{pmatrix} -3 & 0 & 2 \\ -1 & \frac{1}{2} & "
                    r"\frac{1}{2} \\ 2 & 0 & -1 \end{pmatrix}.$"),
            para(r"Check: $AA^{-1} = I_{3}$."),

            example("4.3", "Complete Parametric Analysis of a 3 × 3 Linear System"),
            question(r"Find all values of $(\lambda, \mu)$ for which the "
                     r"system $x + y + z = 6$, $x + 2y + 3z = 10$, "
                     r"$x + 2y + \lambda z = \mu$ has (a) a unique solution, "
                     r"(b) no solution, and (c) infinitely many solutions."),
            solution(r"Subtract equation 2 from equation 3 to eliminate "
                     r"$x$ and $y$:"),
            display(r"$(\lambda - 3)z = \mu - 10, \qquad "
                    r"\Delta = \det \begin{pmatrix} 1 & 1 & 1 \\ 1 & 2 & 3 \\ "
                    r"1 & 2 & \lambda \end{pmatrix} = \lambda - 3,$"),
            para(r"where the determinant is computed as "
                 r"$1(2\lambda - 6) - 1(\lambda - 3) + 1(2 - 2) = \lambda - 3$."),
            bullet(r"(a) Unique solution: $\Delta \neq 0 \iff \lambda \neq 3$, "
                   r"with $\mu \in \mathbb{R}$ arbitrary."),
            bullet(r"(b) No solution: $\lambda = 3$ and $\mu \neq 10$."),
            bullet(r"(c) Infinitely many solutions: $\lambda = 3$ and "
                   r"$\mu = 10$; equations 2 and 3 coincide, leaving two "
                   r"independent equations in three unknowns."),

            example("4.4", "Nested Adjoint & Determinant Identity Problem"),
            question(r"Let $A$ be a $3 \times 3$ matrix with $|A| = 4$. "
                     r"Evaluate (a) $|2A^{-1}|$, (b) $|\operatorname{adj}(3A)|$, "
                     r"and (c) $|\operatorname{adj}(\operatorname{adj}(2A))|$."),
            solution(r"Use the facts $|kM| = k^{n}|M|$, "
                     r"$|M^{-1}| = |M|^{-1}$, and "
                     r"$|\operatorname{adj}(M)| = |M|^{\,n - 1}$ for an "
                     r"$n \times n$ matrix $M$; here $n = 3$ and $|A| = 4$."),
            bullet(r"(a) $|2A^{-1}| = 2^{3}|A^{-1}| = "
                   r"\frac{8}{4}=2$."),
            bullet(r"(b) $|3A| = 3^{3}|A| = 27 \cdot 4 = 108$, so "
                   r"$|\operatorname{adj}(3A)| = |3A|^{\,2} = 108^{2} = "
                   r"11{,}664$."),
            bullet(r"(c) Applying $|\operatorname{adj}(M)| = |M|^{\,2}$ twice "
                   r"gives $|\operatorname{adj}(\operatorname{adj}(M))| = "
                   r"|M|^{\,4}$ for any $3 \times 3$ matrix $M$. With "
                   r"$M = 2A$, $|2A| = 2^{3}|A| = 32$, hence:"),
            display(r"$|\operatorname{adj}(\operatorname{adj}(2A))| = "
                    r"|2A|^{\,4} = 32^{4} = 2^{20} = 1{,}048{,}576.$"),

            example("4.5", "Rank-1 Perturbation Determinant"),
            question(r"Evaluate $\Delta = \det \begin{pmatrix} "
                     r"1 + a & 1 & 1 \\ 1 & 1 + b & 1 \\ 1 & 1 & 1 + c "
                     r"\end{pmatrix}$ for non-zero $a$, $b$, $c$."),
            solution(r"Factor $a$, $b$, $c$ from rows 1, 2, 3 respectively:"),
            display(r"$\Delta = abc \det \begin{pmatrix} "
                    r"1 + \frac{1}{a} & \frac{1}{a} & \frac{1}{a} \\ "
                    r"\frac{1}{b} & 1 + \frac{1}{b} & \frac{1}{b} \\ "
                    r"\frac{1}{c} & \frac{1}{c} & 1 + \frac{1}{c} "
                    r"\end{pmatrix}.$"),
            para(r"Add rows 2 and 3 to row 1, then factor "
                 r"$1 + \frac{1}{a} + \frac{1}{b} + \frac{1}{c}$ out of "
                 r"row 1:"),
            display(r"$\Delta = abc\left(1 + \frac{1}{a} + \frac{1}{b} + "
                    r"\frac{1}{c}\right) \det \begin{pmatrix} "
                    r"1 & 1 & 1 \\ "
                    r"\frac{1}{b} & 1 + \frac{1}{b} & \frac{1}{b} \\ "
                    r"\frac{1}{c} & \frac{1}{c} & 1 + \frac{1}{c} "
                    r"\end{pmatrix}.$"),
            para(r"Subtract column 1 from columns 2 and 3; the matrix becomes "
                 r"lower triangular with 1s on the diagonal, so its determinant "
                 r"is $1$. Therefore:"),
            display(r"$\Delta = abc\left(1 + \frac{1}{a} + \frac{1}{b} + "
                    r"\frac{1}{c}\right) = abc + ab + bc + ca.$"),

            example("4.6", "2D Rotation Matrix Group Property by Induction"),
            question(r"Let $R(\theta) = \begin{pmatrix} \cos\theta & "
                     r"-\sin\theta \\ \sin\theta & \cos\theta \end{pmatrix}$. "
                     r"Prove that $R(\alpha)R(\beta) = R(\alpha + \beta)$ and "
                     r"evaluate $\left[R(\pi/12)\right]^{24}$."),
            solution(r"Multiply the two matrices and apply the "
                     r"compound-angle identities:"),
            display(r"$R(\alpha)R(\beta) = \begin{pmatrix} "
                    r"\cos(\alpha + \beta) & -\sin(\alpha + \beta) \\ "
                    r"\sin(\alpha + \beta) & \cos(\alpha + \beta) "
                    r"\end{pmatrix} = R(\alpha + \beta).$"),
            para(r"By induction, $[R(\theta)]^{n} = R(n\theta)$. Hence"),
            display(r"$\left[R\left(\frac{\pi}{12}\right)\right]^{24} = "
                    r"R(2\pi) = I_{2}.$"),
        ],
        "5.5": [
            example("5.1", "Foot of Perpendicular, Mirror Image & "
                           "Reflection of a Light Ray"),
            question(r"(a) Find the foot of the perpendicular $M$ and the mirror "
                     r"image $Q$ of the point $P(1,-2)$ in the line "
                     r"$2x-3y+5=0$. (b) A ray of light from $A(1,2)$ reflects off "
                     r"the $x$-axis at $R(x_{0},0)$ and passes through $B(5,3)$. "
                     r"Find $x_{0}$."),
            solution(r"(a) Here $a=2$, $b=-3$, $c=5$, and "
                     r"$ax_{1}+by_{1}+c=2(1)-3(-2)+5=13$, with "
                     r"$a^{2}+b^{2}=13$:"),
            display(r"$\frac{h-1}{2}=\frac{k+2}{-3}=-1\implies "
                    r"M(h,k)=(-1,1).$"),
            para(r"For the mirror image $Q(x',y')$, double the right-hand side "
                 r"to $-2$:"),
            display(r"$\frac{x'-1}{2}=\frac{y'+2}{-3}=-2\implies "
                    r"Q(x',y')=(-3,4).$"),
            para(r"(b) By the Law of Reflection, the reflected ray passes through "
                 r"$B$ iff the line joining $B(5,3)$ and the mirror image of "
                 r"$A(1,2)$ across the $x$-axis—namely $A'(1,-2)$—intersects the "
                 r"$x$-axis at $R$. The line $A'B$ is"),
            display(r"$y-(-2)=\frac{5}{4}(x-1).$"),
            para(r"Setting $y=0$ gives "
                 r"$2=\frac{5}{4}(x_{0}-1)\implies x_{0}=\frac{13}{5}=2.6$."),

            example("5.2", "Orthocenter & Circumcenter of a Triangle"),
            question(r"Find the circumcenter $O$, centroid $G$, and orthocenter "
                     r"$H$ of $\triangle ABC$ with vertices $A(0,0)$, $B(6,0)$, "
                     r"$C(0,8)$."),
            solution(r"Since $AB$ is horizontal and $AC$ is vertical, "
                     r"$\angle A=90^{\circ}$."),
            para(r"1. Orthocenter $H$: in a right-angled triangle, the altitudes "
                 r"meet at the right-angle vertex, so $H=(0,0)$."),
            para(r"2. Circumcenter $O$: in a right-angled triangle, the "
                 r"circumcenter is the midpoint of the hypotenuse $BC$:"),
            display(r"$O=\left(\frac{6+0}{2},\frac{0+8}{2}\right)=(3,4),"
                    r"\qquad R=5.$"),
            para(r"3. Centroid $G$:"),
            display(r"$G=\left(\frac{0+6+0}{3},\frac{0+0+8}{3}\right)="
                    r"\left(2,\frac{8}{3}\right).$"),
            para(r"Check Euler's relation $H=3G-2O$: "
                 r"$3G-2O=(6,8)-(6,8)=(0,0)=H$."),

            example("5.3", "Common Tangents & Orthogonal Circle Construction"),
            question(r"Find the equation of the circle passing through "
                     r"$(0,0)$ that cuts both circles "
                     r"$x^{2}+y^{2}-4x+6y+10=0$ and "
                     r"$x^{2}+y^{2}+12y+6=0$ orthogonally."),
            solution(r"Let the required circle be "
                     r"$x^{2}+y^{2}+2gx+2fy+c=0$. Since it passes through "
                     r"$(0,0)$, $c=0$. Apply the orthogonality condition "
                     r"$2gg_{i}+2ff_{i}=c+c_{i}$:"),
            para(r"1. With circle 1 ($g_{1}=-2,f_{1}=3,c_{1}=10$): "
                 r"$-2g+3f=5$."),
            para(r"2. With circle 2 ($g_{2}=0,f_{2}=6,c_{2}=6$): "
                 r"$12f=6\implies f=\frac{1}{2}$."),
            para(r"Then $-2g+\frac{3}{2}=5\implies g=-\frac{7}{4}$. "
                 r"Thus"),
            display(r"$x^{2}+y^{2}-\frac{7}{2}x+y=0\iff "
                    r"2(x^{2}+y^{2})-7x+2y=0.$"),

            example("5.4", "Common Tangent to a Parabola and a Circle"),
            question(r"Find the equations of the common tangents to the parabola "
                     r"$y^{2}=8x$ and the circle $x^{2}+y^{2}=2$."),
            solution(r"For $y^{2}=8x$, $4a=8\implies a=2$. A tangent of slope "
                     r"$m$ is"),
            display(r"$y=mx+\frac{2}{m}\iff m^{2}x-my+2=0.$"),
            para(r"For tangency to the circle $x^{2}+y^{2}=2$ (center $(0,0)$, "
                 r"radius $\sqrt{2}$), its perpendicular distance from $(0,0)$ "
                 r"must equal $\sqrt{2}$:"),
            display(r"$\frac{2}{\sqrt{m^{4}+m^{2}}}=\sqrt{2}\implies "
                    r"m^{4}+m^{2}-2=0\implies m^{2}=1\implies m=\pm1.$"),
            para(r"Hence the common tangents are"),
            display(r"$y=x+2\qquad\text{and}\qquad y=-x-2.$"),

            example("5.5", "Focal Triangle & Eccentricity of an Ellipse"),
            question(r"An ellipse $\frac{x^{2}}{9}+\frac{y^{2}}{4}=1$ has foci "
                     r"$S,S'$, and $P$ is a point on the ellipse such that "
                     r"$\angle SPS'=90^{\circ}$. Find the area of "
                     r"$\triangle SPS'$."),
            solution(r"Here $a=3$, $b=2$, and $c=\sqrt{a^{2}-b^{2}}=\sqrt{5}$, "
                     r"so $SS'=2c=2\sqrt{5}$. For any point $P$ on the ellipse, "
                     r"$SP+S'P=2a=6$. Since $\angle SPS'=90^{\circ}$,"),
            display(r"$SP^{2}+S'P^{2}=(SS')^{2}=20.$"),
            para(r"Therefore,"),
            display(r"$2\,SP\cdot S'P=(SP+S'P)^{2}-(SP^{2}+S'P^{2})=36-20=16,$"),
            display(r"$\operatorname{Area}(\triangle SPS')="
                    r"\frac{1}{2}\,SP\cdot S'P=4=b^{2}.$"),

            example("5.6", "Asymptotes & Rectangular Hyperbola Property"),
            question(r"Prove that the product of the perpendicular distances from "
                     r"any point $P(x_{0},y_{0})$ on the hyperbola "
                     r"$\frac{x^{2}}{a^{2}}-\frac{y^{2}}{b^{2}}=1$ to its two "
                     r"asymptotes $\frac{x}{a}\pm\frac{y}{b}=0$ is the constant "
                     r"$\frac{a^{2}b^{2}}{a^{2}+b^{2}}$."),
            solution(r"Rewrite the asymptotes as $bx-ay=0$ and $bx+ay=0$. "
                     r"Then"),
            display(r"$d_{1}d_{2}="
                    r"\frac{|bx_{0}-ay_{0}|}{\sqrt{a^{2}+b^{2}}}"
                    r"\frac{|bx_{0}+ay_{0}|}{\sqrt{a^{2}+b^{2}}}="
                    r"\frac{|b^{2}x_{0}^{2}-a^{2}y_{0}^{2}|}"
                    r"{a^{2}+b^{2}}.$"),
            para(r"Since $P(x_{0},y_{0})$ lies on the hyperbola, "
                 r"$b^{2}x_{0}^{2}-a^{2}y_{0}^{2}=a^{2}b^{2}$. Hence"),
            display(r"$d_{1}d_{2}=\frac{a^{2}b^{2}}{a^{2}+b^{2}},$"),
            para(r"a constant independent of $P$. $\blacksquare$"),
        ],
        "6.5": [
            example("6.1", "High-Order Taylor Series Limit Parameter Extraction"),
            question(r"Find the constants $(a,b)$ such that "
                     r"$\lim_{x\to0}\frac{x(1+a\cos x)-b\sin x}{x^{3}}=1$."),
            solution(r"Substitute the Maclaurin expansions "
                     r"$\cos x=1-\frac{x^{2}}{2}+\frac{x^{4}}{24}-\cdots$ and "
                     r"$\sin x=x-\frac{x^{3}}{6}+\frac{x^{5}}{120}-\cdots$ into "
                     r"the numerator:"),
            display(r"$x\left(1+a\left(1-\frac{x^{2}}{2}+O(x^{4})\right)\right)"
                    r"-b\left(x-\frac{x^{3}}{6}+O(x^{5})\right)="
                    r"(1+a-b)\,x+\left(\frac{b}{6}-\frac{a}{2}\right)x^{3}"
                    r"+O(x^{5}).$"),
            para(r"For the limit after division by $x^{3}$ to exist and equal "
                 r"$1$, the coefficient of $x$ must vanish and the coefficient "
                 r"of $x^{3}$ must equal $1$:"),
            display(r"$1+a-b=0\implies b=a+1,\qquad "
                    r"\frac{b}{6}-\frac{a}{2}=1\implies b-3a=6.$"),
            display(r"$(a+1)-3a=6\implies -2a=5\implies "
                    r"a=-\frac{5}{2},\qquad b=-\frac{3}{2}.$"),

            example("6.2", "1^∞ Indeterminate Form Limit & Piecewise Continuity"),
            question(r"(a) Evaluate $L=\lim_{x\to0}"
                     r"\left(\frac{\tan x}{x}\right)^{1/x^{2}}$. "
                     r"(b) Find $k$ so that $f(x)=\frac{1-\cos(4x)}{x^{2}}$ for "
                     r"$x\neq0$ and $f(0)=k$ is continuous at $x=0$."),
            solution(r"(a) This is a $1^{\infty}$ indeterminate form; applying "
                     r"the standard formula with $g(x)=1/x^{2}$ and "
                     r"$\tan x=x+\frac{x^{3}}{3}+\cdots$:"),
            display(r"$L=\exp\left(\lim_{x\to0}\frac{1}{x^{2}}"
                    r"\left(\frac{\tan x}{x}-1\right)\right)="
                    r"\exp\left(\lim_{x\to0}\frac{\tan x-x}{x^{3}}\right)="
                    r"e^{1/3}.$"),
            para(r"(b) Using $1-\cos(4x)=2\sin^{2}(2x)$:"),
            display(r"$k=\lim_{x\to0}\frac{2\sin^{2}(2x)}{x^{2}}=8.$"),

            example("6.3", "Implicit Homogeneous Derivative & Parametric "
                            "Second Derivative"),
            question(r"(a) If $x^{p}y^{q}=(x+y)^{p+q}$, prove that "
                     r"$\frac{dy}{dx}=\frac{y}{x}$ and "
                     r"$\frac{d^{2}y}{dx^{2}}=0$. "
                     r"(b) If $x=a(\theta-\sin\theta)$ and "
                     r"$y=a(1-\cos\theta)$, find $\frac{d^{2}y}{dx^{2}}$."),
            solution(r"(a) Taking logarithms, "
                     r"$p\ln x+q\ln y=(p+q)\ln(x+y)$. Differentiating "
                     r"implicitly:"),
            display(r"$\frac{p}{x}+\frac{q}{y}\frac{dy}{dx}="
                    r"\frac{p+q}{x+y}\left(1+\frac{dy}{dx}\right).$"),
            para(r"Collecting the $\frac{dy}{dx}$ terms:"),
            display(r"$\left(\frac{q}{y}-\frac{p+q}{x+y}\right)\frac{dy}{dx}="
                    r"\frac{p+q}{x+y}-\frac{p}{x}.$"),
            para(r"Both sides share the factor $qx-py$, giving"),
            display(r"$\frac{dy}{dx}=\frac{y}{x}\implies "
                    r"\frac{d^{2}y}{dx^{2}}=0.$"),
            para(r"(b) First compute"),
            display(r"$\frac{dy}{dx}=\frac{a\sin\theta}{a(1-\cos\theta)}="
                    r"\cot\frac{\theta}{2}.$"),
            para(r"Differentiating with respect to $x$, where "
                 r"$\frac{d\theta}{dx}=\frac{1}{a(1-\cos\theta)}$:"),
            display(r"$\frac{d^{2}y}{dx^{2}}="
                    r"-\frac{1}{4a}\csc^{4}\frac{\theta}{2}.$"),

            example("6.4", "Second-Order Differential Identity for y = e^{a arcsin x}"),
            question(r"If $y=e^{a\arcsin x}$, prove that "
                     r"$(1-x^{2})y''-xy'-a^{2}y=0$."),
            solution(r"Differentiate once:"),
            display(r"$y'=\frac{a\,y}{\sqrt{1-x^{2}}}.$"),
            para(r"Cross-multiply and square to eliminate the radical:"),
            display(r"$(1-x^{2})(y')^{2}=a^{2}y^{2}.$"),
            para(r"Differentiate implicitly with respect to $x$:"),
            display(r"$2(1-x^{2})y'y''-2x(y')^{2}=2a^{2}yy'.$"),
            para(r"Dividing by $2y'$ and substituting "
                 r"$(1-x^{2})(y')^{2}=a^{2}y^{2}$ gives"),
            display(r"$(1-x^{2})y''-xy'-a^{2}y=0.$"),

            example("6.5", "Cone of Maximum Volume Inscribed in a Sphere of Radius R"),
            question(r"Prove that the altitude $h$ of the right circular cone "
                     r"of maximum volume that can be inscribed in a sphere of "
                     r"radius $R$ is $h=\frac{4R}{3}$, and that its volume is "
                     r"$\frac{8}{27}$ of the sphere's volume."),
            solution(r"Let $x\in(0,R)$ be the distance from the center of the "
                     r"sphere to the cone's base. Then $h=R+x$ and "
                     r"$r^{2}=R^{2}-x^{2}$, so"),
            display(r"$V(x)=\frac{1}{3}\pi(R^{2}-x^{2})(R+x)="
                    r"\frac{1}{3}\pi(R+x)^{2}(R-x).$"),
            para(r"Differentiate:"),
            display(r"$V'(x)=\frac{1}{3}\pi(R+x)(R-3x).$"),
            para(r"The only critical point in $(0,R)$ is $x=R/3$, and it gives "
                 r"the maximum. Thus"),
            display(r"$h=R+\frac{R}{3}=\frac{4R}{3}.$"),
            display(r"$V_{\max}=\frac{32}{81}\pi R^{3}="
                    r"\frac{8}{27}V_{\mathrm{sphere}}.$"),

            example("6.6", "Constant Intercept Property of the Astroid Tangent"),
            question(r"Prove that the portion of the tangent to the astroid "
                     r"$x^{2/3}+y^{2/3}=a^{2/3}$ intercepted between the "
                     r"coordinate axes has constant length $a$."),
            solution(r"Parameterize $P(a\cos^{3}\theta,a\sin^{3}\theta)$. Then"),
            display(r"$\frac{dy}{dx}=-\tan\theta.$"),
            para(r"The tangent at $P$ is"),
            display(r"$y-a\sin^{3}\theta=-\tan\theta(x-a\cos^{3}\theta),$"),
            para(r"which simplifies to"),
            display(r"$\frac{x}{a\cos\theta}+\frac{y}{a\sin\theta}=1.$"),
            para(r"Hence the axis intercepts are $a\cos\theta$ and "
                 r"$a\sin\theta$, so the intercepted length is"),
            display(r"$\sqrt{a^{2}\cos^{2}\theta+a^{2}\sin^{2}\theta}=a.$"), 
        ],
        "7.3": [
            example("7.1", "Algebraic Twin Substitution"),
            question(r"Evaluate $I_{1} = \int \frac{x^{2}+1}{x^{4}+1}\,dx$ and "
                     r"$I_{2} = \int \frac{x^{2}-1}{x^{4}+1}\,dx$."),
            solution(r"Divide numerator and denominator by $x^{2}$. For "
                     r"$I_{1}$, let $u=x-\frac{1}{x}$, so "
                     r"$du=\left(1+\frac{1}{x^{2}}\right)dx$ and "
                     r"$x^{2}+\frac{1}{x^{2}}=u^{2}+2$. Then"),
            display(r"$I_{1} = \int \frac{du}{u^{2} + 2} = "
                    r"\frac{1}{\sqrt{2}} \arctan \frac{u}{\sqrt{2}} + C = "
                    r"\frac{1}{\sqrt{2}} \arctan \frac{x^{2} - 1}{\sqrt{2}\,x} + C.$"),
            para(r"For $I_{2}$, let $v=x+\frac{1}{x}$, so "
                 r"$dv=\left(1-\frac{1}{x^{2}}\right)dx$ and "
                 r"$x^{2}+\frac{1}{x^{2}}=v^{2}-2$:"),
            display(r"$I_{2} = \int \frac{dv}{v^{2} - 2} = "
                    r"\frac{1}{2\sqrt{2}} \ln \left| "
                    r"\frac{v - \sqrt{2}}{v + \sqrt{2}} "
                    r"\right| + C = "
                    r"\frac{1}{2\sqrt{2}} \ln \left| "
                    r"\frac{x^{2} - \sqrt{2}\,x + 1}{x^{2} + \sqrt{2}\,x + 1} "
                    r"\right| + C.$"),

            example("7.2", "Classic ln(sin x) Integral via King's Property"),
            question(r"Evaluate $I = \int_{0}^{\pi/2} \ln(\sin x)\,dx$ using "
                     r"King's Property."),
            solution(r"By King's Property, $I = \int_{0}^{\pi/2} \ln(\cos x)\,dx$. "
                     r"Adding,"),
            display(r"$2I = \int_{0}^{\pi/2} \ln(\sin x \cos x)\,dx = "
                    r"\int_{0}^{\pi/2} \ln\left(\frac{\sin 2x}{2}\right)dx = "
                    r"\int_{0}^{\pi/2} \ln(\sin 2x)\,dx - \frac{\pi}{2}\ln 2.$"),
            para(r"By the symmetry of $\sin x$ about $\pi/2$,"),
            display(r"$\int_{0}^{\pi/2} \ln(\sin 2x)\,dx = I.$"),
            para(r"Hence"),
            display(r"$2I = I - \frac{\pi}{2}\ln 2 \implies I = -\frac{\pi}{2}\ln 2.$"),

            example("7.3", "Definite Integral as the Limit of a Riemann Sum"),
            question(r"Evaluate $L = \lim_{n\to\infty} \sum_{r=1}^{n} "
                     r"\frac{n}{n^{2} + r^{2}}$ and "
                     r"$M = \lim_{n\to\infty} "
                     r"\left(\frac{(2n)!}{n!\, n^{n}}\right)^{1/n}$."),
            solution(r"(a) Factor $\frac{1}{n}$ out of each term:"),
            display(r"$L = \lim_{n\to\infty} \frac{1}{n} \sum_{r=1}^{n} "
                    r"\frac{1}{1 + (r/n)^{2}} = \int_{0}^{1} "
                    r"\frac{dx}{1 + x^{2}} = \frac{\pi}{4}.$"),
            para(r"(b) Write $\frac{(2n)!}{n!\, n^{n}} = "
                 r"\prod_{r=1}^{n} \left(1 + \frac{r}{n}\right)$. Taking "
                 r"logarithms gives"),
            display(r"$\ln M = \lim_{n\to\infty} \frac{1}{n} \sum_{r=1}^{n} "
                    r"\ln\left(1 + \frac{r}{n}\right) = \int_{0}^{1} "
                    r"\ln(1 + x)\,dx = 2\ln 2 - 1 = \ln\frac{4}{e}.$"),
            para(r"Hence $M = \frac{4}{e}$."),

            example("7.4", "Area Enclosed by an Ellipse & Between Circle and Parabola"),
            question(r"(a) Prove via integration that the area of the ellipse "
                     r"$\frac{x^{2}}{a^{2}} + \frac{y^{2}}{b^{2}} = 1$ is "
                     r"$\pi a b$. (b) Find the area inside $x^{2} + y^{2} = 8x$ "
                     r"and outside $y^{2} = 4x$ above the $x$-axis for "
                     r"$x \in [0, 4]$."),
            solution(r"(a) By four-quadrant symmetry,"),
            display(r"$\text{Area} = 4 \int_{0}^{a} \frac{b}{a}"
                    r"\sqrt{a^{2} - x^{2}}\,dx = \pi a b.$"),
            para(r"(b) The circle is $(x - 4)^{2} + y^{2} = 16$; on "
                 r"$[0,4]$, the required area is"),
            display(r"$\int_{0}^{4} \left(\sqrt{16 - (x - 4)^{2}} - "
                    r"2\sqrt{x}\right)dx = 4\pi - \frac{32}{3}.$"),

            example("7.5", "Homogeneous Differential Equation (y = vx Substitution)"),
            question(r"Solve the homogeneous differential equation "
                     r"$x^{2}\,dy + y(x + y)\,dx = 0$ given $y(1) = 1$."),
            solution(r"Rewrite as $\frac{dy}{dx} = -\frac{y}{x} - "
                     r"\left(\frac{y}{x}\right)^{2}$ and set "
                     r"$y = vx$:"),
            display(r"$v + x\frac{dv}{dx} = -v - v^{2} \implies "
                    r"x\frac{dv}{dx} = -v(v + 2).$"),
            para(r"Integrating gives"),
            display(r"$\frac{1}{2} \ln\left|\frac{v}{v + 2}\right| = "
                    r"-\ln|x| + C.$"),
            para(r"Substituting $v=y/x$ and $y(1)=1$ yields "
                 r"$3x^{2}y = y + 2x$."),

            example("7.6", "Bernoulli Differential Equation Reduced to a Linear ODE"),
            question(r"Solve the Bernoulli differential equation "
                     r"$\frac{dy}{dx} + \frac{y}{x} = x^{2} y^{6}$ for "
                     r"$x > 0$."),
            solution(r"Divide by $y^{6}$ and set $u = y^{-5}$:"),
            display(r"$\frac{du}{dx} - \frac{5}{x} u = -5x^{2}.$"),
            para(r"The integrating factor is $x^{-5}$, so"),
            display(r"$\frac{d}{dx}\left(u x^{-5}\right) = -5x^{-3} \implies "
                    r"y^{-5} = \frac{5}{2} x^{3} + C x^{5}.$"),
        ],
        "8.4": [
            example("8.1", "Dyadic Cosine Product & Triple-Angle Evaluation"),
            question(r"Prove without a calculator that "
                     r"$\cos 20^{\circ} \cos 40^{\circ} \cos 60^{\circ} "
                     r"\cos 80^{\circ} = \frac{1}{16}$ and "
                     r"$\sin 20^{\circ} \sin 40^{\circ} \sin 60^{\circ} "
                     r"\sin 80^{\circ} = \frac{3}{16}$."),
            solution(r"Since $\cos 60^{\circ} = \frac{1}{2}$, apply "
                     r"$\prod_{k=0}^{2} \cos(2^{k} \theta) = "
                     r"\frac{\sin(8 \theta)}{8 \sin \theta}$ with "
                     r"$\theta = 20^{\circ}$:"),
            display(r"$\cos 20^{\circ} \cos 40^{\circ} \cos 80^{\circ} = "
                    r"\frac{\sin 160^{\circ}}{8 \sin 20^{\circ}} = "
                    r"\frac{1}{8},$"),
            display(r"$\cos 20^{\circ} \cos 40^{\circ} \cos 60^{\circ} "
                    r"\cos 80^{\circ} = \frac{1}{16}.$"),
            para(r"Using "
                 r"$4 \sin \theta \sin(60^{\circ} - \theta) "
                 r"\sin(60^{\circ} + \theta) = \sin 3 \theta$ at "
                 r"$\theta = 20^{\circ}$:"),
            display(r"$4 \sin 20^{\circ} \sin 40^{\circ} \sin 80^{\circ} = "
                    r"\sin 60^{\circ} = \frac{\sqrt{3}}{2},$"),
            display(r"$\sin 20^{\circ} \sin 40^{\circ} \sin 60^{\circ} "
                    r"\sin 80^{\circ} = \frac{3}{16}.$"),

            example("8.2", "Conditional Triangle Identity Proof"),
            question(r"If $A + B + C = \pi$, prove that "
                     r"$\sin 2A + \sin 2B + \sin 2C = "
                     r"4 \sin A \sin B \sin C$."),
            solution(r"Apply sum-to-product to the first two terms and use "
                     r"$A+B=\pi-C$, so $\sin(A+B)=\sin C$ and "
                     r"$\cos(A+B)=-\cos C$:"),
            display(r"$\sin 2A + \sin 2B + \sin 2C = "
                    r"2 \sin(A + B) \cos(A - B) + 2 \sin C \cos C = "
                    r"2 \sin C (\cos(A - B) - \cos(A + B)) = "
                    r"4 \sin A \sin B \sin C.$"),

            example("8.3", "Solving a cos θ + b sin θ = c via Auxiliary Angle"),
            question(r"Find the general solution of "
                     r"$\sqrt{3} \cos \theta + \sin \theta = \sqrt{2}$."),
            solution(r"Divide both sides by "
                     r"$R = \sqrt{(\sqrt{3})^{2} + 1^{2}} = 2$:"),
            display(r"$\cos\left(\theta - \frac{\pi}{6}\right) = "
                    r"\cos \frac{\pi}{4}.$"),
            para(r"By the general cosine solution,"),
            display(r"$\theta = 2 n \pi + \frac{5 \pi}{12} \quad "
                    r"\text{or} \quad \theta = 2 n \pi - \frac{\pi}{12}, "
                    r"\qquad n \in \mathbb{Z}.$"),

            example("8.4", "Machin's Formula for π"),
            question(r"Prove that $4 \arctan \frac{1}{5} - "
                     r"\arctan \frac{1}{239} = \frac{\pi}{4}$."),
            solution(r"Apply $2 \arctan x = "
                     r"\arctan \frac{2x}{1 - x^{2}}$ twice to "
                     r"$x = \frac{1}{5}$:"),
            display(r"$4 \arctan \frac{1}{5} = "
                    r"\arctan \frac{120}{119}.$"),
            para(r"Now subtract $\arctan \frac{1}{239}$:"),
            display(r"$\arctan \frac{120}{119} - \arctan \frac{1}{239} = "
                    r"\arctan 1 = \frac{\pi}{4}.$"),

            example("8.5", "Piecewise Folding of arcsin(sin 10) and arccos(cos 12)"),
            question(r"Find the exact radian values of "
                     r"(a) $\arcsin(\sin 10)$ and (b) $\arccos(\cos 12)$."),
            solution(r"(a) Choose $\theta\in[-\pi/2,\pi/2]$ with "
                     r"$\sin\theta=\sin10$. Since "
                     r"$\theta=3\pi-10$,"),
            display(r"$\arcsin(\sin 10) = 3\pi - 10.$"),
            para(r"(b) Choose $\phi\in[0,\pi]$ with "
                 r"$\cos\phi=\cos12$. Since $\phi=4\pi-12$,"),
            display(r"$\arccos(\cos 12) = 4\pi - 12.$"),

            example("8.6", "Circumradius, Inradius & Cosine Rule in △ABC"),
            question(r"In a triangle $ABC$ with sides $a = 13$, $b = 14$, "
                     r"$c = 15$, find (a) $\cos A$, (b) the area $\Delta$, "
                     r"(c) the inradius $r$, and (d) the circumradius $R$."),
            solution(r"(a) By the Cosine Rule,"),
            display(r"$\cos A = \frac{b^{2} + c^{2} - a^{2}}{2bc} = "
                    r"\frac{3}{5}.$"),
            para(r"(b) The semi-perimeter is $s=21$. By Heron's formula,"),
            display(r"$\Delta = \sqrt{s(s-a)(s-b)(s-c)} = 84.$"),
            para(r"(c) The inradius is"),
            display(r"$r = \frac{\Delta}{s} = 4.$"),
            para(r"(d) The circumradius is"),
            display(r"$R = \frac{abc}{4\Delta} = \frac{65}{8} = 8.125.$"),
        ],
        "9.4": [
            example("9.1", "Pairwise Norm Identity & Angle Between Vectors"),
            question(r"If $\vec a$, $\vec b$, $\vec c$ are unit vectors "
                     r"satisfying $\vec a+\vec b+\vec c=\vec 0$, find "
                     r"$\vec a\cdot\vec b+\vec b\cdot\vec c+\vec c\cdot"
                     r"\vec a$ and the angle between any two of them."),
            solution(r"Square the magnitude of $\vec a+\vec b+\vec c=\vec 0$:"),
            display(r"$0=|\vec a+\vec b+\vec c|^{2}="
                    r"3+2(\vec a\cdot\vec b+\vec b\cdot\vec c+\vec c\cdot\vec a).$"),
            para(r"Hence $\vec a\cdot\vec b+\vec b\cdot\vec c+\vec c\cdot\vec a="
                 r"-\frac{3}{2}$. Also, $\vec a+\vec b=-\vec c$; squaring gives"),
            display(r"$2+2\cos\theta=1\implies\cos\theta=-\frac{1}{2}"
                    r"\implies\theta=\frac{2\pi}{3}.$"),

            example("9.2", "Vector Triple Product & Solving r × a = b"),
            question(r"Given $\vec a\cdot\vec b=0$ and $\vec a\neq\vec 0$, "
                     r"solve $\vec r\times\vec a=\vec b$ and $\vec r\cdot\vec a=c$."),
            solution(r"Take the cross product of $\vec a$ with both sides and "
                     r"use BAC-CAB:"),
            display(r"$|\vec a|^{2}\vec r-(\vec a\cdot\vec r)\vec a="
                    r"\vec a\times\vec b.$"),
            para(r"Since $\vec a\cdot\vec r=c$,"),
            display(r"$\vec r=\frac{c\vec a+\vec a\times\vec b}{|\vec a|^{2}}.$"),

            example("9.3", "Shortest Distance Between Two Skew Lines in 3D"),
            question(r"Find the shortest distance between the lines "
                     r"$L_{1}:\ \vec r=(\hat i+2\hat j+\hat k)+"
                     r"\lambda(\hat i-\hat j+\hat k)$ and "
                     r"$L_{2}:\ \vec r=(2\hat i-\hat j-\hat k)+"
                     r"\mu(2\hat i+\hat j+2\hat k)$."),
            solution(r"Here $\vec a_{1}=(1,2,1)$, $\vec a_{2}=(2,-1,-1)$, "
                     r"$\vec b_{1}=(1,-1,1)$, $\vec b_{2}=(2,1,2)$, so "
                     r"$\vec a_{2}-\vec a_{1}=(1,-3,-2)$. Compute"),
            display(r"$\vec b_{1}\times\vec b_{2}=-3\hat i+3\hat k,"
                    r"\qquad |\vec b_{1}\times\vec b_{2}|=3\sqrt{2}.$"),
            display(r"$(\vec a_{2}-\vec a_{1})\cdot(\vec b_{1}\times\vec b_{2})=-9,$"),
            display(r"$d=\frac{9}{3\sqrt{2}}=\frac{3\sqrt{2}}{2}.$"),

            example("9.4", "Foot of Perpendicular & Mirror Image of a Point in a 3D Line"),
            question(r"Find the foot of the perpendicular $M$ and the mirror "
                     r"image $Q$ of the point $P(1,6,3)$ in the line "
                     r"$\frac{x}{1}=\frac{y-1}{2}=\frac{z-2}{3}$."),
            solution(r"Any point on the line has the form "
                     r"$M(\lambda,2\lambda+1,3\lambda+2)$, so"),
            display(r"$\overrightarrow{PM}=(\lambda-1,2\lambda-5,3\lambda-1).$"),
            para(r"Perpendicularity to the line direction $(1,2,3)$ gives"),
            display(r"$(\lambda-1)+2(2\lambda-5)+3(3\lambda-1)=14\lambda-14=0"
                    r"\implies\lambda=1.$"),
            para(r"Hence $M=(1,3,5)$, and $Q=2M-P=(1,0,7)$."),

            example("9.5", "Plane Through the Intersection of Two Planes"),
            question(r"Find the equation of the plane passing through the "
                     r"intersection of the planes $x+2y+3z-4=0$ and "
                     r"$2x+y-z+5=0$ and perpendicular to the plane "
                     r"$5x+3y-6z+8=0$."),
            solution(r"Any plane through the intersection belongs to the pencil"),
            display(r"$(x+2y+3z-4)+\lambda(2x+y-z+5)=0.$"),
            para(r"Its normal is "
                 r"$(1+2\lambda,\ 2+\lambda,\ 3-\lambda)$. Perpendicularity to "
                 r"$5x+3y-6z+8=0$ requires"),
            display(r"$5(1+2\lambda)+3(2+\lambda)-6(3-\lambda)=19\lambda-7=0"
                    r"\implies\lambda=\frac{7}{19}.$"),
            para(r"Substituting and clearing denominators gives"),
            display(r"$33x+45y+50z-41=0.$"),

            example("9.6", "Complete Corner-Point Solution of a 2D Linear Program"),
            question(r"Maximize and minimize $Z=5x+10y$ subject to "
                     r"$x+2y\leq120$, $x+y\geq60$, $x-2y\geq0$, and $x,y\geq0$."),
            solution(r"The feasible region is bounded by the three lines; its "
                     r"corner points are $A(60,0)$, $B(120,0)$, $C(60,30)$, "
                     r"and $D(40,20)$. Their $Z$-values are"),
            display(r"$Z(A)=300,\qquad Z(B)=600,\qquad Z(C)=600,\qquad Z(D)=400.$"),
            para(r"Hence $Z_{\min}=300$ at $(60,0)$ and $Z_{\max}=600$, attained "
                 r"on the whole edge $BC$."),
        ],
        "10.3": [
            example("10.1", "Correcting Mean & Standard Deviation After Misread Observation"),
            question(r"The mean and standard deviation of $20$ observations were calculated as $10$ and $2$, respectively. Upon rechecking, one observation of $8$ was found to be incorrect. Find the correct mean and standard deviation if (a) the wrong item $8$ is omitted, and (b) it is replaced by $12$."),
            solution(r"From $N=20$, $\bar{x}=10$ and $\sigma=2$:"),
            display(r"$\sum x_{i}=200,\qquad \sum x_{i}^{2}=2080.$"),
            para(r"(a) Omitting $8$ ($N=19$):"),
            display(r"$\sum_{\mathrm{new}} x_{i}=192,\qquad "
                    r"\sum_{\mathrm{new}} x_{i}^{2}=2016,$"),
            display(r"$\bar{x}_{\mathrm{new}}=\frac{192}{19}\approx 10.105,\qquad "
                    r"\sigma_{\mathrm{new}}\approx 2.00.$"),
            para(r"(b) Replacing $8$ by $12$ ($N=20$):"),
            display(r"$\sum_{\mathrm{new}} x_{i}=204,\qquad "
                    r"\sum_{\mathrm{new}} x_{i}^{2}=2160,$"),
            display(r"$\bar{x}_{\mathrm{new}}=10.2,\qquad "
                    r"\sigma_{\mathrm{new}}\approx 1.99.$"),

            example("10.2", "Pooled Mean & Combined Variance of Two Cohorts"),
            question(r"Group 1 has $n_{1}=40$, $\bar{x}_{1}=50$, $\sigma_{1}=6$; Group 2 has $n_{2}=60$, $\bar{x}_{2}=40$, $\sigma_{2}=8$. Find the pooled mean and pooled variance."),
            solution(r"The pooled mean is"),
            display(r"$\bar{x}=\frac{n_{1}\bar{x}_{1}+n_{2}\bar{x}_{2}}{n_{1}+n_{2}}=44.$"),
            para(r"With $d_{1}=6$, $d_{2}=-4$:"),
            display(r"$\sigma^{2}=\frac{n_{1}(\sigma_{1}^{2}+d_{1}^{2})+"
                    r"n_{2}(\sigma_{2}^{2}+d_{2}^{2})}{n_{1}+n_{2}}="
                    r"\frac{40(72)+60(80)}{100}=76.8,$"),
            para(r"so $\sigma=\sqrt{76.8}\approx 8.76$."),

            example("10.3", "Bayes' Theorem with Truth-Teller vs. Liar"),
            question(r"A man speaks the truth $3$ out of $4$ times. He throws a fair die and reports it shows a Six. Find the posterior probability that it is actually a Six."),
            solution(r"Let $E$ be the event that a Six occurred and $A$ the event that he reports a Six. Then"),
            display(r"$P(E)=\frac{1}{6},\qquad P(A\mid E)=\frac{3}{4},\qquad "
                    r"P(A\mid E^{c})=\frac{1}{4}.$"),
            para(r"By Bayes' theorem,"),
            display(r"$P(E\mid A)="
                    r"\frac{(1/6)(3/4)}{(1/6)(3/4)+(5/6)(1/4)}="
                    r"\frac{3}{8}=0.375.$"),

            example("10.4", "Infinite Alternating Coin-Toss Game"),
            question(r"Players $A$ and $B$ toss a fair coin, $A$ first; the first Head wins. Find the exact winning probabilities of $A$ and $B$."),
            solution(r"$A$ wins on toss $1$, $3$, $5$, ... with probabilities $\frac{1}{2}$, $\frac{1}{8}$, $\frac{1}{32}$, ..."),
            display(r"$P(A\text{ wins})=\frac{1/2}{1-1/4}=\frac{2}{3},\qquad "
                    r"P(B\text{ wins})=\frac{1}{3}.$"),

            example("10.5", "Discrete Random Variable PMF, Expectation & Variance"),
            question(r"Two cards are drawn without replacement from $52$; find the distribution, mean, and variance of the number of Aces $X$."),
            solution(r"The probabilities are"),
            display(r"$P(X=0)=\frac{188}{221},\qquad "
                    r"P(X=1)=\frac{32}{221},\qquad "
                    r"P(X=2)=\frac{1}{221}.$"),
            display(r"$\mathbb{E}[X]=\frac{2}{13},\qquad "
                    r"\operatorname{Var}(X)=\frac{400}{2873}\approx 0.139.$"),

            example("10.6", "Minimum Sample Size in Binomial Trials"),
            question(r"How many times must a fair coin be tossed so that the probability of at least one Head is at least $99\%$?"),
            solution(r"For $X\sim\mathrm{Bin}(n,0.5)$,"),
            display(r"$P(X\geq 1)=1-(1/2)^{n}\geq 0.99 \iff 2^{n}\geq 100.$"),
            para(r"Since $2^{6}=64<100$ and $2^{7}=128\geq 100$, the minimum is $n=7$."),
        ],
        "11.4": [
            example("11.1", "Sigmoid & Logit Mental Math"),
            question(r"If a model outputs the logit $z=\ln 4\approx 1.386$, "
                     r"what is $p=\sigma(z)$? Conversely, what logit $z$ "
                     r"gives $p=0.90$?"),
            solution(r"Since $e^{-z}=e^{-\ln 4}=\frac{1}{4}=0.25$,"),
            display(r"$p=\sigma(z)=\frac{1}{1+e^{-z}}="
                    r"\frac{1}{1+0.25}=0.80.$"),
            para(r"Conversely, for $p=0.90$ the odds are "
                 r"$\frac{0.90}{0.10}=9$, so"),
            display(r"$z=\sigma^{-1}(0.90)=\ln 9\approx 2.1972.$"),

            example("11.2", "Overflow-Safe Log-Sum-Exp & Softmax"),
            question(r"Given logits $z=[1000,\ 1001,\ 999]$, compute "
                     r"$\mathrm{LSE}(z)$ and the softmax probability $p_{2}$ "
                     r"of $z_{2}=1001$."),
            solution(r"Set $c=\max(z)=1001$. Then"),
            display(r"$\mathrm{LSE}(z)=1001+"
                    r"\ln\left(e^{-1}+1+e^{-2}\right)"
                    r"=1001+\ln(1.50322)\approx 1001.4076.$"),
            para(r"Thus"),
            display(r"$p_{2}=e^{1001-\mathrm{LSE}(z)}\approx 0.6652.$"),

            example("11.3", "RL Discounted Horizon & Bond Annuity Valuation"),
            question(r"(a) Find $V=\sum_{t=0}^{\infty}\gamma^{t}r$ for "
                     r"$r=2$ and $\gamma=0.95$. (b) Price a 5-year bond with "
                     r"face value Rs. $1{,}000$, annual coupon Rs. $80$, and "
                     r"yield $y=10\%$."),
            solution(r"(a) By the infinite geometric series,"),
            display(r"$V=\frac{r}{1-\gamma}=\frac{2}{0.05}=40.$"),
            para(r"(b) Discounting coupons and principal at $1/1.10$:"),
            display(r"$P=\frac{80}{0.10}(1-1.10^{-5})+1000(1.10^{-5})"
                    r"=\text{Rs. }924.18.$"),

            example("11.4", "Cauchy-Schwarz Cosine Similarity"),
            question(r"Verify the Cauchy-Schwarz inequality and compute the "
                     r"cosine similarity for $u=[3,\ 4]^{T}$ and "
                     r"$v=[6,\ 8]^{T}$."),
            solution(r"The dot product is $u^{T}v=50$, while "
                     r"$\|u\|_{2}=5$ and $\|v\|_{2}=10$. Hence"),
            display(r"$|u^{T}v|=50=\|u\|_{2}\|v\|_{2},"
                    r"\qquad \cos\theta=1.$"),

            example("11.5", "Complex Division & RoPE Relative Distance Invariance"),
            question(r"Write $z=\frac{3+4i}{1+2i}$ in the form $a+bi$, and show "
                     r"why RoPE rotations depend only on $m-n$."),
            solution(r"Multiply numerator and denominator by $1-2i$:"),
            display(r"$z=\frac{(3+4i)(1-2i)}{5}="
                    r"\frac{11-2i}{5}=2.2-0.4i.$"),
            para(r"For RoPE, "
                 r"$q_{m}\bar{k}_{n}=(q\bar{k})e^{i(m-n)\theta}$, so "
                 r"$\operatorname{Re}(q_{m}\bar{k}_{n})=|q||k|"
                 r"\cos((m-n)\theta+\phi)$ depends only on $m-n$."),
        ],
        "15.3": [
            example("15.1", "Two-Asset Portfolio Volatility & Correlation"),
            question(r"An equal-weight portfolio ($w_{1}=w_{2}=0.5$) holds two "
                     r"stocks, each with volatility $\sigma=20\%$. Find the "
                     r"portfolio volatility $\sigma_{P}$ when (i) $\rho=+1$, "
                     r"(ii) $\rho=0$, and (iii) $\rho=-0.5$."),
            solution(r"The portfolio variance is"),
            display(r"$\sigma_{P}^{2}=0.25(0.04)+0.25(0.04)+"
                    r"2(0.25)\rho(0.04)=0.02(1+\rho).$"),
            bullet(r"$\rho=+1$: $\sigma_{P}=20\%$."),
            bullet(r"$\rho=0$: $\sigma_{P}=\sqrt{0.02}\approx 14.14\%$."),
            bullet(r"$\rho=-0.5$: $\sigma_{P}=10\%$."),

            example("15.2", "Log-Normal Stock Expectation"),
            question(r"If $\ln(S_{1}/100)\sim\mathcal{N}(0,0.20^{2})$, compute "
                     r"$\mathbb{E}[S_{1}]$."),
            solution(r"Write $X=\ln(S_{1}/100)$. Then"),
            display(r"$\mathbb{E}[S_{1}]=100\,e^{0.5(0.20)^{2}}="
                    r"100e^{0.02}\approx \text{Rs. }102.02.$"),

            example("15.3", "Bernoulli Coin-Toss Maximum Likelihood Estimation"),
            question(r"Given $7$ Heads and $3$ Tails in $10$ independent tosses, "
                     r"derive $\hat p_{\mathrm{MLE}}$."),
            solution(r"The log-likelihood is"),
            display(r"$\ell(p)=7\ln p+3\ln(1-p).$"),
            para(r"Setting $\ell'(p)=0$:"),
            display(r"$\frac{7}{p}-\frac{3}{1-p}=0\implies 7(1-p)=3p"
                    r"\implies p=\frac{7}{10}=0.70.$"),

            example("15.4", "Law of Total Variance Across Calm/Crash Regimes"),
            question(r"Calm regime ($P=0.8$): $\mu_{C}=1\%,\sigma_{C}=2\%$; crash "
                     r"regime ($P=0.2$): $\mu_{S}=-4\%,\sigma_{S}=6\%$. Find "
                     r"$\mathbb{E}[R]$ and $\operatorname{Var}(R)$."),
            solution(r"The unconditional mean is"),
            display(r"$\mathbb{E}[R]=0\%.$"),
            para(r"By the Law of Total Variance,"),
            display(r"$\operatorname{Var}(R)="
                    r"0.8(2^{2})+0.2(6^{2})+"
                    r"0.8(1^{2})+0.2(4^{2})=14.4,$"),
            para(r"so $\sigma_{R}=\sqrt{14.4}\approx 3.795\%$."),

            example("15.5", "Shannon Entropy, Cross-Entropy & KL Divergence in Bits"),
            question(r"For $P=(0.5,0.5)$ and $Q=(0.8,0.2)$, compute $H(P)$, "
                     r"$H(P,Q)$, and $D_{\mathrm{KL}}(P\|Q)$ in bits."),
            solution(r"Using $\log_{2}$:"),
            display(r"$H(P)=1.000\ \text{bit},$"),
            display(r"$H(P,Q)=-0.5\log_{2}(0.8)-0.5\log_{2}(0.2)"
                    r"\approx 1.3219\ \text{bits},$"),
            display(r"$D_{\mathrm{KL}}(P\|Q)=H(P,Q)-H(P)\approx 0.3219\ \text{bits}.$"),
        ],
        "16.3": [
            example("16.1", "Step-Size Convergence vs. Divergence"),
            question(r"Starting at $w_{0}=2$ on $f(w)=5w^{2}$ ($L=10$), trace "
                     r"$w_{1},w_{2}$ for (a) $\eta=0.10$ and (b) $\eta=0.25$."),
            solution(r"Since $f'(w)=10w$,"),
            display(r"$w_{t+1}=(1-10\eta)w_{t}.$"),
            para(r"(a) $\eta=0.10$: $w_{1}=0$ in one step."),
            para(r"(b) $\eta=0.25$: $w_{1}=-3$, $w_{2}=4.5$ (exploding)."),

            example("16.2", "Equality-Constrained Lagrange Multipliers"),
            question(r"Minimize $f(x,y)=x^{2}+y^{2}$ subject to $x+y=6$."),
            solution(r"The Lagrangian is "
                     r"$\mathcal{L}=x^{2}+y^{2}+\nu(6-x-y)$. Stationarity gives"),
            display(r"$2x-\nu=0,\qquad 2y-\nu=0,\qquad x+y=6.$"),
            para(r"Hence $x^{*}=y^{*}=3$ and minimum $f(3,3)=18$."),

            example("16.3", "KKT Inequality Constraint Verification"),
            question(r"Minimize $f(x)=(x-3)^{2}$ subject to $x\leq 1$."),
            solution(r"The unconstrained minimizer $x=3$ violates the "
                     r"constraint, so $x^{*}=1$. With "
                     r"$\mathcal{L}=(x-3)^{2}+\lambda(x-1)$, stationarity gives"),
            display(r"$2(x-3)+\lambda=0\implies \lambda=4>0,$"),
            para(r"confirming the constraint is binding."),

            example("16.4", "Markowitz Maximum Sharpe Tangency Portfolio"),
            question(r"Two uncorrelated strategies have excess returns "
                     r"$\mu=[12\%,8\%]^{T}$ and volatilities "
                     r"$\sigma_{1}=20\%,\sigma_{2}=10\%$. Find $w^{*}$ and the "
                     r"maximum Sharpe ratio."),
            solution(r"$\Sigma^{-1}=\operatorname{diag}(25,100)$ and "
                     r"$\Sigma^{-1}\mu=(3,8)^{T}$, so"),
            display(r"$w^{*}=\frac{1}{11}(3,8)^{T},\qquad "
                    r"S^{*}=\sqrt{\mu^{T}\Sigma^{-1}\mu}=1.00.$"),

            example("16.5", "Kelly Criterion vs. Overbetting Decay"),
            question(r"An even-money bet wins with $p=0.60$. Compare "
                     r"$g(f)$ at the Kelly fraction against $f=50\%$."),
            solution(r"The Kelly fraction is"),
            display(r"$f^{*}=p-q=0.20.$"),
            para(r"The expected log-growth is "
                 r"$g(f)=0.6\ln(1+f)+0.4\ln(1-f)$. At $f^{*}=0.20$,"),
            display(r"$g(0.20)\approx +2.01\%\ \text{per bet}.$"),
            para(r"At $f=0.50$,"),
            display(r"$g(0.50)\approx -3.40\%\ \text{per bet}.$"),
            para(r"Overbetting beyond twice the Kelly fraction makes the "
                 r"expected log-growth negative."),
        ],
        "17.3": [
            example("17.1", "Itô's Lemma on W_t^3"),
            question(r"Compute $d(W_{t}^{3})$ using Itô's lemma."),
            solution(r"Take $f(x)=x^{3}$. Since $(dW_{t})^{2}=dt$, Itô's "
                     r"lemma gives"),
            display(r"$d(W_{t}^{3})=3W_{t}^{2}\,dW_{t}+3W_{t}\,dt.$"),

            example("17.2", "GBM Mean vs. Median Stock Price"),
            question(r"A stock follows GBM $dS_{t}=\mu S_{t}dt+"
                     r"\sigma S_{t}dW_{t}$ with $S_{0}=\text{Rs. }100$, "
                     r"$\mu=10\%$, $\sigma=40\%$, $T=1$. Compare the mean "
                     r"and median of $S_{1}$."),
            solution(r"The exact solution is "
                     r"$S_{t}=S_{0}\exp[(\mu-\frac{1}{2}\sigma^{2})t+\sigma W_{t}]$."),
            display(r"$\mathbb{E}[S_{1}]=100e^{0.10}\approx "
                    r"\text{Rs. }110.52.$"),
            para(r"The median path sets $W_{1}=0$:"),
            display(r"$S_{\mathrm{median}}=100e^{0.02}\approx "
                    r"\text{Rs. }102.02.$"),

            example("17.3", "One-Step Binomial No-Arbitrage Replication"),
            question(r"A stock trades at $S_{0}=\text{Rs. }100$; it will be "
                     r"either $S_{u}=120$ or $S_{d}=80$ in one year. With "
                     r"$r=0$, price a call with $K=100$ by replication."),
            solution(r"The call pays $20$ in the up state and $0$ in the down "
                     r"state. The replicating delta is"),
            display(r"$\Delta=\frac{20-0}{120-80}=0.50.$"),
            para(r"The delta-hedged portfolio is riskless with value "
                 r"$-40$ in both states, so"),
            display(r"$C_{0}=0.5(100)-40=\text{Rs. }10.$"),

            example("17.4", "Black-Scholes Call & Put Valuation"),
            question(r"Price a 6-month at-the-money call and put with "
                     r"$S=K=\text{Rs. }100$, $r=6\%$, $\sigma=20\%$."),
            solution(r"Compute $d_{1}$ and $d_{2}$:"),
            display(r"$d_{1}\approx 0.2828,\qquad d_{2}\approx 0.1414.$"),
            para(r"From the normal CDF and put-call parity:"),
            display(r"$C\approx \text{Rs. }7.16,\qquad P\approx \text{Rs. }4.20.$"),

            example("17.5", "Delta-Hedged Gamma-Theta P&L"),
            question(r"A trader is long 100 calls ($\Delta=0.5$, "
                     r"$\Gamma=0.04$, $\Theta=-\text{Rs. }0.05$/day) and "
                     r"short 50 shares. Compute the 1-day P&L if "
                     r"$\Delta S=-\text{Rs. }4$."),
            solution(r"The portfolio is delta-neutral, with"),
            display(r"$\Gamma_{\mathrm{port}}=4,\qquad "
                    r"\Theta_{\mathrm{port}}=-5.00\ \text{per day}.$"),
            para(r"The 1-day P&L is"),
            display(r"$\Delta\Pi\approx -5.00+\frac{1}{2}(4)(4^{2})="
                    r"+\text{Rs. }27.00.$"),
        ],
        "18.3": [
            example("18.1", "Eliminating Catastrophic Cancellation"),
            question(r"Rewrite $f(x)=\sqrt{x^{2}+1}-x$ so it suffers zero "
                     r"cancellation at $x=10{,}000$."),
            solution(r"Multiply numerator and denominator by the conjugate:"),
            display(r"$f(x)=\frac{1}{\sqrt{x^{2}+1}+x}\approx"
                    r"\frac{1}{2x}=5.0\times10^{-5}.$"),

            example("18.2", "1-Step Implied Volatility Newton Update"),
            question(r"At $\sigma_{0}=20\%$, $C_{BS}(0.20)=7.16$ and "
                     r"$\mathcal{V}(0.20)=27.10$. If $C_{\mathrm{mkt}}=8.24$, "
                     r"compute $\sigma_{1}$."),
            solution(r"One Newton-Raphson step gives"),
            display(r"$\sigma_{1}=0.20-\frac{7.16-8.24}{27.10}\approx "
                    r"0.2399\approx 23.99\%.$"),

            example("18.3", "Numerical Option Delta & Gamma from PDE Grid"),
            question(r"Given $C(99)=6.575$, $C(100)=7.160$, $C(101)=7.772$, "
                     r"compute $\Delta$ and $\Gamma$ at $S=100$."),
            solution(r"Centered differences give"),
            display(r"$\Delta\approx 0.5985,\qquad \Gamma\approx 0.0270.$"),

            example("18.4", "Antithetic Monte Carlo Accuracy"),
            question(r"Estimate $\mathbb{E}[e^{0.2Z}]$ using $Z_{1}=+1.0$ vs. "
                     r"the antithetic pair."),
            solution(r"The antithetic average is"),
            display(r"$\frac{1}{2}(e^{0.2}+e^{-0.2})=\cosh(0.2)\approx "
                    r"1.02007.$"),
            para(r"This is about $1500\times$ more accurate than the "
                 r"single draw."),

            example("18.5", "Control Variate Speedup Factor"),
            question(r"A geometric Asian option controls an arithmetic Asian "
                     r"option, with $\rho=0.99$. Find the path speedup factor."),
            solution(r"The variance reduction factor is $1-\rho^{2}$, so"),
            display(r"$\frac{1}{1-\rho^{2}}=\frac{1}{1-0.99^{2}}\approx "
                    r"50.25.$"),
            para(r"About $50\times$ fewer paths are required for the same "
                 r"accuracy."),
        ],
        "20.3": [
            example("20.1", "2-State Bellman Equation Solution"),
            question(r"State $A$ pays $+10$ and transitions to $B$; state "
                     r"$B$ pays $0$ and returns to $A$. With $\gamma=0.8$, "
                     r"find $V(A)$ and $V(B)$."),
            solution(r"The Bellman equations are"),
            display(r"$V(A)=10+0.8V(B),\qquad V(B)=0.8V(A).$"),
            display(r"$V(A)=\frac{10}{1-0.64}\approx 27.78,\qquad "
                    r"V(B)\approx 22.22.$"),

            example("20.2", "Tabular Q-Learning Update"),
            question(r"Given $Q(s,a)=5.0$, $r=4.0$, "
                     r"$\max_{a'}Q(s',a')=10.0$, $\gamma=0.9$, $\alpha=0.2$, "
                     r"compute $Q_{\mathrm{new}}$."),
            solution(r"The TD target and error are"),
            display(r"$y=4.0+0.9(10.0)=13.0,\qquad \delta=13.0-5.0=8.0.$"),
            para(r"The update is"),
            display(r"$Q_{\mathrm{new}}=5.0+0.2(8.0)=6.60.$"),

            example("20.3", "PPO Clipped Surrogate Evaluation"),
            question(r"With $\varepsilon=0.20$ and $r_{t}=1.50$, evaluate "
                     r"$L^{\mathrm{CLIP}}$ for (a) $\hat A_{t}=+2.0$ and "
                     r"(b) $\hat A_{t}=-2.0$."),
            solution(r"Since $r_{t}>1+\varepsilon$, clip to $1.20$:"),
            display(r"$(a)\ \min(1.5\times2,\ 1.2\times2)=2.40,$"),
            display(r"$(b)\ \min(1.5\times(-2),\ 1.2\times(-2))=-3.00.$"),

            example("20.4", "Almgren-Chriss Midday Inventory"),
            question(r"With $X_{0}=100{,}000$, $T=1$ day, $\kappa=2.0$, find "
                     r"the shares remaining at $t=0.5$ vs. TWAP."),
            solution(r"TWAP leaves $50{,}000$ shares at midday. The optimal "
                     r"trajectory is"),
            display(r"$x^{*}(t)=X_{0}\frac{\sinh(\kappa(T-t))}{\sinh(\kappa T)}.$"),
            para(r"At $t=0.5$:"),
            display(r"$x^{*}(0.5)=100{,}000\frac{\sinh(1)}{\sinh(2)}"
                    r"\approx 32{,}402.$"),

            example("20.5", "TWAP Temporary Impact Cost Scaling"),
            question(r"Liquidating $X_{0}=50{,}000$ shares via TWAP over "
                     r"$T=2$ hours with $\eta=0.0002$, find the temporary "
                     r"market impact cost."),
            solution(r"TWAP trades at constant rate, so"),
            display(r"$\text{Cost}=\frac{\eta X_{0}^{2}}{T}="
                    r"\frac{0.0002(5\times10^{4})^{2}}{2}="
                    r"\text{Rs. }250{,}000.$"),
        ],
        "21.3": [
            example("21.1", "Merton Jump Drift Compensator"),
            question(r"With $r=5\%$ and $\lambda=2$ crash jumps/yr of size "
                     r"$J-1=-10\%$ ($k=-0.10$), find the diffusive drift "
                     r"$r-\lambda k$ between jumps."),
            solution(r"Compensate the diffusion drift by the expected jump loss:"),
            display(r"$r-\lambda k=0.05-2(-0.10)=+0.25=25\%\ \text{per year}.$"),

            example("21.2", "Heston Feller Positivity Condition"),
            question(r"Verify whether $\kappa=3.0$, $\theta=0.04$, $\xi=0.40$ "
                     r"satisfy the Feller condition $2\kappa\theta\geq\xi^{2}$."),
            solution(r"Compute both sides:"),
            display(r"$2\kappa\theta=2(3.0)(0.04)=0.24\geq 0.16=\xi^{2}.$"),
            para(r"Hence $v_{t}>0$ strictly for all $t\geq0$."),

            example("21.3", "Dupire Local Volatility Evaluation"),
            question(r"At $K=100$, $r=0$, if "
                     r"$\frac{\partial C}{\partial T}=4.0$ and "
                     r"$\frac{\partial^{2}C}{\partial K^{2}}=0.02$, compute "
                     r"$\sigma_{\mathrm{loc}}(100,T)$."),
            solution(r"Dupire's formula gives"),
            display(r"$\sigma_{\mathrm{loc}}^{2}="
                    r"\frac{4.0}{\frac{1}{2}(100)^{2}(0.02)}="
                    r"\frac{4.0}{100}=0.04,$"),
            para(r"so $\sigma_{\mathrm{loc}}=20.0\%$."),

            example("21.4", "Vasicek Bond Rate Sensitivity B(τ)"),
            question(r"With $\kappa=0.5\ \mathrm{yr}^{-1}$, compute $B(2)$ for a "
                     r"2-year zero-coupon bond."),
            solution(r"The Vasicek duration function is"),
            display(r"$B(\tau)=\frac{1-e^{-\kappa\tau}}{\kappa}.$"),
            para(r"At $\tau=2$:"),
            display(r"$B(2)=\frac{1-e^{-1}}{0.5}=2(1-e^{-1})\approx 1.2642.$"),

            example("21.5", "Geometric Asian Effective Volatility"),
            question(r"Find the effective volatility $\sigma_{A}$ of a "
                     r"continuous geometric Asian option when "
                     r"$\sigma=30\%$."),
            solution(r"Averaging dampens volatility by $\sqrt{3}$:"),
            display(r"$\sigma_{A}=\frac{\sigma}{\sqrt{3}}="
                    r"\frac{30\%}{1.732}\approx 17.32\%.$"),
        ],
        "22.1": [
            para(r"Part A: Core Cross-Chapter Synthesis Exam (22.1 – 22.10)."),

            exam_block("22.1", "Ch. 1 + Ch. 5 — Additive Log-Odds Bayes Update",
                       r"Prove $\ln\frac{P(H\mid D)}{P(H^{c}\mid D)}="
                       r"\ln\frac{P(H)}{P(H^{c})}+"
                       r"\ln\frac{P(D\mid H)}{P(D\mid H^{c})}$.",
                       r"Divide Bayes' rule for $H$ by Bayes' rule for $H^{c}$. "
                       r"The factor $P(D)$ cancels:"),
            display(r"$\frac{P(H\mid D)}{P(H^{c}\mid D)}="
                    r"\frac{P(H)}{P(H^{c})}\cdot"
                    r"\frac{P(D\mid H)}{P(D\mid H^{c})}.$"),
            para(r"Taking logarithms turns the product into a sum."),

            exam_block("22.2", "Ch. 2 + Ch. 6 — 1D Newton Optimization Step",
                       r"Execute one Newton step "
                       r"$x_{1}=x_{0}-\frac{f'(x_{0})}{f''(x_{0})}$ on "
                       r"$f(x)=e^{x}-2x$ from $x_{0}=0$.",
                       r"Compute the derivatives:"),
            display(r"$f'(x)=e^{x}-2,\qquad f''(x)=e^{x}.$"),
            para(r"At $x_{0}=0$:"),
            display(r"$x_{1}=0-\frac{1-2}{1}=1.0.$"),

            exam_block("22.3", "Ch. 3 + Ch. 4 — Complex Eigenvalues of 2D Rotation",
                       r"Find the eigenvalues of "
                       r"$R(\theta)=\begin{pmatrix}\cos\theta&-\sin\theta\\"
                       r"\sin\theta&\cos\theta\end{pmatrix}$.",
                       r"The characteristic equation is"),
            display(r"$(\cos\theta-\lambda)^{2}+\sin^{2}\theta=0\implies "
                    r"\lambda=\cos\theta\pm i\sin\theta=e^{\pm i\theta}.$"),

            exam_block("22.4", "Ch. 4 + Ch. 5 — Cholesky Whitening Transform",
                       r"If $X\sim\mathcal{N}(\mu,\Sigma)$ with "
                       r"$\Sigma=LL^{T}$, find the distribution of "
                       r"$Z=L^{-1}(X-\mu)$.",
                       r"The mean is zero and the covariance is"),
            display(r"$\operatorname{Cov}(Z)=L^{-1}(LL^{T})L^{-T}=I,$"),
            para(r"so $Z\sim\mathcal{N}(0,I)$."),

            exam_block("22.5", "Ch. 5 + Ch. 9 — Label-Smoothing Cross-Entropy Optimum",
                       r"For smoothed target "
                       r"$\tilde y_{k}=(1-\varepsilon)y_{k}+\varepsilon/K$, "
                       r"what predicted distribution $p^{*}$ minimizes "
                       r"$H(\tilde y,p)$?",
                       r"Since $H(\tilde y,p)=H(\tilde y)+D_{\mathrm{KL}}(\tilde y\|p)$, "
                       r"the unique global minimizer is"),
            display(r"$p^{*}=\tilde y.$"),

            exam_block("22.6", "Ch. 6 + Ch. 7 — Optimal Kelly Growth Rate vs. Sharpe Ratio",
                       r"Evaluate $g(f)=f\mu-\frac{1}{2}f^{2}\sigma^{2}$ at "
                       r"the optimal Kelly leverage $f^{*}=\mu/\sigma^{2}$.",
                       r"Substituting $f^{*}$:"),
            display(r"$g(f^{*})=\frac{\mu^{2}}{2\sigma^{2}}="
                    r"\frac{1}{2}\mathrm{Sharpe}^{2}.$"),

            exam_block("22.7", "Ch. 7 + Ch. 8 — Antithetic BSM Call Estimate",
                       r"Compute the 2-path antithetic call estimate with "
                       r"$Z_{1}=+1.0$ ($S_{0}=K=100$, $r=0$, $\sigma=20\%$, "
                       r"$T=1$).",
                       r"The two paths are"),
            display(r"$S_{+}=100e^{0.18}\approx 119.72,\qquad "
                    r"S_{-}=100e^{-0.22}\approx 80.25.$"),
            para(r"The average payoff is"),
            display(r"$\hat C=\frac{1}{2}(19.72+0)=\text{Rs. }9.86.$"),

            exam_block("22.8", "Ch. 4 + Ch. 9 — Low-Rank Attention Complexity",
                       r"How does projecting keys/values to rank "
                       r"$k\ll N$ reduce attention complexity from "
                       r"$O(N^{2}d_{k})$?",
                       r"Compute $Q\tilde K^{T}$ with $\tilde K\in"
                       r"\mathbb{R}^{d_{k}\times k}$:"),
            display(r"$O(Nk\,d_{k})$ operations — linear in sequence length "
                    r"$N$ (for fixed $k$)."),

            exam_block("22.9", "Ch. 2 + Ch. 10 — Continuous Discount Rate",
                       r"Convert discrete discounting $\gamma^{t}$ into "
                       r"continuous-time exponential discounting "
                       r"$e^{-\rho t}$.",
                       r"Set $\gamma=e^{-\rho}$:"),
            display(r"$\rho=-\ln\gamma\approx 1-\gamma.$"),

            exam_block("22.10", "Ch. 7 + Ch. 11 — Bachelier Normal ATM Call Formula",
                       r"For $dS_{t}=\sigma_{N}dW_{t}$ ($r=0$), evaluate "
                       r"$C_{\mathrm{ATM}}=\mathbb{E}[\max(S_{T}-S_{0},0)]$.",
                       r"By symmetry of the normal density,"),
            display(r"$C_{\mathrm{ATM}}=\sigma_{N}\sqrt{\frac{T}{2\pi}}.$"),
        ],
        "22.2": [
            para(r"Part B & Part C: Advanced Wall Street Quant & PhD AI proofs (22.11 – 22.30)."),

            exam_block("22.11", "Boltzmann-Softmax Legendre Duality",
                       r"Maximize $p^{T}z-T\sum_{i=1}^{K}p_{i}\ln p_{i}$ "
                       r"subject to $\sum_{i}p_{i}=1$.",
                       r"The Lagrangian is "
                       r"$\mathcal{L}=p^{T}z-T\sum_{i}p_{i}\ln p_{i}-"
                       r"\nu(\sum_{i}p_{i}-1)$. Setting "
                       r"$\partial_{p_{i}}\mathcal{L}=0$:"),
            display(r"$z_{i}-T(\ln p_{i}+1)-\nu=0\implies "
                    r"p_{i}^{*}=\frac{e^{z_{i}/T}}{\sum_{j}e^{z_{j}/T}}.$"),
            para(r"The maximum value is $T\ln\left(\sum_{i}e^{z_{i}/T}\right)$."),

            exam_block("22.12", "Sherman-Morrison O(n) Covariance Inverse",
                       r"Verify $(\sigma^{2}I+\beta\beta^{T})^{-1}="
                       r"\sigma^{-2}I-\frac{\sigma^{-2}}{\sigma^{2}+"
                       r"\|\beta\|_{2}^{2}}\beta\beta^{T}$.",
                       r"By Sherman-Morrison,"),
            display(r"$(A+uv^{T})^{-1}=A^{-1}-"
                    r"\frac{A^{-1}uv^{T}A^{-1}}{1+v^{T}A^{-1}u}.$"),
            para(r"Take $A=\sigma^{2}I$, $u=v=\beta$. Then"),
            display(r"$(\sigma^{2}I+\beta\beta^{T})^{-1}="
                    r"\sigma^{-2}I-\frac{\sigma^{-2}}{\sigma^{2}+"
                    r"\|\beta\|_{2}^{2}}\beta\beta^{T}.$"),

            exam_block("22.13", "Fisher Information Matrix Identity",
                       r"Prove $I(\theta)=\mathbb{E}[(\nabla_{\theta}\ln p)"
                       r"(\nabla_{\theta}\ln p)^{T}]="
                       r"-\mathbb{E}[\nabla_{\theta}^{2}\ln p]$.",
                       r"Differentiate $\int p(x;\theta)\,dx=1$ twice under "
                       r"the integral sign using Leibniz's rule:"),
            display(r"$\int \nabla^{2}p\,dx=0\implies "
                    r"\mathbb{E}[\nabla^{2}\ln p]+"
                    r"\mathbb{E}[(\nabla\ln p)(\nabla\ln p)^{T}]=0.$"),
            para(r"Hence $I(\theta)=-\mathbb{E}[\nabla^{2}\ln p]="
                 r"\mathbb{E}[(\nabla\ln p)(\nabla\ln p)^{T}]$."),

            exam_block("22.14", "Stein's Lemma & VAE Reparameterization",
                       r"For $Z=\mu+\sigma\varepsilon\sim\mathcal{N}(\mu,"
                       r"\sigma^{2})$, prove "
                       r"$\operatorname{Cov}(Z,f(Z))=\sigma^{2}"
                       r"\mathbb{E}[f'(Z)]$.",
                       r"Integrate by parts with "
                       r"$\int f(\mu+\sigma\varepsilon)\,"
                       r"\varepsilon\phi(\varepsilon)\,d\varepsilon$:"),
            display(r"$\varepsilon\phi(\varepsilon)=-\phi'(\varepsilon)\implies "
                    r"\operatorname{Cov}(Z,f(Z))=\sigma^{2}"
                    r"\mathbb{E}[f'(Z)].$"),

            exam_block("22.15", "Novikov / Girsanov Exponential Martingale",
                       r"Prove $M_{t}=\exp\left(\theta W_{t}-"
                       r"\frac{1}{2}\theta^{2}t\right)$ is a martingale.",
                       r"By Itô's lemma,"),
            display(r"$dM_{t}=\theta M_{t}\,dW_{t}.$"),

            exam_block("22.16", "Black-Scholes ATM √T Approximation",
                       r"Prove $C_{\mathrm{ATM}}\approx S_{0}\sigma"
                       r"\sqrt{T/(2\pi)}\approx 0.4\,S_{0}\sigma\sqrt{T}$.",
                       r"Since $d_{1,2}=\pm\frac{1}{2}\sigma\sqrt{T}$ and "
                       r"$N(x)\approx\frac{1}{2}+\frac{x}{\sqrt{2\pi}}$:"),
            display(r"$C_{\mathrm{ATM}}\approx S_{0}\sigma"
                    r"\sqrt{T/(2\pi)}\approx 0.4\,S_{0}\sigma\sqrt{T}.$"),

            exam_block("22.17", "Perpetual American Put Smooth-Pasting Boundary",
                       r"Solve $\frac{1}{2}\sigma^{2}S^{2}V''+rSV'-rV=0$ for "
                       r"the optimal stopping boundary $S^{*}$.",
                       r"For $r>0$, the negative root is "
                       r"$\gamma_{-}=-2r/\sigma^{2}$. Smooth pasting gives"),
            display(r"$S^{*}=K\frac{\gamma_{-}}{\gamma_{-}-1}="
                    r"\frac{2r}{2r+\sigma^{2}}K.$"),

            exam_block("22.18", "Ridge Regression SVD Effective Degrees of Freedom",
                       r"Prove $\operatorname{tr}\left[X(X^{T}X+"
                       r"\lambda I)^{-1}X^{T}\right]=\sum_{i=1}^{r}"
                       r"\frac{\sigma_{i}^{2}}{\sigma_{i}^{2}+\lambda}$.",
                       r"Write $X=U\Sigma V^{T}$ and use cyclic trace:"),
            display(r"$\operatorname{tr}\left[X(X^{T}X+"
                    r"\lambda I)^{-1}X^{T}\right]=\sum_{i=1}^{r}"
                    r"\frac{\sigma_{i}^{2}}{\sigma_{i}^{2}+\lambda}.$"),

            exam_block("22.19", "CBOE VIX Variance Swap Log-Contract Replication",
                       r"Show how $d(\ln S_{t})$ replicates realized variance "
                       r"$\int_{0}^{T}\sigma_{t}^{2}dt$ using "
                       r"$1/K^{2}$-weighted OTM options.",
                       r"Itô's lemma on $\ln S_{t}$ gives"),
            display(r"$d(\ln S_{t})=\left(r-\frac{1}{2}\sigma_{t}^{2}"
                    r"\right)dt+\sigma_{t}dW_{t}^{Q}.$"),
            display(r"$\int_{0}^{T}\sigma_{t}^{2}dt=2\left[\int_{0}^{T}"
                    r"\frac{dS_{t}}{S_{t}}-\ln\frac{S_{T}}{S_{0}}\right].$"),

            exam_block("22.20", "RLHF / DPO Closed-Form Optimal Policy",
                       r"Maximize $\mathbb{E}_{y\sim\pi}[r(x,y)]-"
                       r"\beta D_{\mathrm{KL}}(\pi\|\pi_{\mathrm{ref}})$ "
                       r"over $\pi(y\mid x)$.",
                       r"Rewrite the objective as "
                       r"$-\beta D_{\mathrm{KL}}\left("
                       r"\pi\,\|\,\pi_{\mathrm{ref}}e^{r/\beta}/Z(x)\right)+"
                       r"\beta\ln Z(x)$. The unique global minimizer is"),
            display(r"$\pi^{*}(y\mid x)="
                    r"\frac{1}{Z(x)}\pi_{\mathrm{ref}}(y\mid x)"
                    r"\exp\left(\frac{r(x,y)}{\beta}\right).$"),

            exam_block("22.21", "Log-Sine Definite Integral Meets Fourier & Information Theory",
                       r"Using $\int_{0}^{\pi/2}\ln(\sin x)dx="
                       r"-\frac{\pi}{2}\ln 2$, evaluate "
                       r"$\int_{0}^{\pi}\ln(1-\cos x)dx$.",
                       r"Substitute $1-\cos x=2\sin^{2}(x/2)$:"),
            display(r"$\int_{0}^{\pi}\ln(1-\cos x)dx="
                    r"\pi\ln 2+4\int_{0}^{\pi/2}\ln(\sin u)du="
                    r"-\pi\ln 2.$"),

            exam_block("22.22", "Complex Roots of Unity Meets Binomial Series Selection",
                       r"Using $1+\omega+\omega^{2}=0$, prove "
                       r"$\sum_{k\equiv 0\!\pmod 3}\binom{n}{k}="
                       r"\frac{2^{n}+2\cos(n\pi/3)}{3}$.",
                       r"Sum $(1+x)^{n}$ at $x=1,\omega,\omega^{2}$:"),
            display(r"$2^{n}+(1+\omega)^{n}+(1+\omega^{2})^{n}="
                    r"2^{n}+(-\omega^{2})^{n}+(-\omega)^{n}="
                    r"2^{n}+2\cos(n\pi/3).$"),
            para(r"Dividing by $3$ extracts the every-third coefficient."),

            exam_block("22.23", "3D Euclidean Geometry Meets SVM Margin Optimization",
                       r"Find the exact SVM margin $\gamma$ and optimal weight "
                       r"vector $w^{*}$ separating $x_{+}=(3,4,5)^{T}$ and "
                       r"$x_{-}=(1,0,1)^{T}$.",
                       r"The difference vector is "
                       r"$\Delta x=x_{+}-x_{-}=(2,4,4)^{T}$ with "
                       r"$\|\Delta x\|_{2}=6$. The optimal weight is parallel "
                       r"to $\Delta x$:"),
            display(r"$w^{*}=\frac{\Delta x}{\|\Delta x\|_{2}^{2}}="
                    r"\left(\frac{1}{9},\frac{2}{9},\frac{2}{9}\right)^{T}.$"),
            para(r"The maximum margin is half the distance, $\gamma=3$."),

            exam_block("22.24", "Matrix Algebra & Cayley-Hamilton Meets Continuous-Time Markov Chains",
                       r"For $Q=\begin{pmatrix}-1&1\\2&-2\end{pmatrix}$, "
                       r"verify $Q^{2}=-3Q$ and compute "
                       r"$P(t)=e^{Qt}$ in closed form.",
                       r"First,"),
            display(r"$Q^{2}=-3Q.$"),
            para(r"Since $f(Q)=I+\frac{1-e^{-3t}}{3}Q$ solves the same "
                 r"exponential,"),
            display(r"$P(t)=e^{Qt}=I+\frac{1-e^{-3t}}{3}Q.$"),

            exam_block("22.25", "Score-Based Diffusion Reverse SDE Drift",
                       r"Given forward Ornstein-Uhlenbeck diffusion "
                       r"$dx_{t}=-\frac{1}{2}\beta_{t}x_{t}dt+"
                       r"\sqrt{\beta_{t}}dW_{t}$, state Anderson's reverse-time "
                       r"SDE.",
                       r"Anderson's reverse-time SDE is"),
            display(r"$dx_{t}=\left[-\frac{1}{2}\beta_{t}x_{t}-"
                    r"\beta_{t}\nabla_{x}\ln p_{t}(x_{t})\right]dt+"
                    r"\sqrt{\beta_{t}}d\bar W_{t}.$"),

            exam_block("22.26", "Marchenko-Pastur Covariance Shrinkage Optimal Intensity",
                       r"Why does Ledoit-Wolf shrinkage "
                       r"$\hat\Sigma=(1-\alpha)S+\alpha\bar\lambda I$ pull "
                       r"small sample eigenvalues up and large ones down?",
                       r"Random sampling noise spreads sample eigenvalues "
                       r"outward relative to population eigenvalues. Convex "
                       r"combination with $\bar\lambda I$ compresses them "
                       r"toward the grand mean:"),
            display(r"$\bar\lambda=\frac{1}{N}\operatorname{tr}(S).$"),

            exam_block("22.27", "Feynman-Kac Derivation of the Vasicek Bond ODEs",
                       r"Substitute the affine ansatz "
                       r"$P(t,r)=e^{A(\tau)-B(\tau)r}$ into the Vasicek PDE "
                       r"and match the coefficient of $r$ to derive the ODE "
                       r"for $B(\tau)$.",
                       r"Collecting terms in $r$ gives"),
            display(r"$B'(\tau)+\kappa B(\tau)=1,\qquad B(0)=0.$"),
            para(r"Hence"),
            display(r"$B(\tau)=\frac{1-e^{-\kappa\tau}}{\kappa}.$"),

            exam_block("22.28", "Black-Scholes Barenblatt PDE for Uncertain Volatility",
                       r"Under uncertain volatility $\sigma_{t}\in"
                       r"[\sigma_{\min},\sigma_{\max}]$, which volatility is "
                       r"selected in the worst-case pricing PDE?",
                       r"A short-gamma seller chooses $\sigma(\Gamma)="
                       r"\sigma_{\max}$ when $\Gamma>0$, and "
                       r"$\sigma(\Gamma)=\sigma_{\min}$ when $\Gamma<0$."),

            exam_block("22.29", "Wasserstein GAN Kantorovich-Rubinstein Duality",
                       r"State the Kantorovich-Rubinstein dual of the "
                       r"1-Wasserstein distance.",
                       r"The dual representation is"),
            display(r"$W_{1}(\mathbb{P}_{r},\mathbb{P}_{g})="
                    r"\sup_{\|f\|_{L}\leq 1}"
                    r"\mathbb{E}_{x\sim\mathbb{P}_{r}}[f(x)]-"
                    r"\mathbb{E}_{z\sim p(z)}[f(G(z))].$"),

            exam_block("22.30", "Multi-Asset Kelly vs. Tangency Portfolio Identity",
                       r"For continuous correlated GBM "
                       r"$dS_{t}=\operatorname{diag}(S_{t})(\mu dt+"
                       r"\Sigma^{1/2}dW_{t})$, prove the growth-optimal Kelly "
                       r"portfolio maximizes "
                       r"$g(f)=r+f^{T}(\mu-r\mathbf{1})-"
                       r"\frac{1}{2}f^{T}\Sigma f$.",
                       r"Taking the gradient with respect to $f$:"),
            display(r"$\nabla_{f}g=(\mu-r\mathbf{1})-\Sigma f=0\implies "
                    r"f^{*}=\Sigma^{-1}(\mu-r\mathbf{1}).$"),
            para(r"This is proportional to the Markowitz maximum-Sharpe "
                 r"tangency portfolio."),
        ],
        "2.1": [
            para("A complex number is $z=x+iy$ "
                 "$(x,y\\in\\mathbb{R})$, where $i^{2}=-1$, "
                 "$x=\\operatorname{Re}(z)$, and "
                 "$y=\\operatorname{Im}(z)$. Since $i^{4}=1$, powers of "
                 "$i$ are periodic with period $4$: $i^{4k+r}=i^{r}$, and "
                 "the sum of any four consecutive powers of $i$ is zero "
                 "($i^{n}+i^{n+1}+i^{n+2}+i^{n+3}=0$)."),
            bullet("Conjugate $\\bar{z}=x-iy$ & Modulus "
                   "$|z|=\\sqrt{x^{2}+y^{2}}$:"),
            display("$z\\bar{z}=|z|^{2}=x^{2}+y^{2},\\qquad "
                    "z^{-1}=\\frac{\\bar{z}}{|z|^{2}},\\qquad "
                    "z_{1}\\pm z_{2}=\\bar{z}_{1}\\pm\\bar{z}_{2},\\qquad "
                    "\\overline{z_{1}z_{2}}=\\bar{z}_{1}\\bar{z}_{2},\\qquad "
                    "|z_{1}z_{2}|=|z_{1}||z_{2}|.$"),
            bullet("Square Root of a Complex Number $z=a+ib$ "
                   "$(b\\neq 0)$:"),
            display("$\\sqrt{a+ib}=\\pm\\left("
                    "\\sqrt{\\frac{|z|+a}{2}}+"
                    "i\\,\\operatorname{sgn}(b)"
                    "\\sqrt{\\frac{|z|-a}{2}}\\right),\\qquad "
                    "\\text{where } |z|=\\sqrt{a^{2}+b^{2}}.$"),
            bullet("Polar & Euler Representation: In the Argand plane, if "
                   "$(x,y)=(r\\cos\\theta,r\\sin\\theta)$ with $r=|z|$ and "
                   "principal argument "
                   "$\\theta=\\operatorname{Arg}(z)\\in(-\\pi,\\pi]$, "
                   "Euler's formula states:"),
            display("$z=r(\\cos\\theta+i\\sin\\theta)=re^{i\\theta},\\qquad "
                    "z_{1}z_{2}=r_{1}r_{2}e^{i(\\theta_{1}+\\theta_{2})},"
                    "\\qquad \\frac{z_{1}}{z_{2}}="
                    "\\frac{r_{1}}{r_{2}}e^{i(\\theta_{1}-\\theta_{2})}.$"),
            theorem("2.1",
                    "Triangle Inequality, Parallelogram Law, De Moivre's "
                    "Theorem & Cube Roots of Unity",
                    "1. Triangle Inequality & Parallelogram Identity: For "
                    "any $z_{1},z_{2}\\in\\mathbb{C}$:"),
            display("$|z_{1}|-|z_{2}|\\leq|z_{1}\\pm z_{2}|\\leq"
                    "|z_{1}|+|z_{2}|,\\qquad "
                    "|z_{1}+z_{2}|^{2}+|z_{1}-z_{2}|^{2}="
                    "2|z_{1}|^{2}+2|z_{2}|^{2}.$"),
            para("2. De Moivre's Theorem: "
                 "$(\\cos\\theta+i\\sin\\theta)^{n}="
                 "\\cos(n\\theta)+i\\sin(n\\theta)$."),
            para("3. Cube Roots of Unity $(z^{3}=1)$: Factor "
                 "$z^{3}-1=(z-1)(z^{2}+z+1)=0$ to obtain $1$, "
                 "$\\omega=e^{i2\\pi/3}="
                 "\\frac{-1+i\\sqrt{3}}{2}$, and "
                 "$\\omega^{2}=e^{i4\\pi/3}="
                 "\\frac{-1-i\\sqrt{3}}{2}$, satisfying:"),
            display("$\\omega^{3}=1,\\qquad 1+\\omega+\\omega^{2}=0,"
                    "\\qquad a^{3}+b^{3}+c^{3}-3abc="
                    "(a+b+c)(a+b\\omega+c\\omega^{2})"
                    "(a+b\\omega^{2}+c\\omega).$"),
            para("4. Coni's Rotation Theorem & Argand Loci: If vector "
                 "$z_{2}-z_{0}$ is rotated counterclockwise by angle "
                 "$\\alpha$ and scaled by "
                 "$|z_{3}-z_{0}|/|z_{2}-z_{0}|$ to obtain $z_{3}-z_{0}$, "
                 "then $\\frac{z_{3}-z_{0}}{z_{2}-z_{0}}="
                 "\\frac{|z_{3}-z_{0}|}{|z_{2}-z_{0}|}e^{i\\alpha}$. An "
                 "equilateral triangle with vertices $z_{1},z_{2},z_{3}$ "
                 "satisfies $z_{1}^{2}+z_{2}^{2}+z_{3}^{2}="
                 "z_{1}z_{2}+z_{2}z_{3}+z_{3}z_{1}$."),
            proof("Triangle Inequality",
                  "Expand $|z_{1}+z_{2}|^{2}=(z_{1}+z_{2})"
                  "(\\bar{z}_{1}+\\bar{z}_{2})="
                  "|z_{1}|^{2}+|z_{2}|^{2}+"
                  "2\\operatorname{Re}(z_{1}\\bar{z}_{2})$. Since "
                  "$\\operatorname{Re}(w)\\leq|w|="
                  "|z_{1}\\bar{z}_{2}|=|z_{1}||z_{2}|$, we have "
                  "$|z_{1}+z_{2}|^{2}\\leq"
                  "(|z_{1}|+|z_{2}|)^{2}$, hence "
                  "$|z_{1}+z_{2}|\\leq|z_{1}|+|z_{2}|$ (with equality iff "
                  "$z_{1}/z_{2}\\in\\mathbb{R}_{\\geq 0}$, i.e., "
                  "$\\arg z_{1}=\\arg z_{2}$). $\\blacksquare$"),
        ],
        "2.2": [
            para("For $f(x)=ax^{2}+bx+c=0$ $(a\\neq 0)$ with discriminant "
                 "$D=b^{2}-4ac$ and roots "
                 "$\\alpha,\\beta=\\frac{-b\\pm\\sqrt{D}}{2a}$:"),
            bullet("Vieta's Relations & Symmetric Identities: "
                   "$\\alpha+\\beta=-\\frac{b}{a}$ and "
                   "$\\alpha\\beta=\\frac{c}{a}$. From these:"),
            display("$\\alpha^{2}+\\beta^{2}=(\\alpha+\\beta)^{2}-2\\alpha"
                    "\\beta,\\qquad |\\alpha-\\beta|=\\frac{\\sqrt{D}}{|a|},"
                    "\\qquad \\alpha^{3}+\\beta^{3}=(\\alpha+\\beta)^{3}-"
                    "3\\alpha\\beta(\\alpha+\\beta).$"),
            bullet("Newton's Recurrence for High-Power Root Sums "
                   "$S_{n}=\\alpha^{n}+\\beta^{n}$: Since "
                   "$a\\alpha^{2}+b\\alpha+c=0$, multiplying by "
                   "$\\alpha^{n-2}$ and adding the $\\beta$ equation gives "
                   "$aS_{n}+bS_{n-1}+cS_{n-2}=0$ for all "
                   "$n\\in\\mathbb{Z}$!"),
            bullet("Condition for Common Roots of "
                   "$a_{1}x^{2}+b_{1}x+c_{1}=0$ and "
                   "$a_{2}x^{2}+b_{2}x+c_{2}=0$:"),
            para("1. Both roots common: "
                 "$\\frac{a_{1}}{a_{2}}=\\frac{b_{1}}{b_{2}}="
                 "\\frac{c_{1}}{c_{2}}$."),
            para("2. At least one root common (by Cramer's Rule on $x^{2}$ "
                 "and $x$): $(c_{1}a_{2}-c_{2}a_{1})^{2}="
                 "(a_{1}b_{2}-a_{2}b_{1})(b_{1}c_{2}-b_{2}c_{1})$."),
            bullet("Master Table of Location of Roots for "
                   "$f(x)=ax^{2}+bx+c=0$ "
                   "$\\left(x_{v}=-\\frac{b}{2a}\\right)$:"),
            para("1. Both roots strictly greater than $k$ "
                 "$(\\alpha,\\beta>k)$: $D\\geq 0$, $x_{v}>k$, and "
                 "$a\\cdot f(k)>0$."),
            para("2. Both roots strictly less than $k$ "
                 "$(\\alpha,\\beta<k)$: $D\\geq 0$, $x_{v}<k$, and "
                 "$a\\cdot f(k)>0$."),
            para("3. Number $k$ lies strictly between the roots "
                 "$(\\alpha<k<\\beta)$: the single condition "
                 "$a\\cdot f(k)<0$ (which automatically guarantees "
                 "$D>0$)."),
            para("4. Both roots lie strictly inside $(k_{1},k_{2})$: "
                 "$D\\geq 0$, $k_{1}<x_{v}<k_{2}$, $a\\cdot f(k_{1})>0$, "
                 "and $a\\cdot f(k_{2})>0$."),
            para("5. Exactly one root lies strictly inside $(k_{1},k_{2})$: "
                 "$f(k_{1})\\cdot f(k_{2})<0$ (check boundary roots "
                 "$f(k_{i})=0$ separately)."),
        ],
        "2.4": [
            para("Naive algebra solves quadratic problems by brute-force root "
                 "formulas or tedious symmetric expansions. Structural algebra "
                 "replaces brute force with three general theorems:"),
            bullet("General Theory of Transformation of Polynomial Equations "
                   "$(y=\\phi(x))$: Suppose $P(x)=a_{n}x^{n}+\\cdots+a_{0}=0$ "
                   "has roots $\\alpha_{1},\\dots,\\alpha_{n}$, and we seek the "
                   "polynomial $Q(y)=0$ whose roots are "
                   "$\\beta_{i}=\\phi(\\alpha_{i})$:"),
            para("• Invertible Substitution Case: If $y=\\phi(x)$ can be "
                 "inverted to $x=\\phi^{-1}(y)$, simply substitute "
                 "$x=\\phi^{-1}(y)$ directly into $P(x)=0$:"),
            display("$\\text{Reciprocal roots } y=\\frac{1}{\\alpha_{i}}\\ "
                    "\\Longrightarrow\\ x=\\frac{1}{y}\\ \\Longrightarrow\\ "
                    "y^{n}P\\!\\left(\\frac{1}{y}\\right)=a_{0}y^{n}+"
                    "a_{1}y^{n-1}+\\cdots+a_{n}=0,$"),
            display("$\\text{Shifted roots } y=\\alpha_{i}+h\\ "
                    "\\Longrightarrow\\ P(y-h)=0,\\qquad "
                    "\\text{Scaled roots } y=k\\alpha_{i}\\ "
                    "\\Longrightarrow\\ P\\!\\left(\\frac{y}{k}\\right)=0.$"),
            para("• Quadratic/Rational Transformation "
                 "$y=\\alpha_{i}^{2}+c$: Substitute $x^{2}=y-c$ into "
                 "$ax^{2}+c_{0}=-bx$, then square both sides to eliminate "
                 "$x$: $\\left[a(y-c)+c_{0}\\right]^{2}=b^{2}(y-c)$, yielding "
                 "the transformed quadratic in a single line!"),
            bullet("Canonical Square Completion & Global Sign Analysis of "
                   "$f(x)=ax^{2}+bx+c$: Always check the degenerate linear "
                   "case $a=0$ first! For $a\\neq 0$, completing the square "
                   "yields the canonical vertex form:"),
            display("$f(x)=a\\left(x+\\frac{b}{2a}\\right)^{2}-"
                    "\\frac{b^{2}-4ac}{4a}=a\\left(x+\\frac{b}{2a}\\right)^{2}-"
                    "\\frac{D}{4a},\\qquad D=b^{2}-4ac.$"),
            para("Since $\\left(x+\\frac{b}{2a}\\right)^{2}\\geq 0$ for all "
                 "$x\\in\\mathbb{R}$ and vanishes at "
                 "$x_{v}=-\\frac{b}{2a}$, we have "
                 "$f(x)>0\\ \\forall x\\in\\mathbb{R}\\iff a>0$ and "
                 "$-\\frac{D}{4a}>0\\iff a>0$ and $D<0$."),
            bullet("Sylvester's Resultant Derivation of the Common-Root "
                   "Condition: If $a_{1}x^{2}+b_{1}x+c_{1}=0$ and "
                   "$a_{2}x^{2}+b_{2}x+c_{2}=0$ share a root $\\alpha$, treat "
                   "$(\\alpha^{2},\\alpha)$ as two linear unknowns in a "
                   "$2\\times 2$ linear system and apply Cramer's Rule:"),
            display("$\\alpha^{2}=\\frac{b_{1}c_{2}-b_{2}c_{1}}"
                    "{a_{1}b_{2}-a_{2}b_{1}},\\qquad "
                    "\\alpha=\\frac{c_{1}a_{2}-c_{2}a_{1}}"
                    "{a_{1}b_{2}-a_{2}b_{1}}.$"),
            display("$\\Longrightarrow\\ (c_{1}a_{2}-c_{2}a_{1})^{2}="
                    "(a_{1}b_{2}-a_{2}b_{1})(b_{1}c_{2}-b_{2}c_{1}).$"),
        ],
        "7.2": [
            para("1. Euler's Beta & Gamma Function Unification of All "
                 "Trigonometric Integrals: For $p,q>0$, Euler's Beta integral "
                 "$B(p,q)=\\int_{0}^{1}t^{p-1}(1-t)^{q-1}\\,dt="
                 "\\frac{\\Gamma(p)\\Gamma(q)}{\\Gamma(p+q)}$ under the "
                 "substitution $t=\\sin^{2}x$ "
                 "$(dt=2\\sin x\\cos x\\,dx)$ becomes:"),
            display("$\\int_{0}^{\\pi/2}\\sin^{2p-1}x\\cos^{2q-1}x\\,dx="
                    "B(p,q)=\\frac{\\Gamma(p)\\Gamma(q)}"
                    "{2\\Gamma(p+q)},\\qquad \\text{where } "
                    "\\Gamma(n+1)=n!,\\ \\Gamma\\!\\left(\\frac{1}{2}\\right)="
                    "\\sqrt{\\pi}.$"),
            para("Setting $2p-1=m$ and $2q-1=n$ gives "
                 "$\\int_{0}^{\\pi/2}\\sin^{m}x\\cos^{n}x\\,dx="
                 "\\frac{\\Gamma\\!\\left(\\frac{m+1}{2}\\right)"
                 "\\Gamma\\!\\left(\\frac{n+1}{2}\\right)}"
                 "{2\\Gamma\\!\\left(\\frac{m+n+2}{2}\\right)}$, which "
                 "derives Wallis' Formula for both even and odd powers "
                 "simultaneously!"),
            para("2. Derivative-Method Decomposition for "
                 "$\\int\\frac{P(x)}{\\sqrt{ax^{2}+bx+c}}\\,dx$: For any "
                 "polynomial $P(x)$ of degree $n\\geq1$, there exist unique "
                 "constants $\\lambda$ and a polynomial $Q(x)$ of degree "
                 "$n-1$ such that:"),
            display("$\\int\\frac{P(x)}{\\sqrt{ax^{2}+bx+c}}\\,dx="
                    "Q(x)\\sqrt{ax^{2}+bx+c}+\\lambda\\int"
                    "\\frac{dx}{\\sqrt{ax^{2}+bx+c}},$"),
            para("found by differentiating both sides, multiplying by "
                 "$\\sqrt{ax^{2}+bx+c}$, and matching polynomial "
                 "coefficients!"),
        ],
        "2.3": [
            para("To solve a rational inequality "
                 "$\\frac{P(x)}{Q(x)}\\geq 0$:"),
            para("1. Move all terms to the LHS so the RHS is $0$, and factor "
                 "the numerator and denominator into linear factors "
                 "$(x-r_{i})^{m_{i}}$ with leading coefficients of $x$ "
                 "strictly positive $+1$."),
            para("2. Plot all roots $r_{1}<r_{2}<\\cdots<r_{k}$ on the real "
                 "line. Mark denominator roots with open circles (strictly "
                 "excluded!)."),
            para("3. In the rightmost interval $(r_{k},\\infty)$, the sign "
                 "is $+$. Moving left across each root $r_{i}$: flip the "
                 "sign if multiplicity $m_{i}$ is odd, and keep the same "
                 "sign if $m_{i}$ is even."),
        ],
    }
    for c in chapters:
        for s in c["sections"]:
            if s["num"] in overrides:
                if any(b.get("type") == "example" for b in overrides[s["num"]]):
                    # Keep the graded-problem tier that follows the worked
                    # examples; only the examples are replaced.
                    first_problem = next(
                        (i for i, b in enumerate(s["blocks"])
                         if b["type"] == "problem"),
                        len(s["blocks"]))
                    s["blocks"] = (overrides[s["num"]] +
                                   s["blocks"][first_problem:])
                else:
                    s["blocks"] = overrides[s["num"]]

    # Worked-example titles that swallowed a formula fragment from the
    # heading line. Restore the human-readable titles.
    title_fixes = {
        ("1.6", "problem", "1.7"): "Domain & Range of √(16−x²)",
        ("1.6", "problem", "1.11"): "Parity Check of ln(x+√(x²+1))",
        ("1.6", "problem", "1.13"): "Domain of 1/√(⌊x⌋²−5⌊x⌋+6)",
        ("1.6", "problem", "1.14"): "Range of f(x)=x/(1+x²)",
        ("3.4", "problem", "3.16"): "Sum of Weighted Binomial Squares",
        ("7.3", "problem", "7.14"): "Trig Denominator Integral",
        ("7.3", "problem", "7.18"): "Wallis' Formula Integrals",
        ("13.4", "problem", "13.12"): "Parseval's Identity for Odd Squares",
        ("13.4", "problem", "13.21"): "Basel Series via Parseval's Theorem",
        ("17.3", "example", "17.1"): "Itô's Lemma on W³",
        ("17.4", "problem", "17.6"): "Itô Integral ∫ Wt dWt",
        ("2.5", "example", "2.1"): "Argand Locus of a Purely Imaginary Quotient",
        ("2.5", "example", "2.6"): "Double-Modulus Inequality |x² − 5x + 4| ≤ 6",
        ("6.5", "example", "6.2"): "1^∞ Indeterminate Form Limit & Piecewise Continuity",
        ("6.5", "example", "6.4"): "Differential Identity for y = e^{ax}",
        ("7.3", "example", "7.1"): "Algebraic Twin Substitution",
        ("2.5", "problem", "2.1"): "Least Positive Integer Power of (1+i)/(1−i)",
        ("3.4", "problem", "3.9"): "Sum of Series with Tk = 1/(k(k+1)(k+3))",
        ("3.4", "problem", "3.20"): "Minimum of sec²θ + 4 csc²θ via AM-GM",
        ("2.5", "problem", "2.14"): "Number of Real Roots of x²−3|x|+2=0",
        ("2.5", "problem", "2.19"): "Number Separating the Roots",
        ("7.3", "example", "7.2"): "Integral of ln(sin x) from 0 to π/2",
    }
    for c in chapters:
        for s in c["sections"]:
            for b in s["blocks"]:
                if b.get("type") in ("example", "problem", "exam"):
                    fixed = title_fixes.get((s["num"], b.get("type"), b.get("num")))
                    if fixed:
                        b["title"] = fixed

    # Curated problem statements where the PDF's fraction rows were split
    # into separate text/display fragments.
    statement_fixes = {
        ("2.5", "example", "2.1"): r"Let $z=x+iy\in\mathbb{C}$. Find the Cartesian "
                        r"equation and geometric locus of points $z$ such that "
                        r"$\frac{z-1}{z+i}$ is purely imaginary.",
        ("2.5", "example", "2.2"): r"If $\alpha$ and $\beta$ are the roots of "
                        r"$x^{2}-6x-2=0$ and "
                        r"$a_{n}=\alpha^{n}-\beta^{n}$ for $n\geq1$, find "
                        r"the exact numerical value of "
                        r"$\frac{a_{10}-2a_{8}}{2a_{9}}$.",
        ("2.5", "example", "2.4"): r"Solve the rational inequality "
                        r"$\frac{(x-1)^{3}(x+2)^{4}(x-3)^{5}}"
                        r"{(x+1)^{2}(x-4)}\leq0$ for "
                        r"$x\in\mathbb{R}$.",
        ("2.5", "example", "2.5"): r"Let $\omega=e^{i2\pi/3}$ be a complex cube root of "
                        r"unity. Evaluate "
                        r"$S=\sum_{k=1}^{100}\left(\omega^{k}+"
                        r"\omega^{2k}\right)$ and simplify "
                        r"$(1-\omega+\omega^{2})^{5}+"
                        r"(1+\omega-\omega^{2})^{5}$.",
        ("2.5", "example", "2.6"): r"Solve the inequality "
                        r"$|x^{2}-5x+4|\leq6$ for "
                        r"$x\in\mathbb{R}$.",
        ("7.3", "example", "7.1"): r"Evaluate "
                        r"$I_{1}=\int\frac{x^{2}+1}{x^{4}+1}\,dx$ and "
                        r"$I_{2}=\int\frac{x^{2}-1}{x^{4}+1}\,dx$.",
        ("7.3", "example", "7.2"): r"Evaluate "
                        r"$I=\int_{0}^{\pi/2}\ln(\sin x)\,dx$ using "
                        r"King's Property.",
        ("1.6", "problem", "1.1"): r"Two finite sets have $m$ and $n$ elements. The "
                        r"number of subsets of the first set is $112$ more "
                        r"than that of the second set. Find $(m,n)$.",
        ("1.6", "problem", "1.2"): r"In a survey of $100$ consumers, $72$ like Product $A$ "
                        r"and $45$ like Product $B$. Find the minimum and "
                        r"maximum possible values of $|A\cap B|$.",
        ("1.6", "problem", "1.3"): r"Using set algebra laws, simplify "
                        r"$(A\cup B)\cap(A\cup B^{c})$.",
        ("1.6", "problem", "1.4"): r"Let $|A|=4$. Find (a) total relations on $A$, "
                        r"(b) reflexive relations on $A$, and (c) relations "
                        r"that are both reflexive and symmetric on $A$.",
        ("1.6", "problem", "1.5"): r"On $A=\{0,1,\ldots,12\}$, let "
                        r"$R=\{(a,b):|a-b|\text{ is a multiple of }4\}$. "
                        r"List the equivalence class $[1]$ and the total "
                        r"number of distinct equivalence classes.",
        ("1.6", "problem", "1.6"): r"Find the domain of "
                        r"$f(x)=\sqrt{\frac{1}{9-x^{2}}}+\ln(x-1)$.",
        ("1.6", "problem", "1.7"): r"Find the domain and range of "
                        r"$f(x)=\sqrt{16-x^{2}}$.",
        ("1.6", "problem", "1.8"): r"Find the domain and range of "
                        r"$f(x)=\frac{|x-4|}{x-4}$.",
        ("1.6", "problem", "1.9"): r"Find the exact number of onto (surjective) functions "
                        r"from $A=\{1,2,3,4,5\}$ onto $B=\{a,b,c\}$.",
        ("1.6", "problem", "1.10"): r"If $f(x)=\frac{4x+3}{6x-4}$ for $x\neq\frac{2}{3}$, "
                         r"prove that $(f\circ f)(x)=x$ and find $f^{-1}(x)$.",
        ("1.6", "problem", "1.11"): r"Prove that $f(x)=\ln(x+\sqrt{x^{2}+1})$ is an odd "
                         r"function on $\mathbb{R}$.",
        ("1.6", "problem", "1.12"): r"Determine whether "
                         r"$f(x)=\frac{x(ax+1)}{ax-1}$ with $a>0$, $a\neq1$, "
                         r"$x\neq0$, is even or odd.",
        ("1.6", "problem", "1.13"): r"Find the domain of "
                         r"$f(x)=\frac{1}{\sqrt{\lfloor x\rfloor^{2}-5\lfloor x\rfloor+6}}$.",
        ("1.6", "problem", "1.14"): r"Find the exact range of "
                         r"$f(x)=\frac{x}{1+x^{2}}$ over $x\in\mathbb{R}$.",
        ("1.6", "problem", "1.15"): r"Given $f(x)=\frac{4x}{4^{x}+2}$, evaluate the sum "
                         r"$S=\sum_{k=1}^{99}f(k/100)$.",
        ("1.6", "problem", "1.16"): r"Find the fundamental period of "
                         r"$f(x)=|\sin x|+|\cos x|$.",
        ("1.6", "problem", "1.17"): r"Find the inverse of the bijection "
                         r"$f:\mathbb{R}\to\mathbb{R}$ defined by "
                         r"$f(x)=\frac{e^{x}-e^{-x}}{2}$.",
        ("1.6", "problem", "1.18"): r"Find the inverse of $f:\mathbb{R}\to(0,1)$ given by "
                         r"$f(x)=\frac{10^{x}}{10^{x}+1}$ (the base-10 sigmoid).",
        ("1.6", "problem", "1.19"): r"If $f:\mathbb{N}\to\mathbb{R}$ satisfies "
                         r"$f(x+y)=f(x)f(y)$ for all $x,y\in\mathbb{N}$, "
                         r"$f(1)=3$, and $\sum_{k=1}^{n}f(k)=363$, find $n$.",
        ("1.6", "problem", "1.20"): r"Find the exact domain of "
                         r"$f(x)=\sqrt{1-\sqrt{1-\sqrt{1-x^{2}}}}$.",
        ("1.6", "problem", "1.21"): r"Two document token sets have $|A|=80$, $|B|=60$, and "
                         r"$|A\cup B|=100$. Compute the Jaccard similarity "
                         r"$J(A,B)=\frac{|A\cap B|}{|A\cup B|}$ and Jaccard distance "
                         r"$d_{J}(A,B)=1-J(A,B)$.",
        ("1.6", "problem", "1.22"): r"How many distinct Boolean classification functions "
                         r"$f:\{0,1\}^{d}\to\{0,1\}$ exist on $d=4$ binary features?",
        ("1.6", "problem", "1.23"): r"Show that the logistic sigmoid "
                         r"$\sigma:\mathbb{R}\to(0,1)$ given by "
                         r"$\sigma(z)=\frac{1}{1+e^{-z}}$ satisfies "
                         r"$\sigma(-z)=1-\sigma(z)$ and find its inverse "
                         r"$\sigma^{-1}(p)$.",
        ("1.6", "problem", "1.24"): r"Let $\operatorname{ReLU}(x)=\max(0,x)$ and "
                         r"$\operatorname{Softplus}(x)=\ln(1+e^{x})$. Prove "
                         r"$\operatorname{Softplus}(x)-\operatorname{Softplus}(-x)=x$.",
        ("1.6", "problem", "1.25"): r"For $z\in\mathbb{R}^{K}$, "
                         r"$\operatorname{Softmax}(z)_{i}=\frac{e^{z_{i}}}"
                         r"{\sum_{j=1}^{K}e^{z_{j}}}$. Prove that "
                         r"$\operatorname{Softmax}(z+c\mathbf{1})="
                         r"\operatorname{Softmax}(z)$ for any scalar $c$.",
        ("1.6", "problem", "1.26"): r"A call payoff is $C(S)=\max(S-K,0)$ and a put payoff "
                         r"is $P(S)=\max(K-S,0)$. Using "
                         r"$\max(u,0)=\frac{u+|u|}{2}$, prove "
                         r"$C(S)-P(S)=S-K$ and $C(S)+P(S)=|S-K|$.",
        ("1.6", "problem", "1.27"): r"Find the unique even and odd parts of "
                         r"$f(x)=e^{x}$.",
        ("1.6", "problem", "1.28"): r"In Monte Carlo simulation, $U\in(0,1]$ is mapped to "
                         r"$R=\sqrt{-2\ln U}$. Find the exact range of $R$.",
        ("1.6", "problem", "1.29"): r"Zero-coupon bond discounting maps continuous yield "
                         r"$y\in(0,\infty)$ to discount factor "
                         r"$D(y)=e^{-yT}$ with $T>0$. Find its range and inverse.",
        ("1.6", "problem", "1.30"): r"Given a feature map $\phi:\mathcal{X}\to"
                         r"\mathbb{R}^{m}$, define $x_{1}\sim x_{2}\iff "
                         r"\phi(x_{1})=\phi(x_{2})$. Prove that $\sim$ is an "
                         r"equivalence relation and describe its equivalence classes.",
        ("3.4", "problem", "3.16"): r"Evaluate $\sum_{r=0}^{n}r\binom{n}{r}^{2}$ in closed form.",
        ("7.3", "problem", "7.14"): r"Evaluate $\int_{0}^{\infty}\frac{dx}{9\cos^{2}x+4\sin^{2}x}$.",
        ("7.3", "problem", "7.18"): r"Evaluate $\int_{0}^{\pi/2}\sin^{5}x\,dx$ and "
                         r"$\int_{0}^{\pi/2}\sin^{4}x\cos^{2}x\,dx$ using Wallis' formula.",
        ("13.4", "problem", "13.12"): r"Apply Parseval's theorem "
                          r"$\frac{1}{\pi}\int_{-\pi}^{\pi}|f(t)|^{2}dt="
                          r"\sum_{n=1}^{\infty}b_{n}^{2}$ to Ex 13.11.",
        ("13.4", "problem", "13.21"): r"Apply Parseval's identity "
                          r"$\frac{1}{\pi}\int_{-\pi}^{\pi}x^{2}dx="
                          r"\sum_{n=1}^{\infty}b_{n}^{2}$ to $f(x)=x$ on "
                          r"$(-\pi,\pi)$ to deduce $\sum_{n=1}^{\infty}1/n^{2}=\pi^{2}/6$.",
        ("17.4", "problem", "17.6"): r"Prove $\int_{0}^{T}W_{t}\,dW_{t}=\frac{1}{2}W_{T}^{2}-\frac{1}{2}T$.",
        ("17.3", "example", "17.1"): r"Compute the stochastic differential $d(W_{t}^{3})$ using Itô's lemma.",
        ("2.5", "problem", "2.29"): r"The Brenner-Subrahmanyam ATM call price with bid-ask "
                        r"cost is $C(\sigma)=0.4S\sqrt{T}\,\sigma-0.02S\sqrt{T}\,\sigma^{2}$. "
                        r"For $S=100$, $T=1$, solve $C(\sigma)\geq 7.5$ for "
                        r"$\sigma\in(0,5)$.",
        ("10.3", "problem", "10.30"): r"An equity quant signal has skill correlation "
                         r"$\mathrm{IC}=0.05$ across $N=400$ independent bets per "
                         r"year. Compute the expected Information Ratio "
                         r"$\mathrm{IR}=\mathrm{IC}\sqrt{N}$.",
        ("11.5", "problem", "11.24"): r"Prove that $f(q)=\sqrt{q}$ is subadditive on "
                          r"$q\geq 0$: $\sqrt{q_{1}+q_{2}}\leq "
                          r"\sqrt{q_{1}}+\sqrt{q_{2}}$.",
        ("12.4", "problem", "12.13"): r"Use the Gamma recursion to evaluate the "
                          r"factorial $\Gamma(n+1)=n!$.",
        ("12.4", "problem", "12.17"): r"Find the volume element in spherical coordinates "
                          r"$\mathrm{d}V=r^{2}\sin\theta\,\mathrm{d}r\,\mathrm{d}\theta\,\mathrm{d}\phi$.",
        ("14.4", "problem", "14.25"): r"For an $N\times T$ matrix of i.i.d. noise returns "
                          r"with variance $\sigma^{2}=1$ and aspect ratio "
                          r"$q=N/T=0.25$, compute the Marchenko-Pastur upper "
                          r"eigenvalue edge $\lambda_{+}=\sigma^{2}(1+\sqrt{q})^{2}$.",
        ("16.4", "problem", "16.13"): r"Prove that combining $BR$ independent signals "
                          r"with correlation $\mathrm{IC}$ yields Information "
                          r"Ratio $\mathrm{IR}=\mathrm{IC}\sqrt{BR}$.",
        ("18.4", "problem", "18.24"): r"If $N=10{,}000$, compare the theoretical QMC error "
                          r"scale $1/N$ with the standard Monte Carlo error "
                          r"scale $1/\sqrt{N}$.",
        ("2.5", "problem", "2.1"): r"Find the smallest positive integer $n$ such that "
                        r"$\left(\frac{1+i}{1-i}\right)^{n}=1$, and interpret the "
                        r"transformation geometrically in the Argand plane.",
        ("2.5", "problem", "2.2"): r"If $a+ib=\frac{(x+i)^{2}}{2x^{2}+1}$ "
                        r"with $x,a,b\in\mathbb{R}$, prove without expanding "
                        r"real and imaginary parts that "
                        r"$a^{2}+b^{2}=\frac{(x^{2}+1)^{2}}{(2x^{2}+1)^{2}}$.",
        ("2.5", "problem", "2.3"): r"Find the two complex square roots of "
                        r"$z=-7-24i$ by deriving the modulus-real-part system "
                        r"from first principles.",
        ("2.5", "problem", "2.4"): r"Express $z=-1-\sqrt{3}\,i$ in polar and "
                        r"Euler form with its exact principal argument "
                        r"$\operatorname{Arg}(z)\in(-\pi,\pi]$.",
        ("2.5", "problem", "2.5"): r"Simplify "
                        r"$W=\frac{(\cos 3\theta+i\sin 3\theta)^{4}"
                        r"(\cos 4\theta-i\sin 4\theta)^{5}}"
                        r"{(\cos 4\theta+i\sin 4\theta)^{3}"
                        r"(\cos 5\theta+i\sin 5\theta)^{-4}}$ completely.",
        ("2.5", "problem", "2.6"): r"If one root of $5x^{2}+13x+k=0$ is the "
                        r"reciprocal of the other, find $k$ and verify the "
                        r"nature of the resulting roots.",
        ("2.5", "problem", "2.7"): r"If $\alpha,\beta$ are the roots of "
                        r"$x^{2}-4x+5=0$, construct the quadratic whose roots "
                        r"are $\alpha^{2}+2$ and $\beta^{2}+2$ using both (a) "
                        r"the root-transformation substitution and (b) Vieta's "
                        r"symmetric sums.",
        ("2.5", "problem", "2.8"): r"Find all real values of $k$ for which "
                        r"$f(x)=kx^{2}-4x+k>0$ for every $x\in\mathbb{R}$, "
                        r"justifying both the degenerate boundary $k=0$ and the "
                        r"vertex extremum condition.",
        ("2.5", "problem", "2.9"): r"Solve the simultaneous linear inequalities "
                        r"$3x-7<5+x$ and $11-5x\leq 1$ for $x\in\mathbb{R}$ in "
                        r"interval notation.",
        ("2.5", "problem", "2.10"): r"Solve "
                        r"$\frac{|x-2|-1}{|x-2|-2}\leq 0$ for all real "
                        r"$x\in\mathbb{R}$.",
        ("2.5", "problem", "2.11"): r"Describe the locus of $z\in\mathbb{C}$ "
                        r"satisfying $\left|\frac{z-2}{z+2}\right|=3$.",
        ("2.5", "problem", "2.12"): r"If $|z-(3+4i)|=2$, find the maximum and "
                        r"minimum possible values of $|z|$.",
        ("2.5", "problem", "2.13"): r"If $x^{2}+ax+10=0$ and "
                        r"$x^{2}+bx-10=0$ share a common root $\alpha$, find "
                        r"the value of $a^{2}-b^{2}$.",
        ("2.5", "problem", "2.14"): r"Find all real solutions of "
                        r"$x^{2}-3|x|+2=0$.",
        ("2.5", "problem", "2.15"): r"Show that "
                        r"$\frac{x^{2}-bc}{2x-b-c}$ takes all real values for "
                        r"$x\in\mathbb{R}$ when $b\neq c$, and find the excluded "
                        r"interval.",
        ("2.5", "problem", "2.16"): r"Solve $\sqrt{x+6}>x$ for $x\in\mathbb{R}$.",
        ("2.5", "problem", "2.17"): r"Solve $\log_{0.5}(x^{2}-5x+6)\geq -1$ "
                        r"for $x\in\mathbb{R}$.",
        ("2.5", "problem", "2.18"): r"Let $1,\zeta_{1},\zeta_{2},\ldots,"
                        r"\zeta_{n-1}$ be the $n$-th roots of unity. Evaluate "
                        r"$\prod_{k=1}^{n-1}(1-\zeta_{k})$.",
        ("2.5", "problem", "2.19"): r"Find all $k\in\mathbb{R}$ such that the "
                        r"number $2$ lies strictly between the two roots of "
                        r"$x^{2}+(k-3)x+k=0$.",
        ("2.5", "problem", "2.20"): r"Solve $|x-1|+|x-3|\leq 4$ for "
                        r"$x\in\mathbb{R}$.",
        ("2.5", "problem", "2.21"): r"In an $N$-point FFT, "
                        r"$W_{N}=e^{-i2\pi/N}$. Prove that "
                        r"$\sum_{n=0}^{N-1}W_{N}^{kn}=N$ if $k\equiv 0\pmod N$ "
                        r"and $0$ otherwise.",
        ("2.5", "problem", "2.22"): r"An AR(2) process "
                        r"$X_{t}=\phi_{1}X_{t-1}+\phi_{2}X_{t-2}+\epsilon_{t}$ "
                        r"is stationary iff all roots of "
                        r"$\Phi(z)=1-\phi_{1}z-\phi_{2}z^{2}=0$ satisfy "
                        r"$|z|>1$. Check stationarity for "
                        r"$\phi_{1}=0.5$, $\phi_{2}=0.24$.",
        ("2.5", "problem", "2.23"): r"Polyak heavy-ball momentum on a "
                        r"curvature-$\lambda$ mode obeys "
                        r"$x_{t+1}-(1+\beta-\eta\lambda)x_{t}+\beta x_{t-1}=0$. "
                        r"When the characteristic roots are complex "
                        r"conjugates, find their exact modulus $|r|$.",
        ("2.5", "problem", "2.24"): r"In LLM Transformers, RoPE maps a 2D "
                        r"query slice $(q_{1},q_{2})$ to "
                        r"$q_{\mathrm{rot}}=(q_{1}+iq_{2})e^{im\theta}$. Prove "
                        r"that RoPE preserves Euclidean norm and that the "
                        r"inner product "
                        r"$\operatorname{Re}(q_{\mathrm{rot},m}"
                        r"\bar{k}_{\mathrm{rot},n})$ depends only on relative "
                        r"position $m-n$.",
        ("2.5", "problem", "2.25"): r"A portfolio of 2 assets has covariance "
                        r"matrix $\Sigma=\begin{pmatrix}\sigma_{1}^{2}&"
                        r"\rho\sigma_{1}\sigma_{2}\\ \rho\sigma_{1}\sigma_{2}&"
                        r"\sigma_{2}^{2}\end{pmatrix}$. Using quadratic "
                        r"inequalities on $w_{1}^{2}\sigma_{1}^{2}+"
                        r"2\rho\sigma_{1}\sigma_{2}w_{1}w_{2}+"
                        r"w_{2}^{2}\sigma_{2}^{2}\geq 0$, find the valid range "
                        r"of $\rho$.",
        ("2.5", "problem", "2.26"): r"In the Heston model, "
                        r"$d=\sqrt{(\kappa-i\rho\sigma u)^{2}+"
                        r"\sigma^{2}(iu+u^{2})}$. Evaluate $d$ at $u=-i$ when "
                        r"$\rho=0$, $\kappa=2$, $\sigma=1$.",
        ("2.5", "problem", "2.27"): r"The perpetual American put value solves "
                        r"$\frac{1}{2}\sigma^{2}S^{2}V''+rSV'-rV=0$ with trial "
                        r"power solution $V(S)=S^{\gamma}$. Find the negative "
                        r"root $\gamma_{-}$ of the fundamental quadratic "
                        r"$\frac{1}{2}\sigma^{2}\gamma(\gamma-1)+r\gamma-r=0$.",
        ("2.5", "problem", "2.28"): r"Huber loss is quadratic "
                        r"$\frac{1}{2}r^{2}$ when $|r|\leq\delta$ and linear "
                        r"$\delta(|r|-\frac{1}{2}\delta)$ when $|r|>\delta$. "
                        r"For residual $r(w)=2w^{2}-5w+1$ and $\delta=2$, find "
                        r"all $w$ in the quadratic regime.",
        ("2.5", "problem", "2.29"): r"The Brenner-Subrahmanyam ATM call price "
                        r"with bid-ask cost is "
                        r"$C(\sigma)=0.4S\sqrt{T}\,\sigma-"
                        r"0.02S\sqrt{T}\,\sigma^{2}$. For $S=100$, $T=1$, solve "
                        r"$C(\sigma)\geq 7.5$ for $\sigma\in(0,5)$.",
        ("2.5", "problem", "2.30"): r"Prove that all roots of "
                        r"$\lambda^{2}+a_{1}\lambda+a_{2}=0$ satisfy "
                        r"$|\lambda|<1$ iff $a_{2}<1$ and "
                        r"$|a_{1}|<1+a_{2}$.",
        ("3.4", "problem", "3.1"): r"If $\binom{n}{8}=\binom{n}{6}$, find $\binom{n}{2}$.",
        ("3.4", "problem", "3.2"): r"In how many ways can 5 boys and 3 girls be seated "
                        r"in a row so that no two girls sit together?",
        ("3.4", "problem", "3.3"): r"How many distinct permutations of the letters "
                        r"of MISSISSIPPI have the four I's not coming together?",
        ("3.4", "problem", "3.4"): r"A committee of 5 is to be formed from 6 men "
                        r"and 4 women. In how many ways can this be done if at "
                        r"least 2 women must be included?",
        ("3.4", "problem", "3.5"): r"Find the middle term in the expansion of "
                        r"$\left(x-\frac{1}{2x}\right)^{10}$.",
        ("3.4", "problem", "3.6"): r"If three consecutive coefficients in "
                        r"$(1+x)^{n}$ are in the ratio $1:7:42$, find $n$.",
        ("3.4", "problem", "3.7"): r"If the $m$-th term of an AP is $n$ and the "
                        r"$n$-th term is $m$ ($m\neq n$), find the $(mn)$-th "
                        r"term and the sum of the first $mn$ terms.",
        ("3.4", "problem", "3.8"): r"Evaluate $S_{n}=7+77+777+\cdots$ to $n$ terms.",
        ("3.4", "problem", "3.9"): r"Find the sum of the first 10 terms of "
                        r"$\sum_{k=1}^{10}\frac{1}{k(k+1)(k+3)}$.",
        ("3.4", "problem", "3.10"): r"Between 1 and 31, $m$ arithmetic means are "
                        r"inserted so that the ratio of the 7-th and "
                        r"$(m-1)$-th means is $5:9$. Find $m$.",
        ("3.4", "problem", "3.11"): r"Find the exact number of trailing zeros at "
                        r"the end of $100!$ in base 10.",
        ("3.4", "problem", "3.12"): r"A convex polygon has 44 diagonals. Find the "
                        r"number of its sides $n$ and the number of triangles "
                        r"formed by its vertices that share no side with the "
                        r"polygon.",
        ("3.4", "problem", "3.13"): r"Find the number of integer solutions to "
                        r"$x_{1}+x_{2}+x_{3}+x_{4}=20$ with $x_{1}\geq 1$, "
                        r"$x_{2}\geq 2$, $x_{3}\geq 3$, $x_{4}\geq 0$.",
        ("3.4", "problem", "3.14"): r"In how many ways can 9 distinct books be "
                        r"divided equally among (a) 3 named students, and "
                        r"(b) 3 unlabeled parcels of 3 books each?",
        ("3.4", "problem", "3.15"): r"Find the coefficient of $x^{3}y^{2}z^{4}$ in "
                        r"the expansion of $(2x-y+3z)^{9}$.",
        ("3.4", "problem", "3.16"): r"Evaluate $\sum_{r=0}^{n}r\binom{n}{r}^{2}$ "
                        r"in closed form.",
        ("3.4", "problem", "3.17"): r"Find the remainder when $7^{103}$ is divided by 25.",
        ("3.4", "problem", "3.18"): r"Evaluate the infinite sum "
                        r"$S=1+\frac{3}{2}+\frac{5}{4}+\frac{7}{8}+\frac{9}{16}+\cdots$.",
        ("3.4", "problem", "3.19"): r"Evaluate $S_{\infty}=\sum_{n=1}^{\infty}"
                        r"\arctan\left(\frac{1}{1+n+n^{2}}\right)$.",
        ("3.4", "problem", "3.20"): r"Find the minimum value of "
                        r"$\sec^{2}\theta+4\csc^{2}\theta$ for "
                        r"$\theta\in(0,\pi/2)$.",
        ("3.4", "problem", "3.21"): r"A degree-$d$ inhomogeneous polynomial "
                        r"kernel $K(x,z)=(x^{T}z+1)^{d}$ on $x\in\mathbb{R}^{p}$ "
                        r"maps implicitly to all monomials of degree $\leq d$. "
                        r"Find the exact dimension of this feature space for "
                        r"$p=10$, $d=4$.",
        ("3.4", "problem", "3.22"): r"Show that $\frac{1}{n}\log_{2}\binom{n}{pn}"
                        r"\to H_{2}(p)=-p\log_{2}p-(1-p)\log_{2}(1-p)$ as "
                        r"$n\to\infty$ using $\ln(m!)\approx m\ln m-m$.",
        ("3.4", "problem", "3.23"): r"A stock pays a dividend of $D_{1}=4$ dollars one "
                        r"year from now, growing at $g=5\%$ per year forever, "
                        r"discounted at $r=9\%$ per year. Find the fair price "
                        r"$P_{0}=\sum_{t=1}^{\infty}\frac{D_{1}(1+g)^{t-1}}{(1+r)^{t}}$.",
        ("3.4", "problem", "3.24"): r"A consol pays $C$ dollars at $t=1,2,3,\ldots$ "
                        r"discounted at yield $y>0$. Prove via AGP that its "
                        r"Macaulay duration equals $\frac{1+y}{y}$.",
        ("3.4", "problem", "3.25"): r"In an $N$-period Cox-Ross-Rubinstein binomial "
                        r"option tree, compare the total number of paths "
                        r"($2^{N}$) with the number of distinct asset prices at "
                        r"step $N$ ($N+1$) for $N=30$.",
        ("3.4", "problem", "3.26"): r"Exponential moving average "
                        r"$m_{t}=(1-\beta)\sum_{k=0}^{\infty}\beta^{k}g_{t-k}$ "
                        r"has weights summing to 1. Compute the expected lag "
                        r"$E[k]=(1-\beta)\sum_{k=0}^{\infty}k\beta^{k}$ for "
                        r"$\beta=0.99$.",
        ("3.4", "problem", "3.27"): r"In a Random Forest, $n$ samples are drawn "
                        r"with replacement from $n$ data points. Find the "
                        r"probability that a specific point is never selected "
                        r"(Out-of-Bag) as $n\to\infty$.",
        ("3.4", "problem", "3.28"): r"In SHAP feature attribution with $M$ "
                        r"features, verify that the sum of Shapley weights "
                        r"$\sum_{s=0}^{M-1}\frac{1}{M}\binom{M-1}{s}^{-1}$ "
                        r"equals 1.",
        ("3.4", "problem", "3.29"): r"For a hypothesis class of VC dimension "
                        r"$d=3$ on $N=10$ points, compute Sauer's upper bound "
                        r"$\sum_{k=0}^{d}\binom{N}{k}$ on the number of dichotomies.",
        ("3.4", "problem", "3.30"): r"A portfolio contains $N=50$ stocks. How "
                        r"many distinct variances and pairwise covariances must "
                        r"be estimated in the symmetric $50\times 50$ "
                        r"covariance matrix $\Sigma$?",
        ("4.3", "problem", "4.1"): r"How many $3\times 3$ matrices can be formed whose entries "
                        r"are chosen from $\{0,1\}$, and how many of them are symmetric?",
        ("4.3", "problem", "4.2"): r"If $A=\begin{pmatrix}3&1\\-1&2\end{pmatrix}$, verify "
                        r"$A^{2}-5A+7I_{2}=0$ and find $A^{4}$.",
        ("4.3", "problem", "4.3"): r"If $A$ and $B$ are symmetric matrices of the same "
                        r"order, prove that $AB-BA$ is skew-symmetric and $AB+BA$ "
                        r"is symmetric.",
        ("4.3", "problem", "4.4"): r"If $A=\begin{pmatrix}1&a\\0&1\end{pmatrix}$, find "
                        r"$A^{n}$ for $n\in\mathbb{N}$.",
        ("4.3", "problem", "4.5"): r"Prove that if $A$ is a skew-symmetric matrix of odd "
                        r"order $n$ (e.g., $n=3$), then $\det(A)=0$.",
        ("4.3", "problem", "4.6"): r"Find $k$ so that the points $(k,2-2k)$, "
                        r"$(1-k,2k)$, $(-4-k,6-2k)$ are collinear.",
        ("4.3", "problem", "4.7"): r"Find the inverse of "
                        r"$A=\begin{pmatrix}2&5\\1&3\end{pmatrix}$ and solve "
                        r"$2x+5y=1$, $x+3y=2$.",
        ("4.3", "problem", "4.8"): r"If $A$ is a $3\times 3$ matrix with $|A|=-3$, find "
                        r"$|-2A^{2}|$.",
        ("4.3", "problem", "4.9"): r"For what value of $k$ does the homogeneous system "
                        r"$x+ky+3z=0$, $3x+ky-2z=0$, $2x+4y-3z=0$ have non-zero "
                        r"solutions?",
        ("4.3", "problem", "4.10"): r"Evaluate $AB$ for "
                        r"$A=\begin{pmatrix}1&1&-1\\1&2&1\\2&1&-3\end{pmatrix}$ and "
                        r"$B=\begin{pmatrix}4&2&2\\-5&0&5\\1&-2&3\end{pmatrix}$, and "
                        r"hence find $A^{-1}$.",
        ("4.3", "problem", "4.11"): r"Evaluate "
                        r"$\Delta=\begin{vmatrix}a&b&c\\b&c&a\\c&a&b\end{vmatrix}$ "
                        r"and show that $\Delta\leq 0$ for all $a,b,c>0$.",
        ("4.3", "problem", "4.12"): r"Evaluate "
                        r"$\Delta=\begin{vmatrix}1&\omega^{n}&\omega^{2n}\\"
                        r"\omega^{2n}&1&\omega^{n}\\1&\omega^{n}&\omega^{2n}"
                        r"\end{vmatrix}$ when $n$ is not a multiple of $3$.",
        ("4.3", "problem", "4.13"): r"If $f(x)=\begin{vmatrix}x&1&1\\1&x&1\\1&1&x"
                        r"\end{vmatrix}$, find $f'(x)$ and $f'(1)$.",
        ("4.3", "problem", "4.14"): r"If $D_{k}=\begin{vmatrix}k&1&5\\k^{2}&2n+1&5\\"
                        r"k^{3}&3n^{2}&5\end{vmatrix}$, evaluate "
                        r"$\sum_{k=1}^{n}D_{k}$ for $n=10$.",
        ("4.3", "problem", "4.15"): r"If $P$ is an idempotent matrix ($P^{2}=P$) and "
                        r"$I+P$ is invertible, find $(I+P)^{-1}$ as a linear "
                        r"combination of $I$ and $P$.",
        ("4.3", "problem", "4.16"): r"If $N$ is a $3\times 3$ nilpotent matrix "
                        r"($N^{3}=0$), prove that $I-N$ is invertible and find "
                        r"$(I-N)^{-1}$ and $\det(I-N)$.",
        ("4.3", "problem", "4.17"): r"Prove that for any real matrix "
                        r"$A\in\mathbb{R}^{m\times n}$, "
                        r"$\operatorname{Tr}(A^{T}A)=0\iff A=0$.",
        ("4.3", "problem", "4.18"): r"If "
                        r"$Q=\frac{1}{3}\begin{pmatrix}1&2&2\\2&1&-2\\2&-2&1"
                        r"\end{pmatrix}$, verify that $Q$ is orthogonal and "
                        r"find $Q^{-1}$.",
        ("4.3", "problem", "4.19"): r"If $A$ and $B$ are $3\times 3$ matrices with "
                        r"$|A|=3$ and $|B|=5$, evaluate "
                        r"$|\operatorname{adj}(AB)|$ and "
                        r"$\det(\operatorname{adj}(A)\operatorname{adj}(B))$.",
        ("4.3", "problem", "4.20"): r"Solve the system in reciprocals "
                        r"$u=1/x$, $v=1/y$, $w=1/z$: $8u+2v+5w=4$, "
                        r"$u-v+w=1$, $u+v-w=2$ (equivalently solve for "
                        r"$x,y,z$ from the original system).",
        ("4.3", "problem", "4.21"): r"In ordinary least squares regression, the hat "
                        r"matrix is $H=X(X^{T}X)^{-1}X^{T}$ where "
                        r"$X\in\mathbb{R}^{n\times p}$ has full column rank $p$. "
                        r"Prove that $H$ and $I_{n}-H$ are symmetric and "
                        r"idempotent, and find $\operatorname{Tr}(H)$.",
        ("4.3", "problem", "4.22"): r"Verify that "
                        r"$(A+uv^{T})^{-1}=A^{-1}-"
                        r"\frac{A^{-1}uv^{T}A^{-1}}{1+v^{T}A^{-1}u}$ by direct "
                        r"multiplication with $A+uv^{T}$.",
        ("4.3", "problem", "4.23"): r"Explain using determinants/eigenvalues why "
                        r"$X^{T}X+\lambda I_{p}$ is strictly invertible for every "
                        r"$\lambda>0$ even when $p>n$ ($X^{T}X$ is singular).",
        ("4.3", "problem", "4.24"): r"Test whether "
                        r"$\Sigma=\begin{pmatrix}2&-1&0\\-1&2&-1\\0&-1&2"
                        r"\end{pmatrix}$ is strictly positive definite by "
                        r"computing its leading principal minors.",
        ("4.3", "problem", "4.25"): r"In a 2-state market ($t=1$), a risk-free bond "
                        r"pays $(1.05,1.05)^{T}$ at price 1 and a stock pays "
                        r"$(1.26,0.84)^{T}$ at price 1. Find the Arrow-Debreu "
                        r"state-price vector $\psi=(\psi_{u},\psi_{d})^{T}$ by "
                        r"inverting the payoff matrix $D$.",
        ("4.3", "problem", "4.26"): r"A Transformer projection matrix "
                        r"$W\in\mathbb{R}^{4096\times 4096}$ is adapted via a "
                        r"rank-$r$ update $\Delta W=BA$ ($B\in"
                        r"\mathbb{R}^{4096\times r}$, $A\in"
                        r"\mathbb{R}^{r\times 4096}$) with $r=8$. Compute the "
                        r"exact parameter reduction factor.",
        ("4.3", "problem", "4.27"): r"The differential entropy of "
                        r"$\mathcal{N}(\mu,\Sigma)$ in $\mathbb{R}^{d}$ is "
                        r"$\frac{1}{2}\ln(2\pi e)^{d}\det(\Sigma)$. If all asset "
                        r"volatilities are doubled ($\tilde\Sigma=4\Sigma$), how "
                        r"much does the entropy increase?",
        ("4.3", "problem", "4.28"): r"A 2-state Markov chain has transition matrix "
                        r"$P=\begin{pmatrix}0.7&0.3\\0.2&0.8\end{pmatrix}$. Show "
                        r"$\det(P-I)=0$ and find the stationary distribution "
                        r"$\pi^{T}P=\pi^{T}$ with $\pi_{1}+\pi_{2}=1$.",
        ("4.3", "problem", "4.29"): r"An affine coupling layer in a normalizing flow "
                        r"maps $(x_{1},x_{2})\mapsto(y_{1},y_{2})=(x_{1},"
                        r"e^{s(x_{1})}x_{2}+t(x_{1}))$. Write its $2\times 2$ "
                        r"Jacobian matrix $J$ and compute $\det(J)$.",
        ("4.3", "problem", "4.30"): r"An economy has consumption matrix "
                        r"$C=\begin{pmatrix}0.2&0.4\\0.1&0.2\end{pmatrix}$ and "
                        r"external demand $d=(100,80)^{T}$. Solve "
                        r"$(I-C)x=d$ for gross output $x$.",
        ("5.5", "problem", "5.1"): r"Find the equation of a line passing through $(2,2)$ whose "
                        r"$x$- and $y$-intercepts sum to $9$.",
        ("5.5", "problem", "5.2"): r"Find the perpendicular distance between $3x-4y+9=0$ and "
                        r"$6x-8y-15=0$.",
        ("5.5", "problem", "5.3"): r"Find the acute angle between $y-3x-5=0$ and $3y-x+6=0$.",
        ("5.5", "problem", "5.4"): r"Find the line passing through the intersection of "
                        r"$x+2y-3=0$ and $2x-y+4=0$ that is parallel to $y=3x$.",
        ("5.5", "problem", "5.5"): r"Find the circle whose diameter has endpoints $(1,2)$ and "
                        r"$(5,6)$.",
        ("5.5", "problem", "5.6"): r"For what values of $c$ is $y=mx+c$ tangent to "
                        r"$x^{2}+y^{2}=r^{2}$?",
        ("5.5", "problem", "5.7"): r"Find the focus, directrix, and latus rectum of "
                        r"$x^{2}=-16y$.",
        ("5.5", "problem", "5.8"): r"Find the vertex and focus of "
                        r"$y^{2}-4y-8x+12=0$.",
        ("5.5", "problem", "5.9"): r"Find the ellipse with foci $(\pm 3,0)$ and "
                        r"semi-major axis $a=4$.",
        ("5.5", "problem", "5.10"): r"What is the eccentricity of a rectangular hyperbola "
                        r"$x^{2}-y^{2}=a^{2}$?",
        ("5.5", "problem", "5.11"): r"A line through $P(1,2)$ makes angle $60^{\circ}$ with the "
                        r"positive $x$-axis and meets $x+y=6$ at $Q$. Find the exact "
                        r"length $PQ$.",
        ("5.5", "problem", "5.12"): r"A variable line of length $L$ slides with its "
                        r"endpoints $A(a,0)$ and $B(0,b)$ on the coordinate axes. "
                        r"Find the locus of the centroid $G(h,k)$ of $\triangle OAB$.",
        ("5.5", "problem", "5.13"): r"For what value of $\lambda$ does "
                        r"$12x^{2}-10xy+2y^{2}+11x-5y+\lambda=0$ represent a pair of "
                        r"straight lines, and what is the angle between them?",
        ("5.5", "problem", "5.14"): r"Find the length of the chord intercepted by the circle "
                        r"$x^{2}+y^{2}=25$ on the line $3x-4y+15=0$.",
        ("5.5", "problem", "5.15"): r"Find the equation and length of the common chord of "
                        r"the circles $x^{2}+y^{2}-4x=0$ and $x^{2}+y^{2}-4y=0$.",
        ("5.5", "problem", "5.16"): r"If $PSQ$ is a focal chord of the parabola "
                        r"$y^{2}=4ax$ with focus $S$, prove that "
                        r"$\frac{1}{SP}+\frac{1}{SQ}=\frac{1}{a}$.",
        ("5.5", "problem", "5.17"): r"Find the minimum distance between the parabola "
                        r"$y^{2}=4x$ and the line $x-y+4=0$.",
        ("5.5", "problem", "5.18"): r"Find the locus of the point of intersection of "
                        r"perpendicular tangents to the ellipse "
                        r"$\frac{x^{2}}{25}+\frac{y^{2}}{9}=1$.",
        ("5.5", "problem", "5.19"): r"If $e_{1}$ and $e_{2}$ are the eccentricities of a "
                        r"hyperbola and its conjugate hyperbola, prove that "
                        r"$\frac{1}{e_{1}^{2}}+\frac{1}{e_{2}^{2}}=1$.",
        ("5.5", "problem", "5.20"): r"If the normal at $P(ct_{1},c/t_{1})$ to the "
                        r"rectangular hyperbola $xy=c^{2}$ meets the curve again at "
                        r"$Q(ct_{2},c/t_{2})$, prove that $t_{1}^{3}t_{2}=-1$.",
        ("5.5", "problem", "5.21"): r"In a linear Support Vector Machine in "
                        r"$\mathbb{R}^{2}$, the positive and negative support lines are "
                        r"$3x_{1}+4x_{2}-7=+1$ and $3x_{1}+4x_{2}-7=-1$. Find the "
                        r"geometric margin width $\gamma$.",
        ("5.5", "problem", "5.22"): r"A 2D Gaussian has inverse covariance "
                        r"$\Sigma^{-1}=\begin{pmatrix}5&-3\\-3&5\end{pmatrix}$. "
                        r"Find the semi-axes of the ellipse $x^{T}\Sigma^{-1}x=1$ by "
                        r"rotating by $45^{\circ}$.",
        ("5.5", "problem", "5.23"): r"In portfolio theory without a risk-free asset, "
                        r"portfolio variance $\sigma_{p}^{2}(\mu_{p})=A\mu_{p}^{2}-"
                        r"2B\mu_{p}+C$ ($AC-B^{2}>0$). Show that in "
                        r"($\sigma_{p},\mu_{p}$) space, the frontier is a hyperbola "
                        r"and find its minimum-variance vertex.",
        ("5.5", "problem", "5.24"): r"A quadratic loss contour is the circle "
                        r"$(w_{1}-3)^{2}+(w_{2}-1)^{2}=r^{2}$. Find $r^{2}$ at which it "
                        r"touches the L1 constraint diamond $|w_{1}|+|w_{2}|\leq 1$, "
                        r"and verify that tangency occurs at the sparse corner "
                        r"$(1,0)$.",
        ("5.5", "problem", "5.25"): r"A Uniswap liquidity pool obeys the rectangular "
                        r"hyperbola $xy=k$ with $x_{0}=100$ ETH and "
                        r"$y_{0}=250{,}000$ USDC ($k=2.5\times 10^{7}$). Compare the "
                        r"marginal spot price $-dy/dx$ at $x_{0}$ with the average "
                        r"execution price when buying $\Delta x=10$ ETH ($x_{1}=90$).",
        ("5.5", "problem", "5.26"): r"An adversarial attack perturbs input "
                        r"$x_{0}=(1,1)^{T}$ to the closest point on the classifier "
                        r"hyperplane $4x_{1}-3x_{2}+9=0$. Find the adversarial example "
                        r"$x^{*}$ and the $L_{2}$ perturbation norm.",
        ("5.5", "problem", "5.27"): r"Gatheral's raw SVI parameterizes total implied "
                        r"variance as $w(k)=a+b\rho(k-m)+\sqrt{(k-m)^{2}+\sigma^{2}}$. "
                        r"For $\rho=0$, show that the $(w,k)$ smile is a hyperbola "
                        r"and find its asymptotic slopes as $k\to\pm\infty$.",
        ("5.5", "problem", "5.28"): r"In 2D k-Means, two centroids are at "
                        r"$\mu_{1}=(1,2)$ and $\mu_{2}=(5,6)$. Find the equation of "
                        r"the Voronoi decision boundary separating their clusters.",
        ("5.5", "problem", "5.29"): r"Two Gaussian classes share covariances "
                        r"$\Sigma_{1}=I_{2}$ and $\Sigma_{2}=4I_{2}$ with means "
                        r"$\mu_{1}=(0,0)$ and $\mu_{2}=(3,0)$. What conic section is "
                        r"the Bayes optimal decision boundary "
                        r"$\|x\|_{2}^{2}-\frac{1}{4}\|x-\mu_{2}\|_{2}^{2}=\mathrm{const}$?",
        ("5.5", "problem", "5.30"): r"Express $P(2,3)$ in barycentric coordinates "
                        r"$(\lambda_{1},\lambda_{2},\lambda_{3})$ "
                        r"($\sum\lambda_{i}=1$) with respect to triangle "
                        r"$A(0,0)$, $B(6,0)$, $C(0,9)$.",
        ("6.5", "problem", "6.1"): r"Evaluate $\lim_{x\to 0} \frac{\sqrt{1+3x}-\sqrt{1-3x}}{x}$.",
        ("6.5", "problem", "6.2"): r"Find $(a,b)$ so that $f(x)=x^{2}+3x+a$ for $x\leq 1$ and "
                        r"$f(x)=bx+2$ for $x>1$ is differentiable at $x=1$.",
        ("6.5", "problem", "6.3"): r"Differentiate $u=x^{\sin x}$ for $x>0$.",
        ("6.5", "problem", "6.4"): r"If $y=\arcsin x$, prove $(1-x^{2})y''-xy'=0$.",
        ("6.5", "problem", "6.5"): r"If $y=x^{x^{\cdots^{\infty}}}=x^{y}$, prove "
                        r"$x\frac{dy}{dx}=\frac{y^{2}}{1-y\ln x}$.",
        ("6.5", "problem", "6.6"): r"Differentiate $u=\arctan\left(\frac{2x}{1-x^{2}}\right)$ "
                        r"with respect to $v=\arcsin\left(\frac{2x}{1+x^{2}}\right)$ for "
                        r"$|x|<1$.",
        ("6.5", "problem", "6.7"): r"Find $c\in(1,4)$ satisfying MVT for "
                        r"$f(x)=x^{2}-4x-3$ on $[1,4]$.",
        ("6.5", "problem", "6.8"): r"A 5 m ladder leans against a wall. Its bottom is "
                        r"pulled away at 2 m/s. How fast is its top sliding down when "
                        r"the bottom is 4 m from the wall?",
        ("6.5", "problem", "6.9"): r"Find the normal to the curve $y=x^{3}-3x$ at $(2,2)$.",
        ("6.5", "problem", "6.10"): r"Show that $f(x)=\frac{\ln x}{x}$ achieves its global "
                        r"maximum at $x=e$, and determine which is larger: $e^{\pi}$ or "
                        r"$\pi^{e}$.",
        ("6.5", "problem", "6.11"): r"Find the maximum area of a rectangle inscribed in "
                        r"the ellipse $\frac{x^{2}}{a^{2}}+\frac{y^{2}}{b^{2}}=1$.",
        ("6.5", "problem", "6.12"): r"Find the absolute maximum and minimum of "
                        r"$f(x)=2x^{3}-15x^{2}+36x+1$ on $[1,5]$.",
        ("6.5", "problem", "6.13"): r"Evaluate $\lim_{x\to 0} "
                        r"\frac{e^{\tan x}-e^{x}}{\tan x-x}$.",
        ("6.5", "problem", "6.14"): r"Evaluate $\lim_{x\to 0}\left("
                        r"\frac{a+b^{x}+cx^{1/x}}{3}\right)^{1/x}$ for $a,b,c>0$.",
        ("6.5", "problem", "6.15"): r"Find all points where "
                        r"$f(x)=|x-1|+|x^{2}-3x+2|$ is non-differentiable.",
        ("6.5", "problem", "6.16"): r"Let $f(x)=x^{3}+x+1$ and $g=f^{-1}$. Find $g'(3)$ "
                        r"and $g''(3)$.",
        ("6.5", "problem", "6.17"): r"If $2a+3b+6c=0$, prove that the quadratic "
                        r"$ax^{2}+bx+c=0$ has at least one real root strictly in $(0,1)$.",
        ("6.5", "problem", "6.18"): r"Find the condition for the curves "
                        r"$a_{1}x^{2}+b_{1}y^{2}=1$ and $a_{2}x^{2}+b_{2}y^{2}=1$ to "
                        r"intersect orthogonally.",
        ("6.5", "problem", "6.19"): r"Sand is poured at $12\ \mathrm{cm}^{3}/\mathrm{s}$ "
                        r"to form a cone whose height is always one-sixth of the "
                        r"radius of its base ($h=r/6$). How fast is the height $h$ "
                        r"increasing when $h=4$ cm?",
        ("6.5", "problem", "6.20"): r"A wire of length $L$ is cut into two pieces, one "
                        r"bent into a square and the other into a circle. Find the "
                        r"ratio of the circle radius $r$ to the square side $s$ that "
                        r"minimizes the combined area.",
        ("6.5", "problem", "6.21"): r"Compute the first derivative of the Swish "
                        r"activation $\operatorname{Swish}(x)=x\sigma(x)$ where "
                        r"$\sigma(x)=\frac{1}{1+e^{-x}}$ satisfies "
                        r"$\sigma'(x)=\sigma(x)(1-\sigma(x))$.",
        ("6.5", "problem", "6.22"): r"In feature engineering, the Box-Cox transform is "
                        r"$y^{(\lambda)}=\frac{y^{\lambda}-1}{\lambda}$ for $y>0$. "
                        r"Prove that $\lim_{\lambda\to 0}y^{(\lambda)}=\ln y$.",
        ("6.5", "problem", "6.23"): r"Prove that investing 1 dollar at nominal annual "
                        r"rate $r$ compounded $m$ times per year over $T$ years "
                        r"converges to $e^{rT}$ as $m\to\infty$.",
        ("6.5", "problem", "6.24"): r"For a portfolio with value $V(S,t)$, the Taylor "
                        r"expansion for a small move $\Delta S$ over $dt=0$ is "
                        r"$\Delta V\approx \Delta(\Delta S)+\frac{1}{2}\Gamma(\Delta S)^{2}$. "
                        r"If $\Delta=0$ (delta-neutral) and $\Gamma=+0.08$, find "
                        r"$\Delta V$ when $\Delta S=\pm 5$.",
        ("6.5", "problem", "6.25"): r"A bond with price $P=100$, modified duration "
                        r"$D_{\mathrm{mod}}=-\frac{1}{P}\frac{dP}{dy}=7$, and "
                        r"convexity $C=\frac{1}{P}\frac{d^{2}P}{dy^{2}}=60$ experiences "
                        r"a yield jump $\Delta y=+0.02$ (+200 bps). Estimate "
                        r"$\Delta P$.",
        ("6.5", "problem", "6.26"): r"For $L(z)=-y\ln\sigma(z)-(1-y)\ln(1-\sigma(z))$ "
                        r"with $\sigma(z)=\frac{1}{1+e^{-z}}$, prove that "
                        r"$\frac{dL}{dz}=\sigma(z)-y$.",
        ("6.5", "problem", "6.27"): r"To invert Black-Scholes price "
                        r"$C_{BS}(\sigma)=C_{\mathrm{mkt}}$, write the Newton-Raphson "
                        r"update for $\sigma_{k+1}$ in terms of option Vega "
                        r"$V(\sigma)=\partial C_{BS}/\partial\sigma$.",
        ("6.5", "problem", "6.28"): r"Compute the Left-Hand Derivative and Right-Hand "
                        r"Derivative of $\lambda|w|$ at $w=0$, and find the "
                        r"subdifferential set $\partial(\lambda|0|)$.",
        ("6.5", "problem", "6.29"): r"Maximize expected log-wealth growth "
                        r"$g(f)=p\ln(1+f)+(1-p)\ln(1-f)$ for $p\in(1/2,1)$ over "
                        r"$f\in[0,1)$.",
        ("6.5", "problem", "6.30"): r"If $f:\mathbb{R}\to\mathbb{R}$ satisfies "
                        r"$0<m\leq f''(x)\leq L$, show via Taylor's Theorem that "
                        r"$f(x-\eta f'(x))\leq f(x)-\eta(1-\frac{L\eta}{2})"
                        r"[f'(x)]^{2}$ and find the step size $\eta^{*}$ "
                        r"maximizing the guaranteed decrease.",
        ("7.3", "problem", "7.1"): r"Evaluate $\int \frac{dx}{x^{2}-6x+13}$.",
        ("7.3", "problem", "7.2"): r"Evaluate $\int \frac{3x-2}{(x+1)^{2}(x+3)}dx$.",
        ("7.3", "problem", "7.3"): r"Evaluate $\int_{a}^{b}\ln x\,dx$ and $\int_{0}^{1}\arctan x\,dx$.",
        ("7.3", "problem", "7.4"): r"Evaluate $\int \frac{xe^{x}}{(1+x)^{2}}dx$.",
        ("7.3", "problem", "7.5"): r"Evaluate $\int_{-1}^{2}|x^{3}-x|dx$.",
        ("7.3", "problem", "7.6"): r"Evaluate $I=\int_{0}^{\pi}\frac{x\sin x}{1+\cos^{2}x}dx$.",
        ("7.3", "problem", "7.7"): r"Find the area bounded by $y^{2}=4x$ and $x^{2}=4y$.",
        ("7.3", "problem", "7.8"): r"Find the smaller area cut from $x^{2}+y^{2}=4$ by the line "
                        r"$x+y=2$.",
        ("7.3", "problem", "7.9"): r"Solve $\frac{dy}{dx}=\frac{1+y^{2}}{1+x^{2}}$ with "
                        r"$y(0)=1$.",
        ("7.3", "problem", "7.10"): r"Solve $(1+y^{2})dx=(\arctan y-x)dy$.",
        ("7.3", "problem", "7.11"): r"A body cools according to $\frac{dT}{dt}=-k(T-20)$. "
                        r"If $T(0)=100$ and $T(10)=60$, find $T(20)$.",
        ("7.3", "problem", "7.12"): r"Solve $y''+4y'+3y=0$ with $y(0)=2$, $y'(0)=-4$.",
        ("7.3", "problem", "7.13"): r"Evaluate $\int_{0}^{\pi/2}\frac{dx}{2+\cos x}$.",
        ("7.3", "problem", "7.14"): r"Evaluate $\int_{0}^{\pi/2}\frac{dx}{9\cos^{2}x+4\sin^{2}x}$.",
        ("7.3", "problem", "7.15"): r"Evaluate $I=\int_{-\pi/2}^{\pi/2}\frac{\cos x}{1+e^{x}}dx$.",
        ("7.3", "problem", "7.16"): r"Evaluate $\int_{0}^{100\pi}|\sin x|dx$.",
        ("7.3", "problem", "7.17"): r"Evaluate $\lim_{x\to 0}\frac{\sqrt{\int_{0}^{x^{2}}\sin t\,dt}}{x^{3}}$.",
        ("7.3", "problem", "7.18"): r"Evaluate $\int_{0}^{\pi/2}\sin^{5}x\,dx$ and "
                        r"$\int_{0}^{\pi/2}\sin^{4}x\cos^{2}x\,dx$ using Wallis' formula.",
        ("7.3", "problem", "7.19"): r"Find the order and degree of $1+\left(\frac{dy}{dx}\right)^{3/2}=R\frac{d^{2}y}{dx^{2}}$.",
        ("7.3", "problem", "7.20"): r"Solve $(2xy+y^{2})dx+(x^{2}+2xy)dy=0$.",
        ("7.3", "problem", "7.21"): r"For $Z\sim\mathcal{N}(0,1)$, use integration by parts with "
                        r"$u=z^{n-1}$ and $dv=ze^{-z^{2}/2}dz$ to prove "
                        r"$E[Z^{n}]=(n-1)E[Z^{n-2}]$ and compute $E[Z^{4}]$.",
        ("7.3", "problem", "7.22"): r"Prove via integration by parts that "
                        r"$\Gamma(\alpha+1)=\alpha\Gamma(\alpha)$ where "
                        r"$\Gamma(\alpha)=\int_{0}^{\infty}x^{\alpha-1}e^{-x}dx$, and "
                        r"evaluate $\Gamma(1/2)$.",
        ("7.3", "problem", "7.23"): r"Evaluate $I(a)=\int_{0}^{1}\frac{x^{a}-1}{\ln x}dx$ "
                        r"for $a>-1$ by differentiating with respect to $a$.",
        ("7.3", "problem", "7.24"): r"Prove that for $Z\sim\mathcal{N}(0,1)$ with PDF "
                        r"$\phi(z)=\frac{1}{\sqrt{2\pi}}e^{-z^{2}/2}$, the conditional tail "
                        r"expectation is $E[Z\mid Z>z_{\alpha}]=\frac{\phi(z_{\alpha})}{1-\alpha}$.",
        ("7.3", "problem", "7.25"): r"Solve $\frac{dP}{dt}=kP(1-P)$ with $P(0)=P_{0}\in(0,1)$.",
        ("7.3", "problem", "7.26"): r"The deterministic skeleton of the Ornstein-Uhlenbeck/Vasicek "
                        r"rate model is $\frac{dr}{dt}=\kappa(\theta-r)$ with $r(0)=r_{0}$. "
                        r"Solve for $r(t)$.",
        ("7.3", "problem", "7.27"): r"Given $C(K)=e^{-rT}\int_{K}^{\infty}(S_{T}-K)f(S_{T})dS_{T}$, "
                        r"apply the Leibniz Rule twice with respect to strike $K$ to "
                        r"recover the risk-neutral PDF $f(K)$.",
        ("7.3", "problem", "7.28"): r"If positive-class scores have CDF $F_{1}(s)$ and PDF "
                        r"$f_{1}(s)$, and negative-class scores have CDF $F_{0}(s)$ and PDF "
                        r"$f_{0}(s)$, show that AUC $=\int_{0}^{1}\mathrm{TPR}\,d(\mathrm{FPR})=P(S_{1}>S_{0})$.",
        ("7.3", "problem", "7.29"): r"Verify by integration by parts that "
                        r"$\int_{0}^{F}\frac{(K-S_{T})_{+}}{FK^{2}}dK+\int_{F}^{\infty}"
                        r"\frac{(S_{T}-K)_{+}}{FK^{2}}dK$ reconstructs "
                        r"$-\ln(S_{T}/F)+S_{T}/F-F$.",
        ("7.3", "problem", "7.30"): r"Solve the continuous-time gradient flow "
                        r"$\frac{dw}{dt}=-\nabla L(w)=-\lambda(w-w^{*})$ with "
                        r"$w(0)=w_{0}$ and find the time $T$ required to reduce the "
                        r"error $\|w(T)-w^{*}\|$ by a factor of $e^{-5}$.",
        ("8.4", "problem", "8.1"): r"If $\tan\theta=\frac{3}{4}$ and $\theta\in(\pi,3\pi/2)$, find $\sin\theta$, "
                        r"$\cos\theta$, and $\sec\theta$.",
        ("8.4", "problem", "8.2"): r"If $\sec\theta+\tan\theta=4$, find $\sec\theta$, $\tan\theta$, and $\sin\theta$.",
        ("8.4", "problem", "8.3"): r"Compute the exact radical values of $\sin 15^{\circ}$, "
                        r"$\cos 15^{\circ}$, and $\tan 15^{\circ}$.",
        ("8.4", "problem", "8.4"): r"Find the maximum and minimum values of "
                        r"$f(\theta)=3\cos\theta+4\sin\theta+8$.",
        ("8.4", "problem", "8.5"): r"Prove that "
                        r"$\frac{\sin 5x+\sin 3x}{\cos 5x+\cos 3x}=\tan(4x)$.",
        ("8.4", "problem", "8.6"): r"If $A+B=\frac{\pi}{4}$, prove neatly that "
                        r"$(1+\tan A)(1+\tan B)=2$ and find $\tan(22.5^{\circ})$.",
        ("8.4", "problem", "8.7"): r"Solve $2\cos^{2}\theta+3\sin\theta=0$ for $\theta\in\mathbb{R}$.",
        ("8.4", "problem", "8.8"): r"Evaluate $\arcsin\left(-\frac{1}{2}\right)+"
                        r"\arccos\left(-\frac{1}{2}\right)+\arctan(-1)+\operatorname{arccot}(-1)$.",
        ("8.4", "problem", "8.9"): r"Prove that $\arctan\frac{1}{2}+\arctan\frac{1}{5}+"
                        r"\arctan\frac{1}{8}=\frac{\pi}{4}$.",
        ("8.4", "problem", "8.10"): r"Simplify $\arctan\sqrt{\frac{1-\cos x}{1+\cos x}}$ for $x\in(0,\pi)$.",
        ("8.4", "problem", "8.11"): r"Prove that $\cos^{2}\theta+\cos^{2}(\theta+60^{\circ})+"
                        r"\cos^{2}(\theta-60^{\circ})=\frac{3}{2}$ for all $\theta\in\mathbb{R}$.",
        ("8.4", "problem", "8.12"): r"Evaluate $S=\sin\frac{\pi}{7}+\sin\frac{2\pi}{7}+\cdots+"
                        r"\sin\frac{6\pi}{7}$.",
        ("8.4", "problem", "8.13"): r"Find all real solutions of "
                        r"$\arctan(x-1)+\arctan x+\arctan(x+1)=\arctan(3x)$.",
        ("8.4", "problem", "8.14"): r"Simplify $\arctan\left(1+\frac{\cos x}{\sin x}\right)$ "
                        r"for $x\in(-\pi/2,\pi/2)$.",
        ("8.4", "problem", "8.15"): r"Find the minimum and maximum values of "
                        r"$S(x)=(\arcsin x)^{3}+(\arccos x)^{3}$ on $x\in[-1,1]$.",
        ("8.4", "problem", "8.16"): r"In $\triangle ABC$, if "
                        r"$\frac{\cos A}{a}=\frac{\cos B}{b}=\frac{\cos C}{c}$, prove that "
                        r"$\triangle ABC$ is equilateral.",
        ("8.4", "problem", "8.17"): r"Find the exact number of real solutions of "
                        r"$\sin x=\frac{x}{10}$.",
        ("8.4", "problem", "8.18"): r"Prove the Projection Formula $a=b\cos C+c\cos B$ using "
                        r"the Cosine Rule.",
        ("8.4", "problem", "8.19"): r"Evaluate $\sum_{n=1}^{\infty}\arctan\sqrt{n+1}-\arctan\sqrt{n}$.",
        ("8.4", "problem", "8.20"): r"Express $\cos(4\theta)$ as a degree-4 polynomial in "
                        r"$x=\cos\theta$.",
        ("8.4", "problem", "8.21"): r"In a Transformer, $PE(p)=(\sin(\omega_{1}p),"
                        r"\cos(\omega_{1}p),\ldots,\sin(\omega_{K}p),"
                        r"\cos(\omega_{K}p))$. Prove that "
                        r"$PE(p)^{T}PE(q)=\sum_{k=1}^{K}\cos\omega_{k}(p-q)$.",
        ("8.4", "problem", "8.22"): r"If two embedding vectors $u,v\in\mathbb{R}^{d}$ are "
                        r"$L_{2}$-normalized ($\|u\|_{2}=\|v\|_{2}=1$) with angle $\theta$, "
                        r"express $\|u-v\|_{2}$ in terms of $\sin(\theta/2)$.",
        ("8.4", "problem", "8.23"): r"In deep learning, "
                        r"$\eta_{t}=\eta_{\min}+\frac{1}{2}(\eta_{\max}-\eta_{\min})"
                        r"(1+\cos(\pi t/T))$. Evaluate $\eta_{t}$ and "
                        r"$d\eta_{t}/dt$ at $t=0$, $T/2$, $T$.",
        ("8.4", "problem", "8.24"): r"If $Z_{1}=R\cos\Theta$ and $Z_{2}=R\sin\Theta$, "
                        r"express $(R^{2},\tan\Theta)$ in terms of $(Z_{1},Z_{2})$.",
        ("8.4", "problem", "8.25"): r"A standard Cauchy random variable has PDF "
                        r"$f(x)=\frac{1}{\pi(1+x^{2})}$. Find its CDF $F(x)$ and "
                        r"interquartile range $Q_{0.75}-Q_{0.25}$.",
        ("8.4", "problem", "8.26"): r"Prove that "
                        r"$\int_{-\pi}^{\pi}\sin(mx)\sin(nx)dx=\pi\delta_{mn}$ for "
                        r"positive integers $m,n$.",
        ("8.4", "problem", "8.27"): r"If Asset 1 and Asset 2 have correlation "
                        r"$\rho_{12}=\cos\theta_{12}=0.8$ and Asset 2 and Asset 3 have "
                        r"$\rho_{23}=\cos\theta_{23}=0.6$, find the valid range of "
                        r"$\rho_{13}$.",
        ("8.4", "problem", "8.28"): r"Sampled at $f_{s}=100$ Hz ($t_{n}=n/100$), show that a "
                        r"90 Hz cosine wave $\cos(2\pi\cdot 90t_{n})$ is identical to a "
                        r"10 Hz cosine wave.",
        ("8.4", "problem", "8.29"): r"In Carr-Madan option pricing, $e^{iuk}=\cos(uk)+"
                        r"i\sin(uk)$. Explain why "
                        r"$\operatorname{Re}\int_{0}^{\infty}e^{iuk}\psi(u)du$ uses only the "
                        r"even part of the integrand.",
        ("8.4", "problem", "8.30"): r"What is the maximum absolute value of the monic "
                        r"degree-$n$ polynomial $2^{-(n-1)}T_{n}(x)=2^{-(n-1)}"
                        r"\cos(n\arccos x)$ on $x\in[-1,1]$?",
        ("9.4", "problem", "9.1"): r"Find the direction cosines of a vector that makes equal acute "
                        r"angles with the $x$, $y$, and $z$ axes.",
        ("9.4", "problem", "9.2"): r"Find the scalar and vector projection of "
                        r"$\vec a=2\hat i+3\hat j+2\hat k$ onto "
                        r"$\vec b=\hat i+2\hat j+\hat k$.",
        ("9.4", "problem", "9.3"): r"Find a unit vector perpendicular to both "
                        r"$\vec a=\hat i-2\hat j+3\hat k$ and "
                        r"$\vec b=\hat i+2\hat j-\hat k$.",
        ("9.4", "problem", "9.4"): r"Find the area of $\triangle ABC$ with vertices "
                        r"$A(1,1,1)$, $B(1,2,3)$, $C(2,3,1)$.",
        ("9.4", "problem", "9.5"): r"Find $\lambda$ so that $\vec a=2\hat i-\hat j+\hat k$, "
                        r"$\vec b=\hat i+2\hat j-3\hat k$, and "
                        r"$\vec c=3\hat i+\lambda\hat j+5\hat k$ are coplanar.",
        ("9.4", "problem", "9.6"): r"Find the acute angle between "
                        r"$\frac{x-2}{2}=\frac{y-1}{5}=\frac{z+3}{-3}$ and "
                        r"$\frac{x+2}{-1}=\frac{y-4}{8}=\frac{z-5}{4}$.",
        ("9.4", "problem", "9.7"): r"Find the perpendicular distance from $(2,5,-3)$ to "
                        r"the plane $6x-3y+2z-4=0$.",
        ("9.4", "problem", "9.8"): r"Find the equation of the plane with intercepts $2$, $3$, "
                        r"$-4$ on the $x$, $y$, $z$ axes.",
        ("9.4", "problem", "9.9"): r"Find the foot of the perpendicular from the origin "
                        r"$(0,0,0)$ to the plane $2x+3y+4z-12=0$.",
        ("9.4", "problem", "9.10"): r"Maximize $Z=3x+4y$ subject to $x+y\leq 4$, $x\geq 0$, "
                        r"$y\geq 0$.",
        ("9.4", "problem", "9.11"): r"Prove that for any vector $\vec a$, "
                        r"$|\vec a\times\hat i|^{2}+|\vec a\times\hat j|^{2}+"
                        r"|\vec a\times\hat k|^{2}=2|\vec a|^{2}$.",
        ("9.4", "problem", "9.12"): r"Prove that "
                        r"$[\vec a+\vec b\ \ \vec b+\vec c\ \ \vec c+\vec a]=2[\vec a\ \vec b\ \vec c]$.",
        ("9.4", "problem", "9.13"): r"Prove that "
                        r"$[\vec a\times\vec b\ \ \vec b\times\vec c\ \ \vec c\times\vec a]"
                        r"=[\vec a\ \vec b\ \vec c]^{2}$.",
        ("9.4", "problem", "9.14"): r"Find the volume of the tetrahedron with vertices "
                        r"$A(0,1,2)$, $B(3,0,1)$, $C(4,3,6)$, $D(2,3,2)$.",
        ("9.4", "problem", "9.15"): r"Using 3D direction cosines, find the acute angle "
                        r"between any two main diagonals of a cube.",
        ("9.4", "problem", "9.16"): r"Find the distance between "
                        r"$\vec r=(\hat i+2\hat j-4\hat k)+\lambda(2\hat i+3\hat j+6\hat k)$ "
                        r"and "
                        r"$\vec r=(3\hat i+3\hat j-5\hat k)+\mu(2\hat i+3\hat j+6\hat k)$.",
        ("9.4", "problem", "9.17"): r"Find the point where the line "
                        r"$\frac{x-2}{3}=\frac{y+1}{4}=\frac{z-2}{12}$ meets the plane "
                        r"$x-y+z=5$, and its distance from $(-1,-5,-10)$.",
        ("9.4", "problem", "9.18"): r"Express the line of intersection of $x+y+z=6$ and "
                        r"$x+2y+3z=10$ in symmetric 3D form.",
        ("9.4", "problem", "9.19"): r"Find the distance of $(1,-2,3)$ from the plane "
                        r"$x-y+z=5$ measured parallel to the line "
                        r"$\frac{x}{2}=\frac{y}{3}=\frac{z}{-6}$.",
        ("9.4", "problem", "9.20"): r"Minimize $Z=3x+2y$ subject to $x+y\geq 8$, "
                        r"$3x+5y\geq 15$, $x\geq 0$, $y\geq 0$.",
        ("9.4", "problem", "9.21"): r"If $v(\text{king})=(2,3,1)$, $v(\text{man})=(1,1,1)$, "
                        r"and $v(\text{woman})=(1,2,2)$, compute the query vector "
                        r"$q=v(\text{king})-v(\text{man})+v(\text{woman})$ and its cosine "
                        r"similarity with $v(\text{queen})=(2,4,2)$.",
        ("9.4", "problem", "9.22"): r"Given $u_{1}=(1,1,0)$ and $v_{2}=(1,1,2)$, find the "
                        r"orthogonal component $u_{2}=v_{2}-\operatorname{proj}_{u_{1}}(v_{2})$.",
        ("9.4", "problem", "9.23"): r"If training examples satisfy $\|x_{i}\|_{2}\leq R=4$ and "
                        r"are linearly separable by unit vector $w^{*}$ with margin "
                        r"$\gamma=0.5$, what is Novikoff's upper bound "
                        r"$(R/\gamma)^{2}$ on the number of Perceptron updates?",
        ("9.4", "problem", "9.24"): r"A 1-period market has payoff matrix "
                        r"$D=\begin{pmatrix}1.1&1.1\\1.3&0.9\end{pmatrix}$ and asset "
                        r"prices $p=(1,1)^{T}$. Verify no-arbitrage by finding a strictly "
                        r"positive state-price vector $\psi>0$ solving $D^{T}\psi=p$.",
        ("9.4", "problem", "9.25"): r"Explain how introducing auxiliary variables "
                        r"$z_{i}\geq 0$ converts the piecewise-linear loss "
                        r"$\max(-w^{T}r_{i}-\zeta,0)$ in CVaR minimization into a pure "
                        r"Linear Program.",
        ("9.4", "problem", "9.26"): r"A surface patch at $(0,0,0)$ has normal "
                        r"$n=(1,2,2)$ and is illuminated by a point light at $(3,4,12)$. "
                        r"Compute the Lambertian diffuse intensity "
                        r"$I=\max(0,\hat n\cdot\hat l)$.",
        ("9.4", "problem", "9.27"): r"For unit vector $u$, $Hx=x-2(u\cdot x)u$ reflects $x$ "
                        r"across the hyperplane $u^{\perp}$. Compute $H(1,2,2)^{T}$ for "
                        r"$u=\frac{1}{3}(1,2,2)^{T}$.",
        ("9.4", "problem", "9.28"): r"Data centered at 0 is projected onto unit vector $u$. "
                        r"Express the sample variance of projections $z_{i}=u^{T}x_{i}$ "
                        r"in terms of sample covariance $S=\frac{1}{n}\sum x_{i}x_{i}^{T}$.",
        ("9.4", "problem", "9.29"): r"Distribution $p=(0.5,0.5,0)$ is transported to "
                        r"$q=(0,0.5,0.5)$ along a line with bin distances $|i-j|$. "
                        r"Find the minimum transport cost $W_{1}(p,q)$.",
        ("9.4", "problem", "9.30"): r"In an $N$-stock universe, portfolio weight vector "
                        r"$w\in\mathbb{R}^{N}$ is both dollar-neutral "
                        r"$(\mathbf{1}^{T}w=0)$ and beta-neutral "
                        r"($\beta^{T}w=0$). What is the dimension of the feasible "
                        r"subspace when $\beta\not\propto\mathbf{1}$?",
        ("10.3", "problem", "10.1"): r"Prove that the variance of the first $n$ natural numbers "
                        r"$\{1,2,\ldots,n\}$ is $\sigma^{2}=\frac{n^{2}-1}{12}$ and evaluate it for $n=11$.",
        ("10.3", "problem", "10.2"): r"If $X$ has mean 20 and variance 9, find the mean and "
                        r"standard deviation of $Y=-3X+50$.",
        ("10.3", "problem", "10.3"): r"Stock A has mean price 100 and SD 8; Stock B has mean "
                        r"price 50 and SD 5. Which stock is more consistent?",
        ("10.3", "problem", "10.4"): r"Find the median and mean deviation about the median of "
                        r"$\{3,9,5,3,12,10,18,4,7,19,21\}$.",
        ("10.3", "problem", "10.5"): r"Two students A and B independently solve a problem with "
                        r"probabilities $P(A)=1/2$ and $P(B)=1/3$. Find the probability "
                        r"that (a) the problem is solved, and (b) exactly one solves it.",
        ("10.3", "problem", "10.6"): r"A black die and a red die are rolled. Find the conditional "
                        r"probability that the sum is $>9$ given that the black die "
                        r"resulted in a 5.",
        ("10.3", "problem", "10.7"): r"An urn contains 10 black and 5 white balls. Two balls "
                        r"are drawn one after another without replacement. Find the "
                        r"probability that both are black.",
        ("10.3", "problem", "10.8"): r"Factory I produces 60% of bulbs (2% defective) and "
                        r"Factory II produces 40% (5% defective). A randomly chosen bulb "
                        r"is defective. Find the probability it came from Factory II.",
        ("10.3", "problem", "10.9"): r"For $X\sim\mathrm{Bin}(n,p)$, if $E[X]=4$ and "
                        r"$\operatorname{Var}(X)=3$, find $n$, $p$, and $P(X\geq 1)$.",
        ("10.3", "problem", "10.10"): r"What is the probability that a randomly chosen leap year "
                        r"contains 53 Sundays?",
        ("10.3", "problem", "10.11"): r"Out of 5 observations with mean 4.4 and variance "
                        r"8.24, three are 1, 2, 6. Find the remaining two observations $a,b$.",
        ("10.3", "problem", "10.12"): r"Chest I has 2 gold coins, Chest II has 2 silver coins, "
                        r"and Chest III has 1 gold and 1 silver coin. A chest is chosen at "
                        r"random and one coin drawn is gold. Find the probability the "
                        r"other coin in that chest is also gold.",
        ("10.3", "problem", "10.13"): r"One card is lost from a 52-card pack. From the remaining "
                        r"51 cards, two cards are drawn and both are Diamonds. Find the "
                        r"probability the lost card is a Diamond.",
        ("10.3", "problem", "10.14"): r"Two integers are selected at random without replacement "
                        r"from $\{1,2,\ldots,11\}$. Given that their sum is even, find the "
                        r"probability that both integers are odd.",
        ("10.3", "problem", "10.15"): r"Two fair coins are tossed. Let $A$ = \"H on coin 1\", "
                        r"$B$ = \"H on coin 2\", $C$ = \"coins match (HH or TT)\". "
                        r"Show $A,B,C$ are pairwise independent but not mutually "
                        r"independent.",
        ("10.3", "problem", "10.16"): r"For $X\sim\mathrm{Bin}(n,p)$, show that "
                        r"$P(X=r)$ increases with $r$ iff $r\leq (n+1)p$, and find the "
                        r"most likely number of successes for $n=10$, $p=0.35$.",
        ("10.3", "problem", "10.17"): r"Two friends agree to meet between 12:00 and 1:00 PM, "
                        r"each waiting at most 15 minutes ($\frac{1}{4}$ hour). Find the "
                        r"probability they meet.",
        ("10.3", "problem", "10.18"): r"A subsystem has 3 independent components in parallel "
                        r"with reliabilities 0.8, 0.9, 0.95. Find the probability the "
                        r"parallel subsystem functions.",
        ("10.3", "problem", "10.19"): r"In an exam with 4 choices per question, a student knows "
                        r"the answer with probability $3/4$ and guesses with probability "
                        r"$1/4$. Given the student answered correctly, find the probability "
                        r"they actually knew the answer.",
        ("10.3", "problem", "10.20"): r"Find the probability distribution and expected value "
                        r"of $M=\max(X_{1},X_{2})$ when two fair 6-sided dice are rolled.",
        ("10.3", "problem", "10.21"): r"A fraud detector has 99% sensitivity "
                        r"($P(+|F)=0.99$) and 99% specificity ($P(-|F^{c})=0.99$). If only "
                        r"0.1% of transactions are fraudulent ($P(F)=0.001$), find the "
                        r"precision $P(F|+)$.",
        ("10.3", "problem", "10.22"): r"Show that under conditional independence "
                        r"$P(x_{1},\ldots,x_{d}|y)=\prod_{j=1}^{d}P(x_{j}|y)$, the posterior "
                        r"log-odds $\ln\frac{P(y=1|x)}{P(y=0|x)}$ is an additive linear "
                        r"model in the log-likelihood ratios.",
        ("10.3", "problem", "10.23"): r"Two GPU mini-batches of size $m_{1}=m_{2}=32$ have "
                        r"means $\mu_{1}=1.0$, $\mu_{2}=3.0$ and variances "
                        r"$\sigma_{1}^{2}=2.0$, $\sigma_{2}^{2}=4.0$. Compute the exact "
                        r"variance of the combined batch of 64.",
        ("10.3", "problem", "10.24"): r"An ensemble of 5 independent classifiers each has "
                        r"accuracy $p=0.7$. Find the accuracy of majority voting ($X\geq 3$).",
        ("10.3", "problem", "10.25"): r"During training, each neuron $h_{i}$ is kept with "
                        r"probability $p\in(0,1)$ via $B_{i}\sim\mathrm{Bernoulli}(p)$ and "
                        r"scaled as $\tilde h_{i}=\frac{1}{p}B_{i}h_{i}$. Compute "
                        r"$E[\tilde h_{i}]$ and $\operatorname{Var}(\tilde h_{i})$.",
        ("10.3", "problem", "10.26"): r"A stock at $S_{0}=100$ moves to $S_{u}=120$ "
                        r"($u=1.2$) or $S_{d}=90$ ($d=0.9$) over 1 year with risk-free "
                        r"rate $R=1+r=1.05$. Find the risk-neutral probability $p^{*}$ "
                        r"and price a call with strike $K=105$.",
        ("10.3", "problem", "10.27"): r"A portfolio holds $n=10$ independent bonds, each "
                        r"with default probability $p=0.02$ and notional 1M (zero recovery). "
                        r"Find the expected loss and standard deviation of loss.",
        ("10.3", "problem", "10.28"): r"A parent node has 50 Class-0 and 50 Class-1 samples "
                        r"(Gini $G=1-p_{0}^{2}-p_{1}^{2}=0.5$). A split creates Left "
                        r"(40 Class-0, 10 Class-1) and Right (10 Class-0, 40 Class-1). "
                        r"Compute the Gini impurity reduction $\Delta G$.",
        ("10.3", "problem", "10.29"): r"A strategy has daily mean excess return "
                        r"$\mu_{d}=0.05\%$ and daily volatility $\sigma_{d}=1.0\%$. "
                        r"Assuming 252 independent trading days per year, find the "
                        r"annualized Sharpe ratio.",
        ("10.3", "problem", "10.30"): r"An equity quant signal has skill correlation "
                        r"$\mathrm{IC}=0.05$ across $N=400$ independent bets per year. "
                        r"Compute the expected Information Ratio "
                        r"$\mathrm{IR}=\mathrm{IC}\sqrt{N}$.",
        ("11.5", "problem", "11.1"): r"Find the inverse function $f^{-1}(y)$ of "
                        r"$f(x)=3e^{2x}-1$ and state its domain.",
        ("11.5", "problem", "11.2"): r"Evaluate $S=\ln(e^{3})+\log_{2}(32)-\ln(e^{-2})$ "
                        r"without a calculator.",
        ("11.5", "problem", "11.3"): r"Compute $S=1+2+4+8+\cdots+512$ using the finite geometric "
                        r"series formula.",
        ("11.5", "problem", "11.4"): r"Without finding the roots $r_{1},r_{2}$ of "
                        r"$2x^{2}-10x+6=0$, compute $r_{1}+r_{2}$, $r_{1}r_{2}$, and "
                        r"$r_{1}^{2}+r_{2}^{2}$.",
        ("11.5", "problem", "11.5"): r"Compute $(1+i)^{8}$ exactly using polar coordinates.",
        ("11.5", "problem", "11.6"): r"Prove that $\tanh(x/2)=2\sigma(x)-1$, where "
                        r"$\sigma(x)=\frac{1}{1+e^{-x}}$.",
        ("11.5", "problem", "11.7"): r"Show that $\zeta(x)=\ln(1+e^{x})$ satisfies "
                        r"$\zeta(x)-\zeta(-x)=x$, and write its overflow-safe form.",
        ("11.5", "problem", "11.8"): r"Evaluate $S=\sum_{n=1}^{\infty}\frac{1}{n(n+2)}$ in "
                        r"exact closed form.",
        ("11.5", "problem", "11.9"): r"An index goes +10% on Day 1 and -10% on Day 2. "
                        r"Compare the 2-day return of the index vs. a 3x daily "
                        r"leveraged ETF.",
        ("11.5", "problem", "11.10"): r"Stock $S_{T}$ is Rs. 80 or Rs. 120 with probability "
                        r"0.5 each, and strike $K=$ Rs. 100. Compare "
                        r"$E[\max(S_{T}-100,0)]$ vs "
                        r"$\max(E[S_{T}]-100,0)$.",
        ("11.5", "problem", "11.11"): r"Given 3 uncorrelated assets with Sharpe ratios "
                        r"$s=[0.6,0.8,1.0]^{T}$, find $\max_{w}\frac{w^{T}s}{\|w\|_{2}}$.",
        ("11.5", "problem", "11.12"): r"Prove that for $|r|<1$, "
                        r"$\sum_{k=1}^{\infty}kr^{k}=\frac{r}{(1-r)^{2}}$.",
        ("11.5", "problem", "11.13"): r"Prove that for any integer $m\not\equiv 0\pmod N$, "
                        r"$\sum_{k=0}^{N-1}e^{i2\pi mk/N}=0$.",
        ("11.5", "problem", "11.14"): r"For what real $k$ does $4x^{2}+2kx+9=0$ have "
                        r"complex conjugate roots, and what is their modulus $|z|$?",
        ("11.5", "problem", "11.15"): r"Prove that for any $z\in\mathbb{R}^{K}$, "
                        r"$\max_{j}z_{j}<\mathrm{LSE}(z_{1},\ldots,z_{K})\leq "
                        r"\max_{j}z_{j}+\ln(K)$.",
        ("11.5", "problem", "11.16"): r"Compute the Fenchel conjugate "
                        r"$f^{*}(y)=\sup_{x\in\mathbb{R}^{d}}(y^{T}x-\frac{1}{2}x^{T}Qx)$ "
                        r"for symmetric positive definite $Q\succ 0$.",
        ("11.5", "problem", "11.17"): r"For $\mathrm{LSE}_{\tau}(z)=\tau\ln\sum_{i=1}^{K}e^{z_{i}/\tau}$ "
                        r"with $\tau>0$, prove $\max_{i}z_{i}\leq "
                        r"\mathrm{LSE}_{\tau}(z)\leq \max_{i}z_{i}+\tau\ln K$.",
        ("11.5", "problem", "11.18"): r"Use $|u||v|\leq \frac{1}{p}|u|^{p}+\frac{1}{q}|v|^{q}$ "
                        r"($\frac{1}{p}+\frac{1}{q}=1$) to prove Hölder's inequality "
                        r"$|u^{T}v|\leq\|u\|_{p}\|v\|_{q}$.",
        ("11.5", "problem", "11.19"): r"For Constant Relative Risk Aversion utility "
                        r"$U(W)=\frac{W^{1-\gamma}-1}{1-\gamma}$ ($\gamma>0,\gamma\neq 1$), "
                        r"compute $-WU''(W)/U'(W)$ and $\lim_{\gamma\to 1}U(W)$.",
        ("11.5", "problem", "11.20"): r"Write the $3\times 3$ companion matrix $C$ whose "
                        r"characteristic polynomial is "
                        r"$\lambda^{3}+a_{2}\lambda^{2}+a_{1}\lambda+a_{0}=0$.",
        ("11.5", "problem", "11.21"): r"Using strict concavity of $\ln u$, prove Gibbs' "
                        r"inequality $D_{\mathrm{KL}}(P\|Q)=\sum_{x}P(x)\ln\frac{P(x)}{Q(x)}\geq 0$.",
        ("11.5", "problem", "11.22"): r"For $\phi(x)=\frac{1}{2}\|x\|_{2}^{2}$, compute the "
                        r"Bregman divergence $D_{\phi}(x,y)=\phi(x)-\phi(y)-\langle\nabla\phi(y),x-y\rangle$.",
        ("11.5", "problem", "11.23"): r"If $X_{k}=\frac{1}{\sqrt{N}}\sum_{n=0}^{N-1}x_{n}e^{-i2\pi kn/N}$, "
                        r"explain why $\sum_{k=0}^{N-1}|X_{k}|^{2}=\sum_{n=0}^{N-1}|x_{n}|^{2}$.",
        ("11.5", "problem", "11.24"): r"Prove that $f(q)=\sqrt{q}$ is subadditive on "
                        r"$q\geq 0$: $\sqrt{q_{1}+q_{2}}\leq\sqrt{q_{1}}+\sqrt{q_{2}}$.",
        ("11.5", "problem", "11.25"): r"If all $n$ roots $r_{1},\ldots,r_{n}$ of "
                        r"$x^{n}+a_{n-1}x^{n-1}+a_{n-2}x^{n-2}+\cdots+a_{0}=0$ are real, "
                        r"express $\sum_{i=1}^{n}r_{i}^{2}$ in terms of $a_{n-1},a_{n-2}$ "
                        r"and deduce $a_{n-1}^{2}\geq 2a_{n-2}$.",
        ("12.4", "problem", "12.1"): r"Compute $f'(x)$ for $f(x)=x^{2}e^{-3x}$ and find all critical points where $f'(x)=0$.",
        ("12.4", "problem", "12.2"): r"Evaluate $\lim_{x\to 0}\frac{e^{2x}-1-2x}{x^{2}}$.",
        ("12.4", "problem", "12.3"): r"Evaluate $\int_{0}^{1}\frac{1}{2}xe^{-x^{2}}dx$.",
        ("12.4", "problem", "12.4"): r"Find the directional derivative of $f(x,y)=x^{2}+xy$ at "
                        r"$(1,2)$ along $v=[3,4]^{T}$.",
        ("12.4", "problem", "12.5"): r"Solve $\frac{dy}{dt}=-2ty$ with initial condition $y(0)=5$.",
        ("12.4", "problem", "12.6"): r"Prove from calculus that $\lim_{n\to\infty}\left(1+\frac{r}{n}\right)^{nt}=e^{rt}$.",
        ("12.4", "problem", "12.7"): r"Prove that for $p(x)=\lambda e^{-\lambda x}$ ($x\geq 0$), "
                        r"$E[X]=1/\lambda$ and $\operatorname{Var}(X)=1/\lambda^{2}$.",
        ("12.4", "problem", "12.8"): r"For $\ell(z)=-y\ln\sigma(z)-(1-y)\ln(1-\sigma(z))$, compute "
                        r"$\ell'(z)$ and $\ell''(z)$.",
        ("12.4", "problem", "12.9"): r"Solve $\frac{dx}{dt}=\kappa(\theta-x)$ with $x(0)=x_{0}$.",
        ("12.4", "problem", "12.10"): r"Classify all critical points of $f(x,y)=x^{3}-3xy+y^{3}$.",
        ("12.4", "problem", "12.11"): r"Differentiate $\int_{-\infty}^{\infty}e^{-\alpha x^{2}}dx=\sqrt{\pi/\alpha}$ "
                        r"with respect to $\alpha$ to evaluate $\int_{-\infty}^{\infty}x^{2}e^{-x^{2}/(2\sigma^{2})}dx$.",
        ("12.4", "problem", "12.12"): r"Verify that $u(x,t)=(4\pi Dt)^{-1/2}e^{-x^{2}/(4Dt)}$ satisfies "
                        r"$\frac{\partial u}{\partial t}=D\frac{\partial^{2}u}{\partial x^{2}}$.",
        ("12.4", "problem", "12.13"): r"For $\Gamma(z)=\int_{0}^{\infty}t^{z-1}e^{-t}dt$, prove "
                        r"$\Gamma(z+1)=z\Gamma(z)$ and $\Gamma(1/2)=\sqrt{\pi}$.",
        ("12.4", "problem", "12.14"): r"For $f(x)=x\sigma(x)$, show that "
                        r"$f'(x)=\sigma(x)+f(x)(1-\sigma(x))$.",
        ("12.4", "problem", "12.15"): r"If $C(\lambda S,\lambda K)=\lambda C(S,K)$ for all "
                        r"$\lambda>0$, prove $S\frac{\partial C}{\partial S}+K\frac{\partial C}{\partial K}=C(S,K)$.",
        ("12.4", "problem", "12.16"): r"Verify $\nabla_{w}(\nabla f(w)^{T}v)=Hv$ explicitly for "
                        r"$f(w)=\frac{1}{2}w^{T}Aw-b^{T}w$ ($A=A^{T}$).",
        ("12.4", "problem", "12.17"): r"For $x=r\sin\theta\cos\phi$, $y=r\sin\theta\sin\phi$, "
                        r"$z=r\cos\theta$, state the Jacobian determinant $|\det J|$ and integrate "
                        r"$\int_{\mathbb{R}^{3}}e^{-(x^{2}+y^{2}+z^{2})}dxdydz$.",
        ("12.4", "problem", "12.18"): r"For $r=\|x\|_{2}$ in $\mathbb{R}^{d}$, compute $\nabla r$ and "
                        r"$\nabla^{2}(r^{2})$.",
        ("12.4", "problem", "12.19"): r"Using Leibniz differentiation under the integral sign on "
                        r"$\int p_{\theta}(x)dx=1$, prove that the expected score vanishes: "
                        r"$E_{\theta}[\nabla_{\theta}\ln p_{\theta}(X)]=0$.",
        ("12.4", "problem", "12.20"): r"Prove Fisher's identity "
                        r"$E(\nabla_{\theta}\ln p_{\theta})(\nabla_{\theta}\ln p_{\theta})^{T}="
                        r"-E[\nabla_{\theta}^{2}\ln p_{\theta}]$.",
        ("12.4", "problem", "12.21"): r"If portfolio VaR $VaR(w)$ is homogeneous of degree 1 "
                        r"($VaR(\lambda w)=\lambda VaR(w)$ for $\lambda>0$), prove the Euler risk "
                        r"decomposition $VaR(w)=\sum_{i=1}^{N}w_{i}\frac{\partial VaR}{\partial w_{i}}$.",
        ("12.4", "problem", "12.22"): r"For $f(x,y)=x^{3}-3xy^{2}$ (the monkey saddle) and "
                        r"$g(x,y)=x^{2}-y^{2}$, classify $(0,0)$ of $g(x,y)$ via the Hessian determinant.",
        ("12.4", "problem", "12.23"): r"Verify that $\omega=(3x^{2}y+2x)dx+(x^{3}-2y)dy$ is "
                        r"closed ($\partial P/\partial y=\partial Q/\partial x$) and evaluate "
                        r"$\int_{(0,0)}^{(1,2)}\omega$.",
        ("12.4", "problem", "12.24"): r"For $Z\sim\mathcal{N}(0,1)$ and differentiable $g$, prove "
                        r"Stein's identity $E[Zg(Z)]=E[g'(Z)]$ via integration by parts.",
        ("12.4", "problem", "12.25"): r"Given $F(x,y)=x^{3}+y^{3}-3xy=0$ (Folium of Descartes) "
                        r"at $(3/2,3/2)$, compute $dy/dx=-F_{x}/F_{y}$.",
        ("13.4", "problem", "13.1"): r"Find $(\cos\theta,\sin\theta)$ at $\theta=\pi$ and $\theta=3\pi/2$.",
        ("13.4", "problem", "13.2"): r"If $\sin\theta=\frac{3}{5}$ with $\theta\in(0,\pi/2)$, find $\cos\theta$, "
                        r"$\tan\theta$, and $\sin(2\theta)$.",
        ("13.4", "problem", "13.3"): r"Evaluate $\lim_{x\to 0}\frac{\sin(5x)}{2x}$ and "
                        r"$\lim_{x\to 0}\frac{1-\cos x}{x^{2}}$.",
        ("13.4", "problem", "13.4"): r"Evaluate $\int_{0}^{1}\frac{dx}{1+x^{2}}$ and "
                        r"$\int_{0}^{\infty}\frac{dx}{1+x^{2}}$.",
        ("13.4", "problem", "13.5"): r"Verify from $\cosh x=\frac{e^{x}+e^{-x}}{2}$ and "
                        r"$\sinh x=\frac{e^{x}-e^{-x}}{2}$ that $\cosh^{2}x-\sinh^{2}x=1$.",
        ("13.4", "problem", "13.6"): r"For $\eta_{t}=\frac{1}{2}\eta_{0}\left(1+\cos(\pi t/T)\right)$, "
                        r"evaluate $\eta_{t}$ at $t=0,T/3,T/2,T$.",
        ("13.4", "problem", "13.7"): r"Prove that $\int_{-\pi}^{\pi}\cos(2x)\cos(5x)\,dx=0$.",
        ("13.4", "problem", "13.8"): r"For Cauchy PDF $p(x)=\frac{1}{\pi(1+x^{2})}$, find the "
                        r"95% quantile $x_{0.95}$.",
        ("13.4", "problem", "13.9"): r"Prove that $\operatorname{arsinh}(y)=\ln\left(y+\sqrt{y^{2}+1}\right)$.",
        ("13.4", "problem", "13.10"): r"Compute the 4-point DFT $X_{k}=\sum_{n=0}^{3}x_{n}e^{-i\pi kn/2}$ "
                        r"of $x=[2,0,-2,0]$.",
        ("13.4", "problem", "13.11"): r"Find $b_{n}$ for $f(t)=\operatorname{sign}(\sin t)$ on "
                        r"$(-\pi,\pi)$ and evaluate at $t=\pi/2$.",
        ("13.4", "problem", "13.12"): r"Apply Parseval's theorem "
                        r"$\frac{1}{\pi}\int_{-\pi}^{\pi}|f(t)|^{2}dt=\sum_{n=1}^{\infty}b_{n}^{2}$ "
                        r"to Ex 13.11.",
        ("13.4", "problem", "13.13"): r"Show that $Z_{1}=\sqrt{-2\ln U_{1}}\cos(2\pi U_{2})$ and "
                        r"$Z_{2}=\sqrt{-2\ln U_{1}}\sin(2\pi U_{2})$ satisfy "
                        r"$Z_{1}^{2}+Z_{2}^{2}\sim\mathrm{Exp}(1/2)$.",
        ("13.4", "problem", "13.14"): r"Prove $1+2\sum_{k=1}^{n}\cos(k\theta)=\frac{\sin((n+1/2)\theta)}{\sin(\theta/2)}$.",
        ("13.4", "problem", "13.15"): r"For $T_{n}(x)=\cos(n\arccos x)$, prove "
                        r"$T_{n+1}(x)=2xT_{n}(x)-T_{n-1}(x)$ and find $T_{2}(x)$, $T_{3}(x)$.",
        ("13.4", "problem", "13.16"): r"For the RBF kernel $k(x,y)=e^{-\|x-y\|^{2}/2}$, state the "
                        r"spectral density $p(\omega)$ in Bochner's theorem and the unbiased "
                        r"2D feature map $\varphi_{\omega}(x)$.",
        ("13.4", "problem", "13.17"): r"Compare direct $N^{2}$ convolution ops vs. $3N\log_{2}N$ "
                        r"FFT convolution ops for $N=2^{16}=65{,}536$.",
        ("13.4", "problem", "13.18"): r"Prove $\tanh(x+y)=\frac{\tanh x+\tanh y}{1+\tanh x\tanh y}$ "
                        r"from $\sinh$ and $\cosh$.",
        ("13.4", "problem", "13.19"): r"Compute $\frac{d}{dx}\ln\left(x+\sqrt{x^{2}+1}\right)$.",
        ("13.4", "problem", "13.20"): r"For $D_{N}(x)=\frac{\sin((N+1/2)x)}{\sin(x/2)}=1+2\sum_{k=1}^{N}\cos(kx)$, "
                        r"evaluate $\frac{1}{2\pi}\int_{-\pi}^{\pi}D_{N}(x)dx$.",
        ("13.4", "problem", "13.21"): r"Apply Parseval's identity "
                        r"$\frac{1}{\pi}\int_{-\pi}^{\pi}x^{2}dx=\sum_{n=1}^{\infty}b_{n}^{2}$ "
                        r"to $f(x)=x$ on $(-\pi,\pi)$ where $b_{n}=\frac{2(-1)^{n+1}}{n}$ "
                        r"to deduce $\sum_{n=1}^{\infty}1/n^{2}=\pi^{2}/6$.",
        ("13.4", "problem", "13.22"): r"For $X_{t}=\phi X_{t-1}+\epsilon_{t}$ ($|\phi|<1$, "
                        r"$\operatorname{Var}(\epsilon_{t})=\sigma^{2}$), compute the power "
                        r"spectral density $S(\omega)=\sigma^{2}/|1-\phi e^{-i\omega}|^{2}$.",
        ("13.4", "problem", "13.23"): r"A Hann window is $w[n]=\frac{1}{2}\left(1-\cos\frac{2\pi n}{N-1}\right)$. "
                        r"Compute its average power $\frac{1}{N}\sum_{n=0}^{N-1}w[n]^{2}$.",
        ("13.4", "problem", "13.24"): r"Under risk aversion $\lambda>0$, optimal liquidation inventory "
                        r"solves $\ddot q=\kappa^{2}q$ with $q(0)=Q$, $q(T)=0$. Show "
                        r"$q(t)=Q\frac{\sinh(\kappa(T-t))}{\sinh(\kappa T)}$.",
        ("13.4", "problem", "13.25"): r"Given characteristic function $\phi_{X}(u)=E[e^{iuX}]$, "
                        r"state the Gil-Pelaez integral for $P(X>k)$.",
        ("13.4", "problem", "13.1"): r"Find $(\cos\theta,\sin\theta)$ at $\theta=\pi$ and $\theta=3\pi/2$.",
        ("13.4", "problem", "13.2"): r"If $\sin\theta=\frac{3}{5}$ with $\theta\in(0,\pi/2)$, find $\cos\theta$, "
                        r"$\tan\theta$, and $\sin(2\theta)$.",
        ("13.4", "problem", "13.3"): r"Evaluate $\lim_{x\to 0}\frac{\sin(5x)}{2x}$ and "
                        r"$\lim_{x\to 0}\frac{1-\cos x}{x^{2}}$.",
        ("13.4", "problem", "13.4"): r"Evaluate $\int_{0}^{1}\frac{dx}{1+x^{2}}$ and "
                        r"$\int_{0}^{\infty}\frac{dx}{1+x^{2}}$.",
        ("13.4", "problem", "13.5"): r"Verify from $\cosh x=\frac{e^{x}+e^{-x}}{2}$ and "
                        r"$\sinh x=\frac{e^{x}-e^{-x}}{2}$ that $\cosh^{2}x-\sinh^{2}x=1$.",
        ("13.4", "problem", "13.6"): r"For $\eta_{t}=\frac{1}{2}\eta_{0}(1+\cos(\pi t/T))$, "
                        r"evaluate $\eta_{t}$ at $t=0,T/3,T/2,T$.",
        ("13.4", "problem", "13.7"): r"Prove that $\int_{-\pi}^{\pi}\cos(2x)\cos(5x)\,dx=0$.",
        ("13.4", "problem", "13.8"): r"For Cauchy PDF $p(x)=\frac{1}{\pi(1+x^{2})}$, find the "
                        r"95% quantile $x_{0.95}$.",
        ("13.4", "problem", "13.9"): r"Prove that $\operatorname{arsinh}(y)=\ln\left(y+\sqrt{y^{2}+1}\right)$.",
        ("13.4", "problem", "13.10"): r"Compute the 4-point DFT $X_{k}=\sum_{n=0}^{3}x_{n}e^{-i\pi kn/2}$ "
                        r"of $x=[2,0,-2,0]$.",
        ("13.4", "problem", "13.11"): r"Find $b_{n}$ for $f(t)=\operatorname{sign}(\sin t)$ on "
                        r"$(-\pi,\pi)$ and evaluate at $t=\pi/2$.",
        ("13.4", "problem", "13.12"): r"Apply Parseval's theorem "
                        r"$\frac{1}{\pi}\int_{-\pi}^{\pi}|f(t)|^{2}dt=\sum_{n=1}^{\infty}b_{n}^{2}$ "
                        r"to Ex 13.11.",
        ("13.4", "problem", "13.13"): r"Show that $Z_{1}=\sqrt{-2\ln U_{1}}\cos(2\pi U_{2})$ and "
                        r"$Z_{2}=\sqrt{-2\ln U_{1}}\sin(2\pi U_{2})$ satisfy "
                        r"$Z_{1}^{2}+Z_{2}^{2}\sim\mathrm{Exp}(1/2)$.",
        ("13.4", "problem", "13.14"): r"Prove $1+2\sum_{k=1}^{n}\cos(k\theta)=\frac{\sin((n+1/2)\theta)}{\sin(\theta/2)}$.",
        ("13.4", "problem", "13.15"): r"For $T_{n}(x)=\cos(n\arccos x)$, prove "
                        r"$T_{n+1}(x)=2xT_{n}(x)-T_{n-1}(x)$ and find $T_{2}(x)$, $T_{3}(x)$.",
        ("13.4", "problem", "13.16"): r"For the RBF kernel $k(x,y)=e^{-\|x-y\|^{2}/2}$, state the "
                        r"spectral density $p(\omega)$ in Bochner's theorem and the unbiased "
                        r"2D feature map $\varphi_{\omega}(x)$.",
        ("13.4", "problem", "13.17"): r"Compare direct $N^{2}$ convolution ops vs. $3N\log_{2}N$ "
                        r"FFT convolution ops for $N=2^{16}=65{,}536$.",
        ("13.4", "problem", "13.18"): r"Prove $\tanh(x+y)=\frac{\tanh x+\tanh y}{1+\tanh x\tanh y}$ "
                        r"from $\sinh$ and $\cosh$.",
        ("13.4", "problem", "13.19"): r"Compute $\frac{d}{dx}\ln\left(x+\sqrt{x^{2}+1}\right)$.",
        ("13.4", "problem", "13.20"): r"For $D_{N}(x)=\frac{\sin((N+1/2)x)}{\sin(x/2)}=1+2\sum_{k=1}^{N}\cos(kx)$, "
                        r"evaluate $\frac{1}{2\pi}\int_{-\pi}^{\pi}D_{N}(x)dx$.",
        ("13.4", "problem", "13.21"): r"Apply Parseval's identity "
                        r"$\frac{1}{\pi}\int_{-\pi}^{\pi}x^{2}dx=\sum_{n=1}^{\infty}b_{n}^{2}$ "
                        r"to $f(x)=x$ on $(-\pi,\pi)$ where $b_{n}=\frac{2(-1)^{n+1}}{n}$ "
                        r"to deduce $\sum_{n=1}^{\infty}1/n^{2}=\pi^{2}/6$.",
        ("13.4", "problem", "13.22"): r"For $X_{t}=\phi X_{t-1}+\epsilon_{t}$ ($|\phi|<1$, "
                        r"$\operatorname{Var}(\epsilon_{t})=\sigma^{2}$), compute the power "
                        r"spectral density $S(\omega)=\sigma^{2}/|1-\phi e^{-i\omega}|^{2}$.",
        ("13.4", "problem", "13.23"): r"A Hann window is $w[n]=\frac{1}{2}(1-\cos\frac{2\pi n}{N-1})$. "
                        r"Compute its average power $\frac{1}{N}\sum_{n=0}^{N-1}w[n]^{2}$.",
        ("13.4", "problem", "13.24"): r"Under risk aversion $\lambda>0$, optimal liquidation inventory "
                        r"solves $\ddot q=\kappa^{2}q$ with $q(0)=Q$, $q(T)=0$. Show "
                        r"$q(t)=Q\frac{\sinh(\kappa(T-t))}{\sinh(\kappa T)}$.",
        ("13.4", "problem", "13.25"): r"Given characteristic function $\phi_{X}(u)=E[e^{iuX}]$, "
                        r"state the Gil-Pelaez integral for $P(X>k)$.",
        ("14.4", "problem", "14.1"): r"Find $k$ so that $u=[2,k,-1]^{T}$ and $v=[3,-2,4]^{T}$ are orthogonal.",
        ("14.4", "problem", "14.2"): r"If $A\in\mathbb{R}^{5\times 8}$ has rank $r=3$, find "
                        r"$\dim N(A)$ and $\dim N(A^{T})$.",
        ("14.4", "problem", "14.3"): r"If $A\in\mathbb{R}^{2\times 2}$ has eigenvalues "
                        r"$\lambda_{1}=7$, $\lambda_{2}=-2$, find $\operatorname{tr}(A)$, "
                        r"$\det(A)$, and $\det(A^{-1})$.",
        ("14.4", "problem", "14.4"): r"Compute $\|A\|_{F}$ for "
                        r"$A=\begin{pmatrix}1&-2\\2&-4\end{pmatrix}$.",
        ("14.4", "problem", "14.5"): r"Rewrite $x^{T}\begin{pmatrix}2&5\\1&4\end{pmatrix}x$ "
                        r"using a symmetric matrix $S$.",
        ("14.4", "problem", "14.6"): r"For $A=\begin{pmatrix}3&1\\1&3\end{pmatrix}$, find its "
                        r"eigenvalues, orthonormal eigenvectors, and $A^{10}$.",
        ("14.4", "problem", "14.7"): r"Fit $y=\beta_{0}+\beta_{1}x$ to $(-1,1)$, $(0,1)$, $(1,4)$ "
                        r"via $\hat\beta=(X^{T}X)^{-1}X^{T}y$.",
        ("14.4", "problem", "14.8"): r"A $1000\times 1000$ weight matrix has singular values "
                        r"$10,5,1,0.1$. Find the rank-2 Frobenius error and % energy retained.",
        ("14.4", "problem", "14.9"): r"Derive $\hat w_{\mathrm{ridge}}=(X^{T}X+\lambda I)^{-1}X^{T}y$ "
                        r"($\lambda>0$) and prove $X^{T}X+\lambda I\succ 0$.",
        ("14.4", "problem", "14.10"): r"Verify that $S=\begin{pmatrix}2&-1&0\\-1&2&-1\\0&-1&2"
                        r"\end{pmatrix}$ is positive definite.",
        ("14.4", "problem", "14.11"): r"Prove that $P=X(X^{T}X)^{-1}X^{T}$ ($X\in"
                        r"\mathbb{R}^{n\times d}$ of rank $d$) has eigenvalues "
                        r"$\lambda\in\{0,1\}$ and $\operatorname{tr}(P)=d$.",
        ("14.4", "problem", "14.12"): r"Use $A^{2}-\operatorname{tr}(A)A+\det(A)I=0$ to "
                        r"express $A^{-1}$.",
        ("14.4", "problem", "14.13"): r"For unit vector $\|u\|_{2}=1$, prove $H=I-2uu^{T}$ is "
                        r"symmetric, orthogonal, and has $\det(H)=-1$.",
        ("14.4", "problem", "14.14"): r"Find all eigenvalues of the $n\times n$ correlation matrix "
                        r"$C=(1-\rho)I_{n}+\rho\mathbf{1}\mathbf{1}^{T}$ and the range of $\rho$ "
                        r"where $C\succ 0$.",
        ("14.4", "problem", "14.15"): r"Maximize $\ell(\Omega)=\ln\det(\Omega)-\operatorname{tr}(S\Omega)$ "
                        r"over $\Omega=\Sigma^{-1}\succ 0$.",
        ("14.4", "problem", "14.16"): r"If $A=U\Sigma V^{T}$ has non-zero singular values "
                        r"$\sigma_{1},\ldots,\sigma_{r}$, write $A^{+}$ and verify $AA^{+}A=A$.",
        ("14.4", "problem", "14.17"): r"For $Ax=b$ with $\sigma_{\max}(A)=100$ and "
                        r"$\sigma_{\min}(A)=0.01$, find $\kappa_{2}(A)$ and the worst-case "
                        r"relative error amplification $\|\Delta x\|_{2}/\|x\|_{2}$. ",
        ("14.4", "problem", "14.18"): r"Construct the lower-triangular Cholesky factor $L$ "
                        r"($LL^{T}=\Sigma$) for $\Sigma=\begin{pmatrix}1&\rho\\\rho&1\end{pmatrix}$.",
        ("14.4", "problem", "14.19"): r"Use Gershgorin's Theorem to prove that "
                        r"$A=\begin{pmatrix}4&-1&1\\-1&5&2\\1&2&6\end{pmatrix}$ is strictly "
                        r"positive definite without computing its characteristic polynomial.",
        ("14.4", "problem", "14.20"): r"A matrix has eigenvalues $\lambda_{1}=4$, $\lambda_{2}=2$, "
                        r"$\lambda_{3}=-1$. At what geometric rate does Power Iteration converge to $u_{1}$?",
        ("14.4", "problem", "14.21"): r"Prove that if $S^{T}=-S$, then $Q=e^{S}$ is an orthogonal "
                        r"matrix with $\det(Q)=+1$.",
        ("14.4", "problem", "14.22"): r"If $A\in\mathbb{R}^{m\times m}$ has eigenvalues $\lambda_{i}$ "
                        r"and $B\in\mathbb{R}^{n\times n}$ has eigenvalues $\mu_{j}$, express "
                        r"$\operatorname{Tr}(A\otimes B)$ and the eigenvalues of $A\otimes B$.",
        ("14.4", "problem", "14.23"): r"For symmetric block matrix "
                        r"$M=\begin{pmatrix}A&B\\B^{T}&C\end{pmatrix}$ with $A\succ 0$, state the "
                        r"Schur complement condition for $M\succ 0$.",
        ("14.4", "problem", "14.24"): r"If $A$ has singular values $\sigma=(5,3,1)$, evaluate "
                        r"$\|A\|_{2}$, $\|A\|_{F}$, and the nuclear (trace) norm "
                        r"$\|A\|_{*}=\sum_{i}\sigma_{i}$.",
        ("15.4", "problem", "15.1"): r"A trade wins Rs. 300 ($p=0.6$) or loses Rs. 200 ($q=0.4$). "
                        r"Compute $E[X]$ and $\sigma_{X}$.",
        ("15.4", "problem", "15.2"): r"If limit orders arrive at rate $\lambda=3$/sec, what is the "
                        r"probability of 0 orders in 1 second?",
        ("15.4", "problem", "15.3"): r"For $X\in\{-1,0,+1\}$ with probability $1/3$ each and "
                        r"$Y=X^{2}$, show $\operatorname{Cov}(X,Y)=0$.",
        ("15.4", "problem", "15.4"): r"A strategy has daily mean 0.05% and daily volatility 1.0% "
                        r"(252 days/yr). Find annualized Sharpe ratio.",
        ("15.4", "problem", "15.5"): r"Find the variance and standard deviation of $X\sim t_{4}$ "
                        r"($\nu=4$).",
        ("15.4", "problem", "15.6"): r"2% of signals are true alpha ($A$). A test has "
                        r"$P(+|A)=90\%$ and $P(+|A^{c})=9\%$. Find $P(A|+)$.",
        ("15.4", "problem", "15.7"): r"Find $\operatorname{Var}\left(\frac{1}{n}\sum_{i=1}^{n}X_{i}\right)$ "
                        r"for $n$ stocks with variance $\sigma^{2}$ and pairwise correlation "
                        r"$\rho$, and take $n\to\infty$.",
        ("15.4", "problem", "15.8"): r"Derive $\hat\lambda_{\mathrm{MLE}}$ for "
                        r"$t_{1},\ldots,t_{n}\sim\mathrm{Exp}(\lambda)$.",
        ("15.4", "problem", "15.9"): r"Find $(\pi_{1},\pi_{2})$ for "
                        r"$P=\begin{pmatrix}0.95&0.05\\0.15&0.85\end{pmatrix}$.",
        ("15.4", "problem", "15.10"): r"Prove $D_{\mathrm{KL}}(N(\mu,\sigma^{2})\|N(0,1))="
                        r"\frac{1}{2}(\mu^{2}+\sigma^{2}-1-\ln\sigma^{2})$.",
        ("15.4", "problem", "15.11"): r"For jointly normal $(X,Y)$ with means 0, variances "
                        r"$\sigma_{X}^{2},\sigma_{Y}^{2}$, and correlation $\rho$, find "
                        r"$E[Y|X=x]$ and $\operatorname{Var}(Y|X=x)$.",
        ("15.4", "problem", "15.12"): r"With prior $p\sim\mathrm{Beta}(1,1)$ and $k$ wins in $n$ "
                        r"trials, find the posterior distribution and $E[p\mid\mathrm{data}]$.",
        ("15.4", "problem", "15.13"): r"Find the expected number of fair coin tosses $E_{0}$ to "
                        r"see two consecutive Heads (HH).",
        ("15.4", "problem", "15.14"): r"Use $\ln u\leq u-1$ to prove $D_{\mathrm{KL}}(P\|Q)\geq 0$.",
        ("15.4", "problem", "15.15"): r"A symmetric $\pm 1$ random walk starts at 0. Find the "
                        r"probability $p$ of hitting $+A$ before $-B$ and $E[\tau]$.",
        ("15.4", "problem", "15.16"): r"For $X_{1},\ldots,X_{n}\sim\mathrm{Poisson}(\lambda)$, compute the "
                        r"Fisher information $I_{n}(\lambda)$ and verify that "
                        r"$\hat\lambda=\bar X$ achieves the CRLB.",
        ("15.4", "problem", "15.17"): r"With prior $p\sim\mathrm{Beta}(1,1)$ (uniform) and $k$ Heads "
                        r"in $n$ tosses, find the posterior distribution and posterior mean "
                        r"$E[p\mid k]$.",
        ("15.4", "problem", "15.18"): r"Prior $\mu\sim\mathcal{N}(\mu_{0},\tau_{0}^{-1})$ and likelihood "
                        r"$\bar X\mid\mu\sim\mathcal{N}(\mu,(n\tau)^{-1})$ have precisions "
                        r"$\tau_{0}$ and $n\tau$. State the posterior precision and mean.",
        ("15.4", "problem", "15.19"): r"If $(X,Y)$ is bivariate normal with means "
                        r"($\mu_{X},\mu_{Y}$), SDs ($\sigma_{X},\sigma_{Y}$), and correlation $\rho$, "
                        r"state $E[Y|X=x]$ and $\operatorname{Var}(Y|X=x)$.",
        ("15.4", "problem", "15.20"): r"Compute the mutual information $I(X;Y)=h(Y)-h(Y|X)$ "
                        r"for bivariate normal $(X,Y)$ with correlation $\rho$.",
        ("15.4", "problem", "15.21"): r"For a Student-t return distribution with $\nu>4$ degrees of "
                        r"freedom, excess kurtosis is $\frac{6}{\nu-4}$. Evaluate it for "
                        r"$\nu=5$ and $\nu=6$.",
        ("15.4", "problem", "15.22"): r"Verify detailed balance $\pi_{i}P_{ij}=\pi_{j}P_{ji}$ for a "
                        r"3-state chain with $P_{12}=0.4$, $P_{21}=0.2$ and find $\pi_{2}/\pi_{1}$.",
        ("15.4", "problem", "15.23"): r"For $Z\sim\mathcal{N}(0,1)$, compute $M_{Z^{2}}(t)=E[e^{tZ^{2}}]$ "
                        r"for $t<1/2$ and deduce $M_{\chi^{2}_{k}}(t)$.",
        ("15.4", "problem", "15.24"): r"If loss $L>x_{m}$ follows $P(L>x)=(x_{m}/x)^{\alpha}$ with "
                        r"$x_{m}=1M$ dollars and $\alpha=2$, find the 99% VaR ($P(L>\mathrm{VaR})=0.01$).",
        ("15.4", "problem", "15.25"): r"Compute $D_{\mathrm{KL}}(N(\mu_{1},\sigma_{1}^{2})\|N(\mu_{2},\sigma_{2}^{2}))$.",
        ("16.4", "problem", "16.1"): r"Find $\mu$, $L$, and $\kappa=L/\mu$ for $f(x,y)=2x^{2}+18y^{2}$.",
        ("16.4", "problem", "16.2"): r"Apply $S_{0.5}(w)$ to $w_{\mathrm{OLS}}=[2.4,-0.35,0.18,-1.5]^{T}$.",
        ("16.4", "problem", "16.3"): r"With $\beta_{1}=0.9$ and $g_{1}=10$, compute $m_{1}$ and bias-corrected "
                        r"$\hat m_{1}=\frac{m_{1}}{1-\beta_{1}^{1}}$.",
        ("16.4", "problem", "16.4"): r"Find total expected test MSE if Bias $=0.3$, Variance $=0.16$, and "
                        r"noise $\sigma=0.5$.",
        ("16.4", "problem", "16.5"): r"Find GMV weights $(w_{1},w_{2})$ for uncorrelated assets "
                        r"with $\sigma_{1}=10\%$, $\sigma_{2}=20\%$.",
        ("16.4", "problem", "16.6"): r"Prove $\eta^{*}=\frac{2}{L+\mu}$ minimizes "
                        r"$\max(|1-\eta\mu|,|1-\eta L|)$.",
        ("16.4", "problem", "16.7"): r"Minimize $\sum_{i=1}^{n}p_{i}\ln(p_{i}/q_{i})$ subject to "
                        r"$\sum_{i=1}^{n}p_{i}=1$.",
        ("16.4", "problem", "16.8"): r"Find optimal Kelly fraction $f^{*}$ for a $3:1$ payoff ($b=3$) "
                        r"with win probability $p=0.35$.",
        ("16.4", "problem", "16.9"): r"Find $N$ so that $P(|\hat p-p|\geq 0.02)\leq 0.05$.",
        ("16.4", "problem", "16.10"): r"Prove the perpendicular distance between $w^{T}x+b=+1$ and "
                        r"$w^{T}x+b=-1$ is $\frac{2}{\|w\|_{2}}$.",
        ("16.4", "problem", "16.11"): r"Prove Newton's step $x_{t+1}=x_{t}-(\nabla^{2}f)^{-1}\nabla f$ "
                        r"is invariant under any invertible linear reparameterization $x=Ay$.",
        ("16.4", "problem", "16.12"): r"Derive $S_{\lambda}(w_{0})$ from $0\in w-w_{0}+\lambda\partial|w|$.",
        ("16.4", "problem", "16.13"): r"Prove that combining $BR$ independent signals "
                        r"with correlation $\mathrm{IC}$ yields Information Ratio "
                        r"$\mathrm{IR}=\mathrm{IC}\sqrt{BR}$.",
        ("16.4", "problem", "16.14"): r"Why does averaging the last $T$ noisy SGD iterates "
                        r"$\bar w_{T}=\frac{1}{T}\sum_{t=1}^{T}w_{t}$ reduce variance from "
                        r"$O(\eta)$ to $O(1/T)$?",
        ("16.4", "problem", "16.15"): r"Compute $f^{*}(y)=\sup_{x}y^{T}x-\frac{1}{2}x^{T}\Sigma x$ "
                        r"for $\Sigma\succ 0$.",
        ("16.4", "problem", "16.16"): r"Minimize $\frac{1}{2}x^{T}\Sigma x$ subject to $Ax=b$ "
                        r"($\Sigma\succ 0$) via Lagrange multipliers $\nu$.",
        ("16.4", "problem", "16.17"): r"For $L_{i}(w)=\max(0,1-y_{i}w^{T}x_{i})$, find "
                        r"$\nabla_{w}L_{i}(w)$ when $y_{i}w^{T}x_{i}<1$ and when "
                        r"$y_{i}w^{T}x_{i}>1$.",
        ("16.4", "problem", "16.18"): r"With optimal fixed step size $\eta=\frac{2}{L+\mu}$, "
                        r"contraction factor is $\frac{\kappa-1}{\kappa+1}\approx 1-\frac{2}{\kappa}$. "
                        r"How many steps does Nesterov acceleration save when $\kappa=10{,}000$?",
        ("16.4", "problem", "16.19"): r"If Asset 1 has volatility $\sigma_{1}=10\%$ and Asset 2 "
                        r"has $\sigma_{2}=20\%$ (for any correlation $\rho$), find the long-only "
                        r"Risk Parity weights $w_{1},w_{2}$ ($w_{1}+w_{2}=1$).",
        ("16.4", "problem", "16.20"): r"Minimize $\frac{1}{2}(w-z)^{2}+\lambda_{1}|w|+\frac{1}{2}\lambda_{2}w^{2}$. "
                        r"Show that the solution is scaled soft-thresholding.",
        ("16.4", "problem", "16.21"): r"Explain how projecting $v\in\mathbb{R}^{K}$ onto "
                        r"$\{w\geq 0:\mathbf{1}^{T}w=1\}$ reduces to finding a single scalar "
                        r"threshold $\theta$ such that $\sum_{i=1}^{K}\max(v_{i}-\theta,0)=1$.",
        ("16.4", "problem", "16.22"): r"In parameter space with Riemannian Fisher metric $F(\theta)$, "
                        r"what is the steepest descent direction minimizing "
                        r"$d\theta^{T}\nabla L(\theta)$ subject to "
                        r"$d\theta^{T}F(\theta)d\theta=\epsilon^{2}$?",
        ("16.4", "problem", "16.23"): r"Maximize $w^{T}\alpha-\frac{\lambda}{2}w^{T}\Sigma w-"
                        r"\frac{\tau}{2}\|w-w_{0}\|_{2}^{2}$. Find $w^{*}$.",
        ("16.4", "problem", "16.24"): r"Minimize $c^{T}x-\mu\sum_{i=1}^{n}\ln x_{i}$ for $c>0$, "
                        r"$\mu>0$. Find the central path $x^{*}(\mu)$ and verify "
                        r"$x_{i}^{*}c_{i}=\mu$.",
        ("16.4", "problem", "16.25"): r"For continuous return $dW/W=(r+f(\mu-r))dt+f\sigma dB_{t}$, "
                        r"growth rate is $g(f)=r+f(\mu-r)-\frac{1}{2}f^{2}\sigma^{2}$. Show that "
                        r"Half-Kelly ($f=f^{*}/2$) captures 75% of the maximum excess growth rate "
                        r"with only 50% of the volatility!",
        ("21.4", "problem", "21.2"): r"Find the long-run volatility $\sqrt{\theta}$ for "
                         r"$dv_{t}=4(0.09-v_{t})dt+0.3\sqrt{v_{t}}\,dW_{t}$.",
    }
    for c in chapters:
        for s in c["sections"]:
            for b in s["blocks"]:
                if b.get("type") in ("example", "problem", "exam"):
                    txt = statement_fixes.get((s["num"], b.get("type"), b.get("num")))
                    if txt:
                        b["statement"] = md_runs(txt)

    # Curated solution rewrites: the PDF parser leaves many graded solutions
    # as boilerplate plus fragmented display rows (empty radicals, split
    # fractions). Replace the whole child sequence after a problem/example
    # with one concise derivation, preserving the (already curated)
    # statement above it.
    solution_fixes = {
    }
    solution_fixes.update({
        ("15.4", "problem", "15.1"): r"$E[X]=0.6(300)-0.4(200)=100$ and $E[X^{2}]=0.6(90000)+0.4(40000)=70000$, so $\operatorname{Var}(X)=70000-100^{2}=60000$ and $\sigma_{X}=\sqrt{60000}\approx244.95$.",
        ("15.4", "problem", "15.2"): r"For a Poisson count with mean $\lambda t=3$, $P(K=0)=e^{-3}3^{0}/0!=e^{-3}\approx0.0498$.",
        ("15.4", "problem", "15.3"): r"$E[X]=0$ and $E[XY]=E[X^{3}]=E[X]=0$, so $\operatorname{Cov}(X,Y)=E[XY]-E[X]E[Y]=0$, even though $Y=X^{2}$ is a function of $X$.",
        ("15.4", "problem", "15.4"): r"Daily Sharpe is $0.05/1.0=0.05$, so annualized Sharpe is $\sqrt{252}\times0.05\approx0.794$.",
        ("15.4", "problem", "15.5"): r"For $X\sim t_{\nu}$ with $\nu>2$, $\operatorname{Var}(X)=\nu/(\nu-2)$. With $\nu=4$, $\operatorname{Var}(X)=4/2=2$ and $\sigma=\sqrt{2}\approx1.414$.",
        ("15.4", "problem", "15.6"): r"By Bayes, $P(A\mid +)=\frac{0.90\times0.02}{0.90\times0.02+0.09\times0.98}=\frac{0.018}{0.1062}\approx0.1695$.",
        ("15.4", "problem", "15.7"): r"$\operatorname{Var}(\bar X)=\frac{\sigma^{2}}{n}+\frac{n-1}{n}\rho\sigma^{2}$, which tends to $\rho\sigma^{2}$ as $n\to\infty$ (non-diversifiable systematic variance).",
        ("15.4", "problem", "15.8"): r"The log-likelihood is $\ell(\lambda)=n\ln\lambda-\lambda\sum_{i}t_{i}$. Setting $\ell'(\lambda)=n/\lambda-\sum_{i}t_{i}=0$ gives $\hat\lambda_{\mathrm{MLE}}=n/\sum_{i}t_{i}=1/\bar t$.",
        ("15.4", "problem", "15.10"): r"$D_{\mathrm{KL}}(p\|q)=E_{p}[\ln p-\ln q]$. For $p=\mathcal{N}(\mu,\sigma^{2})$ and $q=\mathcal{N}(0,1)$ this evaluates to $\frac{1}{2}(\mu^{2}+\sigma^{2}-1-\ln\sigma^{2})$.",
        ("15.4", "problem", "15.11"): r"Writing $Y=\rho\frac{\sigma_{Y}}{\sigma_{X}}X+\epsilon$ with $\epsilon\perp X$ gives $E[Y\mid X=x]=\rho\frac{\sigma_{Y}}{\sigma_{X}}x$ and $\operatorname{Var}(Y\mid X=x)=(1-\rho^{2})\sigma_{Y}^{2}$.",
        ("15.4", "problem", "15.12"): r"The Beta prior is conjugate to the binomial likelihood, so the posterior is $\mathrm{Beta}(k+1,n-k+1)$ with mean $E[p\mid\mathrm{data}]=(k+1)/(n+2)$.",
        ("15.4", "problem", "15.13"): r"Let $E_{0}$ be the mean wait from no partial match and $E_{1}$ from one Head showing. Then $E_{0}=1+\frac{1}{2}E_{0}+\frac{1}{2}E_{1}$ and $E_{1}=1+\frac{1}{2}E_{0}$, giving $E_{0}=6$ tosses.",
        ("15.4", "problem", "15.14"): r"Since $\ln u\leq u-1$ with equality only at $u=1$, $D_{\mathrm{KL}}(P\|Q)=E_{P}[-\ln(Q/P)]\geq E_{P}[1-Q/P]=0$.",
        ("15.4", "problem", "15.15"): r"Optional stopping on $S_{t}$ gives $pA+(1-p)(-B)=0$, so $p=B/(A+B)$. Optional stopping on $S_{t}^{2}-t$ gives $E[\tau]=AB$.",
        ("15.4", "problem", "15.16"): r"$\ln p(x;\lambda)=-\lambda+x\ln\lambda-\ln(x!)$, so $-\partial^{2}\ln p/\partial\lambda^{2}=x/\lambda^{2}$ and $I_{n}(\lambda)=n/\lambda$. Since $\operatorname{Var}(\bar X)=\lambda/n=I_{n}(\lambda)^{-1}$, $\bar X$ is efficient.",
        ("15.4", "problem", "15.17"): r"The posterior is $\mathrm{Beta}(k+1,n-k+1)$ with mean $(k+1)/(n+2)$ (Laplace's rule of succession).",
        ("15.4", "problem", "15.18"): r"Posterior precision is $\tau_{0}+n\tau$ and posterior mean is the precision-weighted average $(\tau_{0}\mu_{0}+n\tau\bar X)/(\tau_{0}+n\tau)$.",
        ("15.4", "problem", "15.19"): r"$E[Y\mid X=x]=\mu_{Y}+\rho\frac{\sigma_{Y}}{\sigma_{X}}(x-\mu_{X})$ and $\operatorname{Var}(Y\mid X=x)=(1-\rho^{2})\sigma_{Y}^{2}$.",
        ("15.4", "problem", "15.20"): r"Since $\operatorname{Var}(Y\mid X)=(1-\rho^{2})\sigma_{Y}^{2}$, $I(X;Y)=h(Y)-h(Y\mid X)=-\frac{1}{2}\ln(1-\rho^{2})$ nats.",
        ("15.4", "problem", "15.21"): r"Excess kurtosis is $6/(\nu-4)$. For $\nu=5$ it is $6$ (total kurtosis $9$); for $\nu=6$ it is $3$ (total kurtosis $6$).",
        ("15.4", "problem", "15.22"): r"Detailed balance $\pi_{1}P_{12}=\pi_{2}P_{21}$ gives $\pi_{2}/\pi_{1}=P_{12}/P_{21}=0.4/0.2=2$.",
        ("15.4", "problem", "15.23"): r"$M_{Z^{2}}(t)=\int_{-\infty}^{\infty}e^{tz^{2}}\phi(z)dz=(1-2t)^{-1/2}$ for $t<1/2$. For $k$ independent squares, $M_{\chi^{2}_{k}}(t)=(1-2t)^{-k/2}$.",
        ("15.4", "problem", "15.24"): r"Setting $(x_{m}/\mathrm{VaR})^{\alpha}=0.01$ with $x_{m}=1$M and $\alpha=2$ gives $\mathrm{VaR}=x_{m}/\sqrt{0.01}=10$M.",
        ("15.4", "problem", "15.25"): r"$D_{\mathrm{KL}}(\mathcal{N}(\mu_{1},\sigma_{1}^{2})\|\mathcal{N}(\mu_{2},\sigma_{2}^{2}))=\ln\frac{\sigma_{2}}{\sigma_{1}}+\frac{\sigma_{1}^{2}+(\mu_{1}-\mu_{2})^{2}}{2\sigma_{2}^{2}}-\frac{1}{2}$.",
    })
    solution_fixes.update({
        ("2.5", "problem", "2.3"): r"Let $(x+iy)^{2}=-7-24i$. Then $x^{2}-y^{2}=-7$, $2xy=-24$, and $x^{2}+y^{2}=|z|=25$. Solving gives $x^{2}=9$, $y^{2}=16$ with $xy=-12$, so the roots are $3-4i$ and $-3+4i$.",
        ("2.5", "problem", "2.4"): r"$|z|=\sqrt{(-1)^{2}+(-\sqrt{3})^{2}}=2$ and the reference angle is $\arctan(\sqrt{3})= \pi/3$. Since $z$ is in Quadrant III, $\operatorname{Arg}(z)=-\pi+\pi/3=-2\pi/3$. Hence $z=2[\cos(-2\pi/3)+i\sin(-2\pi/3)]=2e^{-2\pi i/3}$.",
        ("2.5", "problem", "2.6"): r"By Vieta, the product of the roots is $k/5$. Reciprocal roots have product $1$, so $k/5=1$ and $k=5$. Then $D=13^{2}-4(5)(5)=69>0$, giving two distinct real roots.",
        ("2.5", "problem", "2.8"): r"If $k=0$, $f(x)=-4x$ is not always positive; if $k<0$, $f(x)\to-\infty$. For $k>0$ the minimum at $x^{*}=2/k$ is $f_{\min}=k-4/k$. Requiring $f_{\min}>0$ gives $(k^{2}-4)/k>0$, so $k>2$.",
        ("2.5", "problem", "2.11"): r"Writing $z=x+iy$, $|z-2|=3|z+2|$ gives $(x-2)^{2}+y^{2}=9[(x+2)^{2}+y^{2}]$, i.e. $x^{2}+y^{2}+5x+4=0$. This is $(x+5/2)^{2}+y^{2}=(3/2)^{2}$, a circle of radius $3/2$ centered at $(-5/2,0)$.",
        ("2.5", "problem", "2.15"): r"Setting $(x^{2}-bc)/(2x-b-c)=y$ gives $x^{2}-2yx+y(b+c)-bc=0$. Its discriminant is $4(y-b)(y-c)$, so real $x$ requires $(y-b)(y-c)\geq0$. Hence $y$ takes all values except the open interval strictly between $b$ and $c$.",
        ("2.5", "problem", "2.18"): r"Since $z^{n}-1=(z-1)\prod_{k=1}^{n-1}(z-\zeta_{k})$, dividing by $z-1$ gives $1+z+\cdots+z^{n-1}=\prod_{k=1}^{n-1}(z-\zeta_{k})$. Evaluating at $z=1$ yields $\prod_{k=1}^{n-1}(1-\zeta_{k})=n$.",
        ("2.5", "problem", "2.23"): r"In the complex-conjugate regime $r_{2}=\bar r_{1}$ and $r_{1}r_{2}=\beta$ by Vieta, so $|r|^{2}=r_{1}\bar r_{1}=\beta$ and $|r|=\sqrt{\beta}$.",
        ("2.5", "problem", "2.26"): r"At $u=-i$, $iu+u^{2}=i(-i)+(-i)^{2}=1-1=0$, so $d=\sqrt{(\kappa)^{2}+0}=2$.",
        ("2.5", "problem", "2.28"): r"We need $-2\leq2w^{2}-5w+1\leq2$. The left inequality gives $(w-1)(2w-3)\geq0$, i.e. $w\leq1$ or $w\geq1.5$. The right gives $2w^{2}-5w-1\leq0$, i.e. $w\in[(5-\sqrt{33})/4,(5+\sqrt{33})/4]$. Intersecting gives $[(5-\sqrt{33})/4,1]\cup[1.5,(5+\sqrt{33})/4]$.",
        ("2.5", "problem", "2.29"): r"$C(\sigma)=40\sigma-2\sigma^{2}\geq7.5$ becomes $2\sigma^{2}-40\sigma+7.5\leq0$, with roots $(20\pm\sqrt{385})/2$. Hence $\sigma\in[(20-\sqrt{385})/2,(20+\sqrt{385})/2]\approx[0.189,19.81]$, which within $(0,5)$ is $[0.189,5)$.",
    })
    solution_fixes.update({
        ("1.6", "problem", "1.6"): r"We need $9-x^{2}>0$ for the radical, so $x\in(-3,3)$, and $x-1>0$ for the logarithm, so $x>1$. Intersecting gives domain $(1,3)$.",
        ("1.6", "problem", "1.11"): r"$f(-x)+f(x)=\ln(-x+\sqrt{x^{2}+1})+\ln(x+\sqrt{x^{2}+1})=\ln[( \sqrt{x^{2}+1})^{2}-x^{2}]=\ln1=0$, so $f(-x)=-f(x)$ and $f$ is odd.",
        ("1.6", "problem", "1.19"): r"By induction $f(k)=f(1)^{k}=3^{k}$. The geometric sum $\sum_{k=1}^{n}3^{k}=(3^{n+1}-3)/2=363$ gives $3^{n+1}=729=3^{6}$, so $n=5$.",
        ("1.6", "problem", "1.20"): r"Working inside out: $1-x^{2}\geq0$ gives $x\in[-1,1]$. For such $x$, $1-x^{2}\in[0,1]$, so its square root is in $[0,1]$, and $1$ minus that is again in $[0,1]$. Hence all radicands are nonnegative and the domain is $[-1,1]$.",
        ("1.6", "problem", "1.27"): r"The even part is $f_{e}(x)=\frac{f(x)+f(-x)}{2}=\frac{e^{x}+e^{-x}}{2}=\cosh x$ and the odd part is $f_{o}(x)=\frac{f(x)-f(-x)}{2}=\frac{e^{x}-e^{-x}}{2}=\sinh x$.",
        ("1.6", "problem", "1.28"): r"As $U$ ranges over $(0,1]$, $\ln U$ ranges over $(-\infty,0]$, so $-2\ln U$ ranges over $[0,\infty)$ and $R=\sqrt{-2\ln U}$ ranges over $[0,\infty)$.",
    })
    solution_fixes.update({
        ("3.4", "problem", "3.10"): r"The common difference is $d=(31-1)/(m+1)=30/(m+1)$ and the $k$-th mean is $1+kd$. The ratio $(1+7d)/(1+(m-1)d)=5/9$ gives $m=14$ (then $d=2$, means $15$ and $27$).",
        ("3.4", "problem", "3.15"): r"By the multinomial theorem the coefficient is $\frac{9!}{3!2!4!}2^{3}(-1)^{2}3^{4}=1260\times8\times81=816480$.",
        ("3.4", "problem", "3.16"): r"Write $r\binom{n}{r}=n\binom{n-1}{r-1}$. Then $\sum_{r}r\binom{n}{r}^{2}=n\sum_{r}\binom{n-1}{r-1}\binom{n}{n-r}=n\binom{2n-1}{n}$ by Vandermonde.",
        ("3.4", "problem", "3.23"): r"The price is a geometric series with first term $D_{1}/(1+r)$ and ratio $(1+g)/(1+r)<1$, so $P_{0}=\frac{D_{1}/(1+r)}{1-(1+g)/(1+r)}=D_{1}/(r-g)=4/0.04=100$.",
        ("3.4", "problem", "3.24"): r"With $v=1/(1+y)$, price is proportional to $\sum_{t\geq1}v^{t}=v/(1-v)$ and the weighted sum is $\sum_{t\geq1}tv^{t}=v/(1-v)^{2}$. Their ratio, the Macaulay duration, is $1/(1-v)=(1+y)/y$.",
        ("3.4", "problem", "3.26"): r"By the arithmetico-geometric series, $E[k]=(1-\beta)\sum_{k\geq0}k\beta^{k}=(1-\beta)\beta/(1-\beta)^{2}=\beta/(1-\beta)=0.99/0.01=99$ steps.",
        ("4.3", "problem", "4.3"): r"Since $A^{T}=A$ and $B^{T}=B$, $(AB-BA)^{T}=BA-AB=-(AB-BA)$ (skew-symmetric) and $(AB+BA)^{T}=BA+AB=AB+BA$ (symmetric).",
        ("4.3", "problem", "4.7"): r"$\det A=2\cdot3-5\cdot1=1$, so $A^{-1}=\begin{pmatrix}3&-5\\-1&2\end{pmatrix}$. Then $(x,y)^{T}=A^{-1}(1,2)^{T}=(-7,3)^{T}$.",
        ("4.3", "problem", "4.8"): r"$\det(-2A^{2})=(-2)^{3}\det(A)^{2}=(-8)(-3)^{2}=-72$.",
        ("4.3", "problem", "4.15"): r"Try $I+cP$: $(I+P)(I+cP)=I+(1+2c)P$ using $P^{2}=P$. Setting $1+2c=0$ gives $c=-1/2$, so $(I+P)^{-1}=I-\frac{1}{2}P$.",
        ("4.3", "problem", "4.19"): r"For $3\times3$ matrices, $\det\operatorname{adj}(M)=\det(M)^{2}$. Hence $|\operatorname{adj}(AB)|=|\det(AB)|^{2}=(3\cdot5)^{2}=225$, and $\det(\operatorname{adj}(A)\operatorname{adj}(B))=3^{2}\cdot5^{2}=225$.",
        ("4.3", "problem", "4.21"): r"$H^{T}=H$ by symmetry of $(X^{T}X)^{-1}$, and $H^{2}=H$ by direct multiplication. By cyclic trace, $\operatorname{Tr}(H)=\operatorname{Tr}((X^{T}X)^{-1}X^{T}X)=\operatorname{Tr}(I_{p})=p$.",
        ("4.3", "problem", "4.29"): r"The Jacobian is lower-triangular, $J=\begin{pmatrix}1&0\\\partial_{x_{1}}[\cdot]&e^{s(x_{1})}\end{pmatrix}$, so $\det(J)=e^{s(x_{1})}$ in $O(1)$ time.",
    })
    solution_fixes.update({
        ("5.5", "problem", "5.2"): r"Rewrite the first line as $6x-8y+18=0$. The distance between parallel lines is $|18-(-15)|/\sqrt{6^{2}+(-8)^{2}}=33/10=3.3$.",
        ("5.5", "problem", "5.4"): r"The pencil is $(x+2y-3)+\lambda(2x-y+4)=0$, i.e. $(1+2\lambda)x+(2-\lambda)y+(-3+4\lambda)=0$ with slope $-(1+2\lambda)/(2-\lambda)$. Setting this to $3$ gives $\lambda=7$, hence $15x-5y+25=0$ or $3x-y+5=0$.",
        ("5.5", "problem", "5.5"): r"A circle on diameter $(1,2)$--$(5,6)$ satisfies $(x-1)(x-5)+(y-2)(y-6)=0$, i.e. $x^{2}+y^{2}-6x-8y+17=0$, with center $(3,4)$ and radius $\sqrt{8}=2\sqrt{2}$.",
        ("5.5", "problem", "5.6"): r"The distance from $(0,0)$ to $mx-y+c=0$ is $|c|/\sqrt{m^{2}+1}$. Tangency requires this to equal $r$, so $c=\pm r\sqrt{m^{2}+1}$.",
        ("5.5", "problem", "5.11"): r"Parametrize as $(1+r\cos60^{\circ},2+r\sin60^{\circ})=(1+r/2,2+r\sqrt{3}/2)$. Imposing $x+y=6$ gives $3+r(1+\sqrt{3})/2=6$, so $r=6/(1+\sqrt{3})=3(\sqrt{3}-1)$.",
        ("5.5", "problem", "5.13"): r"Here $a=12$, $h=-5$, $b=2$, $g=11/2$, $f=-5/2$, $c=\lambda$. The pair-of-lines condition $abc+2fgh-af^{2}-bg^{2}-ch^{2}=0$ gives $-\lambda+2=0$, so $\lambda=2$. The angle satisfies $\tan\theta=2\sqrt{h^{2}-ab}/(a+b)=2/14=1/7$.",
        ("5.5", "problem", "5.15"): r"Subtracting the circles gives $-4x+4y=0$, i.e. $y-x=0$. The first circle has center $(2,0)$ and radius $2$; its distance to the chord is $\sqrt{2}$, so the half-chord is $\sqrt{4-2}=\sqrt{2}$ and the common chord length is $2\sqrt{2}$.",
        ("5.5", "problem", "5.23"): r"Completing the square, $\sigma_{p}^{2}=A(\mu_{p}-B/A)^{2}+(AC-B^{2})/A$, i.e. $\sigma_{p}^{2}-A(\mu_{p}-B/A)^{2}=(AC-B^{2})/A$, a hyperbola in $(\sigma_{p},\mu_{p})$ space with minimum-variance vertex $\mu_{p}=B/A$, $\sigma_{p,\min}^{2}=(AC-B^{2})/A$.",
        ("6.5", "problem", "6.4"): r"$y'=(1-x^{2})^{-1/2}$, so $(1-x^{2})(y')^{2}=1$. Differentiating gives $(1-x^{2})2y'y''-2x(y')^{2}=0$, hence $(1-x^{2})y''-xy'=0$.",
        ("6.5", "problem", "6.10"): r"$f'(x)=(1-\ln x)/x^{2}=0$ at $x=e$, and $f$ increases before $e$ and decreases after, so $x=e$ is the global maximum. Since $\pi>e$ and $f$ is decreasing on $(e,\infty)$, $\ln\pi/\pi<\ln e/e$, i.e. $e^{\pi}>\pi^{e}$.",
        ("6.5", "problem", "6.12"): r"$f'(x)=6x^{2}-30x+36=6(x-2)(x-3)$, so critical points are $2,3$. Comparing $f(1)=24$, $f(2)=29$, $f(3)=28$, $f(5)=56$, the absolute minimum is $24$ at $x=1$ and the absolute maximum is $56$ at $x=5$.",
    })
    solution_fixes.update({
        ("7.3", "problem", "7.5"): r"$x^{3}-x=x(x-1)(x+1)$ is $\geq0$ on $[-1,0]$, $\leq0$ on $[0,1]$ and $\geq0$ on $[1,2]$. With antiderivative $x^{4}/4-x^{2}/2$, the three absolute pieces are $1/4$, $1/4$ and $9/4$, totaling $11/4$.",
        ("7.3", "problem", "7.11"): r"$T(t)-20=80e^{-kt}$. At $t=10$, $40=80e^{-10k}$ so $e^{-10k}=1/2$. At $t=20$, $T-20=80(1/2)^{2}=20$, hence $T(20)=40$.",
        ("7.3", "problem", "7.16"): r"$|\sin x|$ has period $\pi$ with $\int_{0}^{\pi}|\sin x|dx=2$. Over $0$ to $100\pi$ there are $100$ periods, so the integral is $200$.",
        ("7.3", "problem", "7.17"): r"For small $x$, $\int_{0}^{x^{2}}\sin t\,dt=x^{2}+O(x^{6})$, so its square root is $|x|+O(|x|^{5})$. Hence the ratio is $1/x^{2}+O(1)$ for $x>0$ and tends to $+\infty$; the two-sided finite limit does not exist.",
        ("7.3", "problem", "7.20"): r"Here $M=2xy+y^{2}$ and $N=x^{2}+2xy$ satisfy $\partial M/\partial y=\partial N/\partial x=2x+2y$, so the equation is exact. A potential is $F=x^{2}y+xy^{2}$, and $dF=0$ gives $x^{2}y+xy^{2}=C$.",
        ("7.3", "problem", "7.22"): r"Integration by parts with $u=x^{\alpha}$, $dv=e^{-x}dx$ gives $\Gamma(\alpha+1)=[-x^{\alpha}e^{-x}]_{0}^{\infty}+\alpha\int_{0}^{\infty}x^{\alpha-1}e^{-x}dx=\alpha\Gamma(\alpha)$. Substituting $x=z^{2}/2$ in $\Gamma(1/2)$ reduces it to the Gaussian integral $\sqrt{\pi}$.",
        ("7.3", "problem", "7.24"): r"$\int_{z_{\alpha}}^{\infty}z\phi(z)dz=\frac{1}{\sqrt{2\pi}}\int_{z_{\alpha}}^{\infty}ze^{-z^{2}/2}dz=\phi(z_{\alpha})$. Dividing by $P(Z>z_{\alpha})=1-\alpha$ gives $E[Z\mid Z>z_{\alpha}]=\phi(z_{\alpha})/(1-\alpha)$.",
        ("8.4", "problem", "8.3"): r"Using $15^{\circ}=45^{\circ}-30^{\circ}$, $\sin15^{\circ}=(\sqrt{6}-\sqrt{2})/4$, $\cos15^{\circ}=(\sqrt{6}+\sqrt{2})/4$, and $\tan15^{\circ}=2-\sqrt{3}$.",
        ("8.4", "problem", "8.4"): r"$3\cos\theta+4\sin\theta$ has amplitude $\sqrt{3^{2}+4^{2}}=5$, so it ranges over $[-5,5]$. Adding $8$ gives minimum $3$ and maximum $13$.",
        ("8.4", "problem", "8.6"): r"$\tan(A+B)=1$ gives $\frac{\tan A+\tan B}{1-\tan A\tan B}=1$, i.e. $\tan A+\tan B+\tan A\tan B=1$, so $(1+\tan A)(1+\tan B)=2$. With $A=B=22.5^{\circ}$, $(1+\tan22.5^{\circ})^{2}=2$, hence $\tan22.5^{\circ}=\sqrt{2}-1$.",
        ("8.4", "problem", "8.8"): r"$\arcsin(-1/2)=-\pi/6$, $\arccos(-1/2)=2\pi/3$, $\arctan(-1)=-\pi/4$ and $\operatorname{arccot}(-1)=3\pi/4$. Their sum is $(-2+8-3+9)\pi/12=\pi$.",
        ("8.4", "problem", "8.9"): r"$\arctan\frac{1}{2}+\arctan\frac{1}{5}=\arctan\frac{7/10}{1-1/10}=\arctan\frac{7}{9}$. Adding $\arctan\frac{1}{8}$ gives $\arctan\frac{7/9+1/8}{1-7/72}=\arctan1=\pi/4$.",
        ("8.4", "problem", "8.10"): r"By half-angle formulas, $\sqrt{\frac{1-\cos x}{1+\cos x}}=\tan(x/2)$ for $x\in(0,\pi)$. Hence $\arctan\sqrt{\frac{1-\cos x}{1+\cos x}}=x/2$.",
        ("8.4", "problem", "8.11"): r"Using $\cos^{2}u=(1+\cos2u)/2$, the sum is $3/2+\frac{1}{2}[\cos2\theta+\cos(2\theta+120^{\circ})+\cos(2\theta-120^{\circ})]=3/2+\frac{1}{2}[\cos2\theta+2\cos2\theta\cos120^{\circ}]=3/2$.",
        ("8.4", "problem", "8.15"): r"Let $u=\arcsin x\in[-\pi/2,\pi/2]$, so $\arccos x=\pi/2-u$ and $S=u^{3}+(\pi/2-u)^{3}=(\pi/2)^{3}-3u(\pi/2-u)(\pi/2)$. This is minimized at $u=\pi/4$ with value $\pi^{3}/32$ and maximized at the endpoints with value $\pi^{3}/8$.",
        ("8.4", "problem", "8.25"): r"$F(x)=\frac{1}{2}+\frac{1}{\pi}\arctan x$. Setting $F=0.75$ gives $Q_{0.75}=1$ and $F=0.25$ gives $Q_{0.25}=-1$, so the interquartile range is $2$.",
    })
    solution_fixes.update({
        ("9.4", "problem", "9.2"): r"$a\cdot b=2+6+2=10$ and $|b|=\sqrt{6}$. Scalar projection is $10/\sqrt{6}=5\sqrt{6}/3$ and vector projection is $\frac{10}{6}(1,2,1)=(5/3,10/3,5/3)$.",
        ("9.4", "problem", "9.3"): r"$a\times b=(-4,4,4)$ with magnitude $\sqrt{48}=4\sqrt{3}$. A unit vector is $\pm(-1,1,1)/\sqrt{3}$.",
        ("9.4", "problem", "9.4"): r"$AB=(0,1,2)$ and $AC=(1,2,0)$, so $AB\times AC=(-4,2,-1)$ with magnitude $\sqrt{21}$. The area is $\sqrt{21}/2$.",
        ("9.4", "problem", "9.5"): r"Coplanarity means the scalar triple product vanishes: $\det\begin{pmatrix}2&-1&1\\1&2&-3\\3&\lambda&5\end{pmatrix}=7\lambda+28=0$, so $\lambda=-4$.",
        ("9.4", "problem", "9.6"): r"Direction vectors are $(2,5,-3)$ and $(-1,8,4)$ with dot product $-2+40-12=26$. Hence $\cos\theta=26/(\sqrt{38}\times9)=26/(9\sqrt{38})$.",
        ("9.4", "problem", "9.7"): r"$d=|6(2)-3(5)+2(-3)-4|/\sqrt{36+9+4}=|-13|/7=13/7$.",
        ("9.4", "problem", "9.17"): r"Parametrize as $(2+3t,-1+4t,2+12t)$. Imposing $x-y+z=5$ gives $5+11t=5$, so $t=0$ and $P=(2,-1,2)$. Its distance to $(-1,-5,-10)$ is $\sqrt{3^{2}+4^{2}+12^{2}}=13$.",
        ("9.4", "problem", "9.23"): r"Novikoff's bound is $(R/\gamma)^{2}=(4/0.5)^{2}=64$ updates.",
        ("9.4", "problem", "9.24"): r"Solving $D^{T}\psi=p$ gives $1.1\psi_{1}+1.1\psi_{2}=1$ and $1.3\psi_{1}+0.9\psi_{2}=1$, so $\psi_{1}=\psi_{2}=5/11>0$. Positive state prices certify no arbitrage.",
        ("9.4", "problem", "9.26"): r"$|n|=3$ and $|l|=\sqrt{9+16+144}=13$. Hence $I=\hat n\cdot\hat l=(3+8+24)/(3\times13)=35/39$.",
        ("10.3", "problem", "10.6"): r"Conditioning on black $=5$ leaves $6$ equally likely red outcomes, of which $(5,5)$ and $(5,6)$ have sum $>9$. The conditional probability is $2/6=1/3$.",
        ("10.3", "problem", "10.9"): r"For $\mathrm{Bin}(n,p)$, $np=4$ and $np(1-p)=3$, so $1-p=3/4$, $p=1/4$ and $n=16$. Then $P(X\geq1)=1-(3/4)^{16}\approx0.99$.",
        ("10.3", "problem", "10.26"): r"$p^{*}=(1.05-0.90)/(1.20-0.90)=0.5$. Call payoffs are $15$ (up) and $0$ (down), so $C_{0}=0.5(15)/1.05\approx7.14$.",
        ("10.3", "problem", "10.29"): r"Annualized mean is $252\times0.05\%$ and annualized volatility is $\sqrt{252}\times1.0\%$, so Sharpe $=\sqrt{252}\times0.05\approx0.794$.",
        ("10.3", "problem", "10.30"): r"$\mathrm{IR}=0.05\times\sqrt{400}=0.05\times20=1.00$.",
    })
    solution_fixes.update({
        ("11.5", "problem", "11.5"): r"$1+i=\sqrt{2}e^{i\pi/4}$, so $(1+i)^{8}=(\sqrt{2})^{8}e^{i8\pi/4}=16e^{i2\pi}=16$.",
        ("11.5", "problem", "11.7"): r"$\zeta(x)-\zeta(-x)=\ln\frac{1+e^{x}}{1+e^{-x}}=\ln e^{x}=x$. The overflow-safe form is $\zeta(x)=\max(0,x)+\ln(1+e^{-|x|})$.",
        ("11.5", "problem", "11.8"): r"Partial fractions give $\frac{1}{n(n+2)}=\frac{1}{2}(\frac{1}{n}-\frac{1}{n+2})$. The sum telescopes to $\frac{1}{2}[1+\frac{1}{2}]=\frac{3}{4}$.",
        ("11.5", "problem", "11.11"): r"By Cauchy-Schwarz, $w^{T}s\leq\|w\|_{2}\|s\|_{2}$ with equality at $w\propto s$. Hence the maximum is $\|s\|_{2}=\sqrt{0.36+0.64+1}=\sqrt{2}\approx1.414$.",
        ("11.5", "problem", "11.20"): r"$C=\begin{pmatrix}0&1&0\\0&0&1\\-a_{0}&-a_{1}&-a_{2}\end{pmatrix}$, whose characteristic polynomial is $\lambda^{3}+a_{2}\lambda^{2}+a_{1}\lambda+a_{0}$.",
        ("11.5", "problem", "11.23"): r"The normalized DFT matrix $F_{kn}=\frac{1}{\sqrt{N}}e^{-i2\pi kn/N}$ is unitary ($F^{*}F=I$), so $\|Fx\|_{2}^{2}=x^{*}F^{*}Fx=\|x\|_{2}^{2}$, i.e. $\sum_{k}|X_{k}|^{2}=\sum_{n}|x_{n}|^{2}$. This is Parseval's identity.",
        ("11.5", "problem", "11.24"): r"Squaring both nonnegative sides, $\sqrt{q_{1}+q_{2}}\leq\sqrt{q_{1}}+\sqrt{q_{2}}$ becomes $q_{1}+q_{2}\leq q_{1}+q_{2}+2\sqrt{q_{1}q_{2}}$, true for $q_{1},q_{2}\geq0$.",
        ("12.4", "problem", "12.1"): r"$f'(x)=2xe^{-3x}-3x^{2}e^{-3x}=x(2-3x)e^{-3x}$, so $f'(x)=0$ at $x=0$ and $x=2/3$.",
        ("12.4", "problem", "12.2"): r"Since $e^{2x}=1+2x+2x^{2}+O(x^{3})$, the numerator is $2x^{2}+O(x^{3})$, so the limit is $2$.",
        ("12.4", "problem", "12.13"): r"Integration by parts with $u=t^{z}$, $dv=e^{-t}dt$ gives $\Gamma(z+1)=z\Gamma(z)$. Substituting $t=z^{2}/2$ in $\Gamma(1/2)$ reduces it to the Gaussian integral $\sqrt{\pi}$.",
        ("12.4", "problem", "12.16"): r"$\nabla f(w)=Aw-b$, so $\nabla f(w)^{T}v=w^{T}Av-b^{T}v$ (using $A^{T}=A$). Taking $\nabla_{w}$ gives $Av=Hv$ with Hessian $H=A$.",
        ("12.4", "problem", "12.22"): r"For $g(x,y)=x^{2}-y^{2}$, $\nabla g(0,0)=0$ and $H=\operatorname{diag}(2,-2)$ with $\det H=-4<0$, so $(0,0)$ is a saddle point.",
        ("12.4", "problem", "12.23"): r"Here $P=3x^{2}y+2x$, $Q=x^{3}-2y$, so $\partial P/\partial y=3x^{2}=\partial Q/\partial x$ and $\omega$ is closed. A potential is $U=x^{3}y+x^{2}-y^{2}$, hence the integral from $(0,0)$ to $(1,2)$ is $U(1,2)-U(0,0)=-1$.",
    })
    solution_fixes.update({
        ("13.4", "problem", "13.2"): r"Since $\theta\in(0,\pi/2)$, $\cos\theta=\sqrt{1-(3/5)^{2}}=4/5$. Then $\tan\theta=3/4$ and $\sin(2\theta)=2\sin\theta\cos\theta=2(3/5)(4/5)=24/25$.",
        ("13.4", "problem", "13.11"): r"$b_{n}=\frac{1}{\pi}\int_{-\pi}^{\pi}f(t)\sin(nt)dt=\frac{4}{n\pi}$ for odd $n$ and $0$ for even $n$. At $t=\pi/2$ the series $1-\frac{1}{3}+\frac{1}{5}-\cdots$ sums to $\pi/4$, so $f(\pi/2)=1$.",
        ("13.4", "problem", "13.12"): r"$\frac{1}{\pi}\int_{-\pi}^{\pi}|f|^{2}dt=2$ since $|f|=1$. Parseval gives $\sum_{n}b_{n}^{2}=2$, i.e. $\frac{16}{\pi^{2}}\sum_{k\geq0}\frac{1}{(2k+1)^{2}}=2$, so $\sum_{k\geq0}1/(2k+1)^{2}=\pi^{2}/8$.",
        ("13.4", "problem", "13.13"): r"$Z_{1}^{2}+Z_{2}^{2}=-2\ln U_{1}(\cos^{2}(2\pi U_{2})+\sin^{2}(2\pi U_{2}))=-2\ln U_{1}$. Since $-\ln U_{1}\sim\mathrm{Exp}(1)$, the sum is $\mathrm{Exp}(1/2)$.",
        ("13.4", "problem", "13.14"): r"Summing the geometric series $\sum_{k=-n}^{n}e^{ik\theta}=e^{-in\theta}(1-e^{i(2n+1)\theta})/(1-e^{i\theta})=\sin((n+1/2)\theta)/\sin(\theta/2)$. Taking real parts gives $1+2\sum_{k=1}^{n}\cos(k\theta)$.",
        ("13.4", "problem", "13.20"): r"$\int_{-\pi}^{\pi}\cos(kx)dx=0$ for $k\geq1$, so only the constant term $1$ in $D_{N}$ integrates, giving $(1/2\pi)(2\pi)=1$.",
        ("14.4", "problem", "14.1"): r"$u^{T}v=6-2k-4=2-2k=0$, so $k=1$.",
        ("14.4", "problem", "14.3"): r"$\operatorname{tr}(A)=7-2=5$, $\det(A)=7(-2)=-14$, and $\det(A^{-1})=1/\det(A)=-1/14$.",
        ("14.4", "problem", "14.8"): r"Total energy is $100+25+1+0.01=126.01$. The rank-2 Frobenius error is $\sqrt{1^{2}+0.1^{2}}\approx1.005$, retaining $125/126.01\approx99.2\%$ of variance.",
        ("14.4", "problem", "14.11"): r"$P^{2}=P$ implies $\lambda^{2}=\lambda$, so $\lambda\in\{0,1\}$. By cyclic trace, $\operatorname{tr}(P)=\operatorname{tr}((X^{T}X)^{-1}X^{T}X)=\operatorname{tr}(I_{d})=d$.",
        ("14.4", "problem", "14.17"): r"$\kappa_{2}(A)=\sigma_{\max}/\sigma_{\min}=100/0.01=10000$. Worst-case relative error amplification $\|\Delta x\|_{2}/\|x\|_{2}$ is $\kappa_{2}(A)=10000$ times the relative residual.",
        ("14.4", "problem", "14.18"): r"$L=\begin{pmatrix}1&0\\\rho&\sqrt{1-\rho^{2}}\end{pmatrix}$, since $LL^{T}=\begin{pmatrix}1&\rho\\\rho&1\end{pmatrix}$.",
        ("14.4", "problem", "14.24"): r"$\|A\|_{2}=\sigma_{\max}=5$, $\|A\|_{F}=\sqrt{5^{2}+3^{2}+1^{2}}=\sqrt{35}$, and nuclear norm $\|A\|_{*}=5+3+1=9$.",
        ("14.4", "problem", "14.25"): r"$\lambda_{+}=(1+\sqrt{q})^{2}=(1+\sqrt{0.25})^{2}=(1.5)^{2}=2.25$.",
    })
    solution_fixes.update({
        ("16.4", "problem", "16.1"): r"The Hessian is $H=\operatorname{diag}(4,36)$, so $\mu=4$, $L=36$ and $\kappa=L/\mu=9$.",
        ("16.4", "problem", "16.2"): r"$S_{0.5}(w)=\operatorname{sign}(w)\max(0,|w|-0.5)$. Hence $[2.4,-0.35,0.18,-1.5]^{T}$ maps to $[1.9,0,0,-1.0]^{T}$.",
        ("16.4", "problem", "16.5"): r"GMV weights satisfy $w_{i}\propto1/\sigma_{i}^{2}$, so $w_{1}:w_{2}=100:25=4:1$ and $(w_{1},w_{2})=(0.8,0.2)$. The GMV volatility is $1/\sqrt{125}\approx8.94\%$.",
        ("16.4", "problem", "16.6"): r"Equating $1-\eta\mu=-(1-\eta L)$ gives $\eta^{*}=2/(L+\mu)$. The resulting contraction factor is $(\kappa-1)/(\kappa+1)$.",
        ("16.4", "problem", "16.8"): r"$f^{*}=(bp-q)/b$ with $b=3$, $p=0.35$, $q=0.65$ gives $(1.05-0.65)/3=0.40/3\approx13.33\%$.",
        ("16.4", "problem", "16.11"): r"Under $x=Ay$, $\nabla g=A^{T}\nabla f$ and $\nabla^{2}g=A^{T}(\nabla^{2}f)A$. Hence $A(\nabla^{2}g)^{-1}\nabla g=(\nabla^{2}f)^{-1}\nabla f$, so Newton's step in $x$ is invariant.",
        ("16.4", "problem", "16.13"): r"Summing $BR$ independent signals each with Sharpe $s_{i}=\mathrm{IC}$ gives total Sharpe $\sqrt{BR}\cdot\mathrm{IC}$, i.e. $\mathrm{IR}=\mathrm{IC}\sqrt{BR}$.",
    })
    solution_fixes.update({
        ("22.2", "exam", "22.28"): r"Under uncertain volatility $\sigma_{t}\in[\sigma_{\min},\sigma_{\max}]$, the worst-case (superreplication) price satisfies $V_{t}+rSV_{S}+\max_{\sigma\in[\sigma_{\min},\sigma_{\max}]}\frac{1}{2}\sigma^{2}S^{2}V_{SS}-rV=0$. The maximum selects $\sigma_{\max}$ when $\Gamma=V_{SS}>0$ (e.g. long convex payoffs) and $\sigma_{\min}$ when $\Gamma<0$.",
    })
    for c in chapters:
        for s in c["sections"]:
            blocks = s["blocks"]
            rebuilt = []
            i = 0
            while i < len(blocks):
                b = blocks[i]
                key = (s["num"], b.get("type"), b.get("num"))
                if b.get("type") in ("example", "problem", "exam") and key in solution_fixes:
                    rebuilt.append(b)
                    j = i + 1
                    while j < len(blocks):
                        nxt = blocks[j]
                        if nxt.get("type") in ("problem", "exam", "example", "tier", "theorem"):
                            break
                        j += 1
                    rebuilt.append({"type": "solution", "label": "Step-by-Step Solution",
                                    "runs": md_runs(solution_fixes[key])})
                    i = j
                else:
                    rebuilt.append(b)
                    i += 1
            s["blocks"] = rebuilt

    # Strip generic boilerplate that the PDF repeats verbatim in every
    # chapter: the "First-Principles Strategy & Structural Setup" intro
    # block and the "Verification & Structural Takeaway" filler. The
    # actual derivation blocks remain, so no mathematics is lost.
    def _block_text(b):
        return " ".join((r.get("v") if r.get("k") == "text" else r.get("latex", ""))
                        for r in (b.get("runs") or []))
    for c in chapters:
        for sec in c["sections"]:
            kept = []
            for b in sec["blocks"]:
                if b.get("type") == "solution" and b.get("label") == "Step-by-Step Solution":
                    t = _block_text(b)
                    if "First-Principles Strategy" in t or "Structural Setup:" in t:
                        continue
                if b.get("type") == "verify":
                    continue
                if b.get("type") == "solution" and "Complete Step-by-Step Derivation" in (b.get("label") or ""):
                    b = dict(b)
                    b["label"] = "Step-by-Step Solution"
                kept.append(b)
            sec["blocks"] = kept

    # Proof titles sometimes carry raw LaTeX (e.g. "Proof of $(A∪B)...$").
    # They are rendered as plain text, so strip the dollars and map the
    # handful of commands that appear to readable Unicode.
    _PROOF_TITLES = {
        "1.1": "Proof of (A ∪ B)ᶜ = Aᶜ ∩ Bᶜ",
        "3.1": "Proof of Σ r·C(n,r) = n·2ⁿ⁻¹",
    }
    for c in chapters:
        for s in c["sections"]:
            for b in s["blocks"]:
                if b.get("type") == "proof" and b.get("title"):
                    if s["num"] in _PROOF_TITLES:
                        b["title"] = _PROOF_TITLES[s["num"]]
                    elif "$" in b["title"] or "\\" in b["title"]:
                        t = b["title"].replace("$", "").replace("\\cup", "∪") \
                            .replace("\\cap", "∩").replace("\\sum", "∑") \
                            .replace("\\binom", "C").replace("{", "").replace("}", "") \
                            .replace("\\", "")
                        b["title"] = re.sub(r"\s+", " ", t).strip()

    # Drop math runs with no content; they were emitted by empty radical
    # rows in the PDF and render as invisible noise.
    for c in chapters:
        for sec in c["sections"]:
            for b in sec["blocks"]:
                runs = b.get("runs")
                if runs:
                    b["runs"] = [r for r in runs
                                 if not (r.get("k") == "math" and
                                         not r.get("latex", "").strip())]
                if b.get("statement"):
                    b["statement"] = [r for r in b["statement"]
                                      if not (r.get("k") == "math" and
                                              not r.get("latex", "").strip())]

    # Normalize glyphs that leaked from the PDF's matrix brackets and from
    # empty radical rows. These keep the formulas readable and KaTeX-safe.
    for c in chapters:
        for sec in c["sections"]:
            for b in sec["blocks"]:
                for r in b.get("runs", []):
                    if r.get("k") != "math":
                        continue
                    tex = r["latex"]
                    tex = tex.replace(r'\#', ']').replace('#', ']')
                    tex = tex.replace('"', '[')
                    tex = tex.replace('&', r'\;')
                    tex = tex.replace(r'\surd', r'\sqrt{\phantom{x}}')
                    tex = re.sub(r'\\text\{d([A-Za-z])\}', r'\\mathrm{d}\1', tex)
                    tex = tex.replace('=,', '=').replace(',,', ',')
                    tex = tex.replace('undefined', 'x')
                    r["latex"] = tex
                if b.get("statement"):
                    for r in b["statement"]:
                        if r.get("k") == "math":
                            tex = r["latex"]
                            tex = tex.replace(r'\#', ']').replace('#', ']')
                            tex = tex.replace('"', '[')
                            tex = tex.replace('&', r'\;')
                            tex = tex.replace(r'\surd', r'\sqrt{\phantom{x}}')
                            tex = re.sub(r'\\text\{d([A-Za-z])\}', r'\\mathrm{d}\1', tex)
                            tex = tex.replace('=,', '=').replace(',,', ',')
                            tex = tex.replace('undefined', 'x')
                            r["latex"] = tex

    # Hand-curated repairs for the few matrix-bearing blocks the PDF
    # parser simply cannot recover. Replace the whole problem/exam and its
    # solution run, rather than leaving half-read fragments behind.
    # Final sanitation pass (after any curated replacements) over every
    # run — including chapter intros, which the earlier pass skipped.
    for c in chapters:
        for b in c.get("intro", []):
            for r in b.get("runs", []):
                if r.get("k") == "math":
                    t = r["latex"]
                    r["latex"] = (t.replace(r'\#', ']').replace('#', ']')
                                  .replace('"', '[').replace('&', r'\;')
                                  .replace(r'\surd', r'\sqrt{\phantom{x}}')
                                  .replace('=,', '=').replace(',,', ',')
                                  .replace('undefined', 'x'))
        for sec in c["sections"]:
            for b in sec["blocks"]:
                for r in b.get("runs", []):
                    if r.get("k") == "math":
                        t = r["latex"]
                        r["latex"] = (t.replace(r'\#', ']').replace('#', ']')
                                      .replace('"', '[').replace('&', r'\;')
                                      .replace(r'\surd', r'\sqrt{\phantom{x}}')
                                      .replace('=,', '=').replace(',,', ',')
                                      .replace('undefined', 'x'))
                if b.get("statement"):
                    for r in b["statement"]:
                        if r.get("k") == "math":
                            t = r["latex"]
                            r["latex"] = (t.replace(r'\#', ']').replace('#', ']')
                                          .replace('"', '[').replace('&', r'\;')
                                          .replace(r'\surd', r'\sqrt{\phantom{x}}')
                                          .replace('=,', '=').replace(',,', ',')
                                          .replace('undefined', 'x'))

    # Merge row-split formulas: the PDF parser frequently emits a single
    # formula as several consecutive math runs in the same block (e.g.
    # "x", "=", "y" or "\sqrt{...}", "radicand"). Concatenate them so the
    # reader shows one complete formula. Also absorb the radicand of an
    # empty radical into the next short math run when available.
    def _merge_one(runs):
        if not runs:
            return runs
        # 1) absorb short radicands into empty radicals
        out = []
        i = 0
        while i < len(runs):
            r = runs[i]
            if (r.get("k") == "math" and "\\sqrt{\\phantom{x}}" in (r.get("latex") or "")):
                nxt = runs[i + 1] if i + 1 < len(runs) else None
                if nxt and nxt.get("k") == "math":
                    cand = (nxt.get("latex") or "").strip()
                    # strip sentence punctuation absorbed into the math run
                    cand_clean = cand.rstrip(".,;:")
                    if cand_clean and len(cand_clean) <= 20 and "=" not in cand_clean:
                        r = dict(r)
                        r["latex"] = r["latex"].replace(
                            "\\sqrt{\\phantom{x}}",
                            "\\sqrt{" + cand_clean + "}")
                        out.append(r)
                        i += 2
                        continue
            out.append(r)
            i += 1
        # 2) merge consecutive math runs
        merged = []
        for r in out:
            if (r.get("k") == "math" and merged and merged[-1].get("k") == "math"):
                merged[-1] = {"k": "math",
                              "latex": (merged[-1].get("latex") or "") +
                                       " " + (r.get("latex") or "")}
            else:
                merged.append(r)
        return merged

    for c in chapters:
        for b in c.get("intro", []):
            b["runs"] = _merge_one(b.get("runs") or [])
        for sec in c["sections"]:
            for b in sec["blocks"]:
                b["runs"] = _merge_one(b.get("runs") or [])
                if b.get("statement"):
                    b["statement"] = _merge_one(b["statement"])

    # Drop any remaining empty-radical glyphs from chapter intros (symbol
    # decoder tables). These are stray sqrt symbols with no radicand and
    # render as blank radicals.
    for c in chapters:
        for b in c.get("intro", []):
            runs = b.get("runs") or []
            b["runs"] = [r for r in runs if not (r.get("k") == "math" and "\\sqrt{\\phantom{x}}" in (r.get("latex") or ""))]

    # Lone-phantom display blocks: the radical glyph landed alone in its own
    # display block and the radicand is the first math run of the next
    # block. Absorb it (and drop it from the donor) so no empty radical
    # remains visible.
    for c in chapters:
        for sec in c["sections"]:
            blocks = sec["blocks"]
            for idx, b in enumerate(blocks):
                runs = b.get("runs") or []
                if (b.get("type") == "display" and len(runs) == 1 and
                        runs[0].get("k") == "math" and
                        "\\sqrt{\\phantom{x}}" in (runs[0].get("latex") or "")):
                    if idx + 1 < len(blocks):
                        nxt = blocks[idx + 1]
                        nruns = nxt.get("runs") or []
                        if nruns and nruns[0].get("k") == "math":
                            cand = (nruns[0].get("latex") or "").strip().rstrip(".,;:")
                            if cand and len(cand) <= 24 and "=" not in cand:
                                b["runs"][0]["latex"] = b["runs"][0]["latex"].replace(
                                    "\\sqrt{\\phantom{x}}",
                                    "\\sqrt{" + cand + "}")
                                nxt["runs"] = nruns[1:]

    def replace_sequence(secnum, num, new_blocks):
        sec = next(s for c in chapters for s in c["sections"] if s["num"] == secnum)
        for i, b in enumerate(sec["blocks"]):
            if b.get("num") == num and b.get("type") in ("problem", "exam"):
                j = i + 1
                while j < len(sec["blocks"]):
                    nxt = sec["blocks"][j]
                    if nxt.get("type") in ("problem", "exam", "tier", "theorem"):
                        break
                    j += 1
                sec["blocks"][i:j] = new_blocks
                return
        raise AssertionError(f"block not found: {secnum} {num}")

    replace_sequence("12.4", "12.10", [
        {"type": "problem", "num": "12.10",
         "runs": md_runs(r"Classify all critical points of "
                        r"$f(x,y)=x^{3}-3xy+y^{3}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(
             r"Compute $\nabla f=(3x^{2}-3y,\ -3x+3y^{2})$. "
             r"Setting both partials to zero gives $(0,0)$ and $(1,1)$. "
             r"The Hessian is $H=\begin{pmatrix}6x&-3\\-3&6y\end{pmatrix}$. "
             r"At $(0,0)$, $\det H=-9<0$, so it is a saddle point. "
             r"At $(1,1)$, $H_{11}=6>0$ and $\det H=27>0$, so it is a "
             r"strict local minimum.")},
    ])

    replace_sequence("14.4", "14.4", [
        {"type": "problem", "num": "14.4",
         "runs": md_runs(r"Compute $\|A\|_{F}$ for "
                        r"$A=\begin{pmatrix}1&-2\\2&-4\end{pmatrix}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\|A\|_{F}="
                        r"\sqrt{1^{2}+(-2)^{2}+2^{2}+(-4)^{2}}="
                        r"\sqrt{25}=5$.")},
    ])

    replace_sequence("14.4", "14.5", [
        {"type": "problem", "num": "14.5",
         "runs": md_runs(r"Rewrite "
                        r"$x^{T}\begin{pmatrix}2&5\\1&4\end{pmatrix}x$ "
                        r"using a symmetric matrix $S$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Only the symmetric part contributes to a quadratic "
                        r"form, so "
                        r"$S=\frac{A+A^{T}}{2}="
                        r"\begin{pmatrix}2&3\\3&4\end{pmatrix}$.")},
    ])

    replace_sequence("14.4", "14.6", [
        {"type": "problem", "num": "14.6",
         "runs": md_runs(r"For "
                        r"$A=\begin{pmatrix}3&1\\1&3\end{pmatrix}$, find "
                        r"its eigenvalues, orthonormal eigenvectors, and "
                        r"$A^{10}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"The eigenvalues are $4$ and $2$, with "
                        r"$q_{1}=\frac{1}{\sqrt{2}}(1,1)^{T}$ and "
                        r"$q_{2}=\frac{1}{\sqrt{2}}(1,-1)^{T}$. Hence "
                        r"$A^{10}="
                        r"\begin{pmatrix}"
                        r"(4^{10}+2^{10})/2&(4^{10}-2^{10})/2\\"
                        r"(4^{10}-2^{10})/2&(4^{10}+2^{10})/2"
                        r"\end{pmatrix}="
                        r"\begin{pmatrix}524800&523776\\523776&524800\end{pmatrix}$.")},
    ])

    replace_sequence("14.4", "14.7", [
        {"type": "problem", "num": "14.7",
         "runs": md_runs(r"Fit $y=\beta_{0}+\beta_{1}x$ to "
                        r"$(-1,1),(0,1),(1,4)$ via "
                        r"$\hat\beta=(X^{T}X)^{-1}X^{T}y$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$X^{T}X=\begin{pmatrix}3&0\\0&2\end{pmatrix}$ and "
                        r"$X^{T}y=\begin{pmatrix}6\\3\end{pmatrix}$, so "
                        r"$\hat\beta=\begin{pmatrix}2\\1.5\end{pmatrix}$ and "
                        r"$\hat y=2+1.5x$.")},
    ])

    replace_sequence("14.4", "14.10", [
        {"type": "problem", "num": "14.10",
         "runs": md_runs(r"Verify that "
                        r"$S=\begin{pmatrix}2&-1&0\\-1&2&-1\\0&-1&2\end{pmatrix}$ "
                        r"is positive definite.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Leading principal minors: "
                        r"$\Delta_{1}=2>0$, "
                        r"$\Delta_{2}=\det\begin{pmatrix}2&-1\\-1&2\end{pmatrix}=3>0$, "
                        r"and $\Delta_{3}=\det S=4>0$. By Sylvester's criterion, "
                        r"$S\succ0$.")},
    ])

    replace_sequence("15.4", "15.9", [
        {"type": "problem", "num": "15.9",
         "runs": md_runs(r"Find $(\pi_{1},\pi_{2})$ for "
                        r"$P=\begin{pmatrix}0.95&0.05\\0.15&0.85\end{pmatrix}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Balance the stationary equations: "
                        r"$0.05\pi_{1}=0.15\pi_{2}$, hence "
                        r"$\pi_{1}=3\pi_{2}$. Since "
                        r"$\pi_{1}+\pi_{2}=1$, "
                        r"$(\pi_{1},\pi_{2})=(0.75,0.25)$.")},
    ])

    replace_sequence("22.1", "22.3", [
        {"type": "exam", "num": "22.3",
         "title": "Ch. 3 + Ch. 4 — Complex Eigenvalues of 2D Rotation",
         "open": False,
         "runs": md_runs(r"Find the eigenvalues of "
                        r"$R(\theta)=\begin{pmatrix}\cos\theta&-\sin\theta\\"
                        r"\sin\theta&\cos\theta\end{pmatrix}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"The characteristic equation is "
                        r"$(\cos\theta-\lambda)^{2}+\sin^{2}\theta=0$, so "
                        r"$\lambda=\cos\theta\pm i\sin\theta=e^{\pm i\theta}$.")},
    ])


    # --- Chapters 17-21: clean problem + solution rewrites (PDF fragments
    # --- dropped the radicands/terms; replaced with concise derivations).
    replace_sequence("17.4", "17.1", [
        {"type": "problem", "num": "17.1", "title": "Brownian Moments Drill",
         "runs": md_runs(r"Find $E[W_{4}]$, $\operatorname{Var}(W_{4})$, and "
                         r"$\operatorname{Var}(W_{5}-W_{2})$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Since $W_{t}\sim\mathcal{N}(0,t)$ and increments are "
                         r"independent, $E[W_{4}]=0$ and "
                         r"$\operatorname{Var}(W_{4})=4$. Also "
                         r"$W_{5}-W_{2}\sim\mathcal{N}(0,5-2)$, so "
                         r"$\operatorname{Var}(W_{5}-W_{2})=3$.")},
    ])
    replace_sequence("17.4", "17.2", [
        {"type": "problem", "num": "17.2", "title": "Ito Differential Drill",
         "runs": md_runs(r"Find $d(e^{2W_{t}})$ using Ito's Lemma.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"For $f(x)=e^{2x}$, $f'=2e^{2x}$ and "
                         r"$f''=4e^{2x}$. Ito's Lemma with $(dW_{t})^{2}=dt$ gives "
                         r"$d(e^{2W_{t}})=2e^{2W_{t}}dW_{t}+2e^{2W_{t}}dt$.")},
    ])
    replace_sequence("17.4", "17.3", [
        {"type": "problem", "num": "17.3", "title": "Put-Call Parity Drill",
         "runs": md_runs(r"If $S_{0}=105$, $K=100$, $e^{-rT}=0.96$, and $C=12$, "
                         r"find $P$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Put-call parity is $C-P=S_{0}-Ke^{-rT}$, so "
                         r"$P=C-S_{0}+Ke^{-rT}=12-105+96=3$.")},
    ])
    replace_sequence("17.4", "17.4", [
        {"type": "problem", "num": "17.4", "title": "Put Delta and Gamma Drill",
         "runs": md_runs(r"If call delta is $0.65$ and call gamma is $\Gamma_{C}=0.03$, "
                         r"find $\Delta_{P}$ and $\Gamma_{P}$ for the corresponding put.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Differentiating $C-P=S_{0}-Ke^{-rT}$ gives "
                         r"$\Delta_{P}=\Delta_{C}-1=-0.35$. Differentiating again, "
                         r"the linear term $S_{0}$ drops out, so "
                         r"$\Gamma_{P}=\Gamma_{C}=0.03$.")},
    ])
    replace_sequence("17.4", "17.5", [
        {"type": "problem", "num": "17.5", "title": "Gaussian VaR Drill",
         "runs": md_runs(r"For daily $\sigma=$ Rs. 10,000 ($\mu=0$), find 95% VaR "
                         r"($z=1.645$) and 99% VaR ($z=2.326$).")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Gaussian VaR is $z\sigma$. Hence "
                         r"$\operatorname{VaR}_{95\%}=1.645\times10000=16450$ and "
                         r"$\operatorname{VaR}_{99\%}=2.326\times10000=23260$.")},
    ])
    replace_sequence("17.4", "17.6", [
        {"type": "problem", "num": "17.6", "title": "Ito Integral of Brownian Motion",
         "runs": md_runs(r"Prove $\int_{0}^{T}W_{t}dW_{t}=\frac{1}{2}W_{T}^{2}-\frac{1}{2}T$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Ito's Lemma on $W_{t}^{2}$ gives "
                         r"$d(W_{t}^{2})=2W_{t}dW_{t}+dt$. Integrating from $0$ to "
                         r"$T$ and rearranging yields the result.")},
    ])
    replace_sequence("17.4", "17.7", [
        {"type": "problem", "num": "17.7", "title": "Power Contract Valuation",
         "runs": md_runs(r"Under $dS_{t}=rS_{t}dt+\sigma S_{t}dW_{t}^{Q}$, find "
                         r"$V_{0}=e^{-rT}E^{Q}[S_{T}^{2}]$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"By Ito's Lemma, $d(S_{t}^{2})=(2r+\sigma^{2})S_{t}^{2}dt"
                         r"+2\sigma S_{t}^{2}dW_{t}^{Q}$, so "
                         r"$E^{Q}[S_{T}^{2}]=S_{0}^{2}e^{(2r+\sigma^{2})T}$. "
                         r"Discounting gives $V_{0}=S_{0}^{2}e^{(r+\sigma^{2})T}$.")},
    ])
    replace_sequence("17.4", "17.8", [
        {"type": "problem", "num": "17.8", "title": "Digital Cash-or-Nothing Call",
         "runs": md_runs(r"Price a binary call paying Rs. 100 at $T$ if $S_{T}>K$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Risk-neutral pricing gives "
                         r"$V_{0}=100e^{-rT}Q(S_{T}>K)=100e^{-rT}N(d_{2})$, where "
                         r"$d_{2}=\frac{\ln(S_{0}/K)+(r-\frac{1}{2}\sigma^{2})T}{\sigma\sqrt{T}}$.")},
    ])
    replace_sequence("17.4", "17.9", [
        {"type": "problem", "num": "17.9", "title": "Ornstein-Uhlenbeck Half-Life",
         "runs": md_runs(r"Find the half-life and stationary standard deviation for "
                         r"$dX_{t}=-4X_{t}dt+0.30dW_{t}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"The mean decays as $e^{-4t}$, so the half-life is "
                         r"$\ln2/4\approx0.173$. The stationary variance is "
                         r"$\frac{0.30^{2}}{2\times4}=\frac{0.09}{8}$, giving a "
                         r"stationary standard deviation of about $0.106$.")},
    ])
    replace_sequence("17.4", "17.10", [
        {"type": "problem", "num": "17.10", "title": "Expected Shortfall Drill",
         "runs": md_runs(r"Compute $\operatorname{CVaR}_{99\%}$ for daily "
                         r"$\sigma=$ Rs. 20,000, given $N'(2.326)=0.02665$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"For a normal loss, "
                         r"$\operatorname{CVaR}_{99\%}=\sigma\frac{\phi(2.326)}{0.01}"
                         r"=20000\times\frac{0.02665}{0.01}=53300$.")},
    ])
    replace_sequence("17.4", "17.11", [
        {"type": "problem", "num": "17.11", "title": "Brownian Covariance",
         "runs": md_runs(r"Prove $E[W_{s}W_{t}]=s$ for $0\leq s\leq t$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Write $W_{t}=W_{s}+(W_{t}-W_{s})$ with independent "
                         r"increments. Then "
                         r"$E[W_{s}W_{t}]=E[W_{s}^{2}]+E[W_{s}]E[W_{t}-W_{s}]=s+0=s$.")},
    ])
    replace_sequence("17.4", "17.12", [
        {"type": "problem", "num": "17.12", "title": "Vega-Gamma Identity",
         "runs": md_runs(r"Prove $\mathcal{V}=\sigma S^{2}\tau\Gamma$ in Black-Scholes.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Vega is $\mathcal{V}=S\sqrt{\tau}N'(d_{1})$ and gamma is "
                         r"$\Gamma=\frac{N'(d_{1})}{S\sigma\sqrt{\tau}}$. Multiplying "
                         r"$\sigma S^{2}\tau$ by $\Gamma$ gives "
                         r"$S\sqrt{\tau}N'(d_{1})=\mathcal{V}$.")},
    ])
    replace_sequence("17.4", "17.13", [
        {"type": "problem", "num": "17.13", "title": "Forward Martingale Property",
         "runs": md_runs(r"Show $F_{t,T}=S_{t}e^{r(T-t)}$ satisfies "
                         r"$dF_{t,T}=\sigma F_{t,T}dW_{t}^{Q}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"By the product rule, "
                         r"$dF_{t,T}=-rF_{t,T}dt+e^{r(T-t)}(rS_{t}dt+\sigma S_{t}dW_{t}^{Q})$ "
                         r"$=\sigma F_{t,T}dW_{t}^{Q}$. The drift is zero, so the "
                         r"forward price is a $Q$-martingale.")},
    ])
    replace_sequence("17.4", "17.14", [
        {"type": "problem", "num": "17.14", "title": "Score Diffusion Marginal",
         "runs": md_runs(r"Find $p(x_{t}\mid x_{0})$ for "
                         r"$dx_{t}=-\frac{1}{2}\beta x_{t}dt+\sqrt{\beta}dW_{t}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"This is an Ornstein-Uhlenbeck process with mean "
                         r"$e^{-\beta t/2}x_{0}$ and variance "
                         r"$1-e^{-\beta t}$. Hence "
                         r"$x_{t}\mid x_{0}\sim\mathcal{N}(e^{-\beta t/2}x_{0},(1-e^{-\beta t})I)$, "
                         r"converging to $\mathcal{N}(0,I)$ as $t\to\infty$.")},
    ])
    replace_sequence("17.4", "17.15", [
        {"type": "problem", "num": "17.15", "title": "Dividend BSM Formula",
         "runs": md_runs(r"Modify the Black-Scholes call formula for continuous "
                         r"dividend yield $q$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Replace $S$ by $Se^{-q\tau}$: "
                         r"$C=Se^{-q\tau}N(d_{1})-Ke^{-r\tau}N(d_{2})$ with "
                         r"$d_{1}=\frac{\ln(S/K)+(r-q+\frac{1}{2}\sigma^{2})\tau}{\sigma\sqrt{\tau}}$ "
                         r"and $d_{2}=d_{1}-\sigma\sqrt{\tau}$.")},
    ])
    replace_sequence("17.4", "17.16", [
        {"type": "problem", "num": "17.16", "title": "Fourth Moment of Brownian Motion",
         "runs": md_runs(r"Apply Ito's Lemma to $W_{t}^{4}$ and take expectations to "
                         r"prove $E[W_{t}^{4}]=3t^{2}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Ito's Lemma gives "
                         r"$d(W_{t}^{4})=4W_{t}^{3}dW_{t}+6W_{t}^{2}dt$. Taking "
                         r"expectations kills the stochastic integral, so "
                         r"$E[W_{t}^{4}]=6\int_{0}^{t}s\,ds=3t^{2}$.")},
    ])
    replace_sequence("17.4", "17.17", [
        {"type": "problem", "num": "17.17", "title": "Ito Isometry Variance",
         "runs": md_runs(r"Compute the distribution and variance of "
                         r"$I_{T}=\int_{0}^{T}t^{2}dW_{t}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"By the Ito isometry, $I_{T}$ is Gaussian with mean $0$ and "
                         r"variance $\int_{0}^{T}(t^{2})^{2}dt=\int_{0}^{T}t^{4}dt"
                         r"=\frac{T^{5}}{5}$.")},
    ])
    replace_sequence("17.4", "17.18", [
        {"type": "problem", "num": "17.18", "title": "Exponential Martingale Parameter",
         "runs": md_runs(r"Find the constant $c$ such that "
                         r"$M_{t}=\exp(\sigma W_{t}+ct)$ is a martingale.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Ito's Lemma gives "
                         r"$\frac{dM_{t}}{M_{t}}=(c+\frac{1}{2}\sigma^{2})dt+\sigma dW_{t}$. "
                         r"Setting the drift to zero yields $c=-\frac{1}{2}\sigma^{2}$.")},
    ])
    replace_sequence("17.4", "17.19", [
        {"type": "problem", "num": "17.19", "title": "Black-76 Futures Option Formula",
         "runs": md_runs(r"Under $Q$, a futures price $F_{t}$ has zero drift. Write "
                         r"the Black-76 call price in terms of $F_{0}$, $K$, $r$, "
                         r"$\sigma$, $T$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$C_{0}=e^{-rT}[F_{0}N(d_{1})-KN(d_{2})]$ with "
                         r"$d_{1,2}=\frac{\ln(F_{0}/K)\pm\frac{1}{2}\sigma^{2}T}{\sigma\sqrt{T}}$.")},
    ])
    replace_sequence("17.4", "17.20", [
        {"type": "problem", "num": "17.20", "title": "FX Risk-Neutral Drift",
         "runs": md_runs(r"For an exchange rate $S_{t}$ with domestic rate $r_{d}$ and "
                         r"foreign rate $r_{f}$, state its risk-neutral drift under "
                         r"the domestic measure.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"The foreign currency is like a stock paying continuous "
                         r"dividend yield $q=r_{f}$, so "
                         r"$dS_{t}=(r_{d}-r_{f})S_{t}dt+\sigma S_{t}dW_{t}^{Q}$.")},
    ])
    replace_sequence("17.4", "17.21", [
        {"type": "problem", "num": "17.21", "title": "Digital Call Price",
         "runs": md_runs(r"What is the Black-Scholes price at $t=0$ of a binary call "
                         r"paying 1 if $S_{T}>K$ and 0 otherwise?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$V_{\mathrm{dig}}=e^{-rT}Q(S_{T}>K)=e^{-rT}N(d_{2})$, with "
                         r"$d_{2}=\frac{\ln(S_{0}/K)+(r-\frac{1}{2}\sigma^{2})T}{\sigma\sqrt{T}}$.")},
    ])
    replace_sequence("17.4", "17.22", [
        {"type": "problem", "num": "17.22", "title": "Geometric Asian Volatility",
         "runs": md_runs(r"Since the time-averaged Brownian motion has variance "
                         r"reduced by a factor of $1/3$, what is the effective "
                         r"volatility of the continuous geometric average?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"The averaged Brownian motion has variance $T/3$ instead of "
                         r"$T$, so the effective volatility is "
                         r"$\sigma_{\mathrm{Asian}}=\sigma/\sqrt{3}\approx0.577\sigma$.")},
    ])
    replace_sequence("17.4", "17.23", [
        {"type": "problem", "num": "17.23", "title": "First-Passage Probability",
         "runs": md_runs(r"Find the probability that $W_{t}$ hits $+2$ at some time "
                         r"$t\in[0,4]$, in terms of $\Phi$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"By the reflection principle, "
                         r"$P(\max_{0\leq t\leq4}W_{t}\geq2)=2P(W_{4}\geq2)"
                         r"=2(1-\Phi(1))\approx2\times0.1587=0.3173$.")},
    ])
    replace_sequence("17.4", "17.24", [
        {"type": "problem", "num": "17.24", "title": "Two-Boundary Rinom",
         "runs": md_runs(r"Starting at $W_{0}=x\in(0,B)$, find the probability that "
                         r"$W_{t}$ hits $B$ before $0$ and the expected exit time "
                         r"$E[\tau]$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Optional stopping on the martingale $W_{t}$ gives "
                         r"$P(W_{\tau}=B)=x/B$. Optional stopping on $W_{t}^{2}-t$ "
                         r"gives $E[W_{\tau}^{2}]=E[\tau]+x^{2}$ with "
                         r"$E[W_{\tau}^{2}]=xB$, so $E[\tau]=x(B-x)$.")},
    ])
    replace_sequence("17.4", "17.25", [
        {"type": "problem", "num": "17.25", "title": "Stratonovich Conversion",
         "runs": md_runs(r"Evaluate the Stratonovich integral "
                         r"$\int_{0}^{T}W_{t}\circ dW_{t}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Stratonovich equals Ito plus half the quadratic variation: "
                         r"$\int_{0}^{T}W_{t}\circ dW_{t}=\int_{0}^{T}W_{t}dW_{t}+\frac{1}{2}T"
                         r"=\frac{1}{2}W_{T}^{2}$.")},
    ])

    replace_sequence("18.4", "18.1", [
        {"type": "problem", "num": "18.1", "title": "Matrix Conditioning Drill",
         "runs": md_runs(r"If $\sigma_{\max}(A)=500$ and $\sigma_{\min}(A)=0.5$, find $\kappa_{2}(A)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\kappa_{2}(A)=\sigma_{\max}/\sigma_{\min}=500/0.5=1000$, so about three decimal digits are lost in solving $Ax=b$.")},
    ])
    replace_sequence("18.4", "18.2", [
        {"type": "problem", "num": "18.2", "title": "Newton Square-Root Drill",
         "runs": md_runs(r"Compute $x_{1}=\frac{1}{2}(x_{0}+10/x_{0})$ for $\sqrt{10}$ from $x_{0}=3$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$x_{1}=\frac{1}{2}(3+10/3)=\frac{1}{2}(3+3.3333)=3.1667$, close to $\sqrt{10}\approx3.1623$.")},
    ])
    replace_sequence("18.4", "18.3", [
        {"type": "problem", "num": "18.3", "title": "Monte Carlo Scaling Drill",
         "runs": md_runs(r"If $N=10{,}000$ paths give standard error Rs. 0.10, how many paths give standard error Rs. 0.01?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Standard error scales as $1/\sqrt{N}$. Cutting it by $10\times$ needs $10^{2}=100\times$ more paths, so $N=1{,}000{,}000$.")},
    ])
    replace_sequence("18.4", "18.4", [
        {"type": "problem", "num": "18.4", "title": "Finite-Difference Drill",
         "runs": md_runs(r"Compare forward vs. centered difference of $f(x)=x^{3}$ at $x=2$ with $h=0.1$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Forward: $(2.1^{3}-2^{3})/0.1=12.61$. Centered: $(2.1^{3}-1.9^{3})/0.2=12.01$. Exact $f'(2)=12$, so the centered formula is more accurate.")},
    ])
    replace_sequence("18.4", "18.5", [
        {"type": "problem", "num": "18.5", "title": "Explicit Stability Drill",
         "runs": md_runs(r"How does the explicit stability bound $\Delta t\leq(\Delta x)^{2}/(2D)$ change if $\Delta x\to\Delta x/2$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Since the bound is proportional to $(\Delta x)^{2}$, halving $\Delta x$ shrinks the bound by $4\times$.")},
    ])
    replace_sequence("18.4", "18.6", [
        {"type": "problem", "num": "18.6", "title": "Second-Difference Error Proof",
         "runs": md_runs(r"Prove $\frac{f(x+h)-2f(x)+f(x-h)}{h^{2}}=f''(x)+\frac{h^{2}}{12}f^{(4)}(x)+O(h^{4})$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Adding the Taylor expansions of $f(x+h)$ and $f(x-h)$ cancels all odd powers, leaving $2f(x)+h^{2}f''(x)+\frac{h^{4}}{12}f^{(4)}(x)$; dividing by $h^{2}$ gives the result.")},
    ])
    replace_sequence("18.4", "18.7", [
        {"type": "problem", "num": "18.7", "title": "Milstein Scheme on GBM",
         "runs": md_runs(r"Write the Milstein update for $dS_{t}=rS_{t}dt+\sigma S_{t}dW_{t}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$S_{n+1}=S_{n}+rS_{n}\Delta t+\sigma S_{n}\Delta W_{n}+\frac{1}{2}\sigma^{2}S_{n}((\Delta W_{n})^{2}-\Delta t)$.")},
    ])
    replace_sequence("18.4", "18.8", [
        {"type": "problem", "num": "18.8", "title": "Control Variate Slope",
         "runs": md_runs(r"Prove $\operatorname{Var}(Y-\beta(C-E[C]))$ is minimized at $\beta^{*}=\operatorname{Cov}(Y,C)/\operatorname{Var}(C)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"The variance is $\operatorname{Var}(Y)-2\beta\operatorname{Cov}(Y,C)+\beta^{2}\operatorname{Var}(C)$. Setting its derivative to zero gives $\beta^{*}=\operatorname{Cov}(Y,C)/\operatorname{Var}(C)$.")},
    ])
    replace_sequence("18.4", "18.9", [
        {"type": "problem", "num": "18.9", "title": "Importance Sampling Tilt",
         "runs": md_runs(r"Write the unbiased estimator for $P(Z>4)$ ($Z\sim\mathcal{N}(0,1)$) when sampling $X\sim\mathcal{N}(4,1)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\hat p=\frac{1}{N}\sum_{i=1}^{N}I(X_{i}>4)e^{-4X_{i}+8}$, where the exponential is the likelihood ratio $\phi(X_{i})/\phi(X_{i}-4)$.")},
    ])
    replace_sequence("18.4", "18.10", [
        {"type": "problem", "num": "18.10", "title": "Optimal Step Size Drill",
         "runs": md_runs(r"Balance truncation error $O(\varepsilon^{2})$ against roundoff $O(\varepsilon_{\mathrm{mach}}/\varepsilon)$ for centered differences.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Equating $\varepsilon^{2}\approx\varepsilon_{\mathrm{mach}}/\varepsilon$ gives $\varepsilon^{*}\approx\varepsilon_{\mathrm{mach}}^{1/3}\approx10^{-5.3}$.")},
    ])
    replace_sequence("18.4", "18.11", [
        {"type": "problem", "num": "18.11", "title": "Tridiagonal Solver Complexity",
         "runs": md_runs(r"Why does solving an $M\times M$ tridiagonal Crank-Nicolson matrix cost $O(M)$ instead of $O(M^{3})$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Each row has only three nonzeros, so the Thomas forward sweep and back substitution need only $O(1)$ operations per row, about $8M$ in total.")},
    ])
    replace_sequence("18.4", "18.12", [
        {"type": "problem", "num": "18.12", "title": "Log-Price PDE Transformation",
         "runs": md_runs(r"Transform the Black-Scholes PDE into constant-coefficient form using $x=\ln S$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Since $SV_{S}=V_{x}$ and $S^{2}V_{SS}=V_{xx}-V_{x}$, the PDE becomes $V_{t}+(r-\frac{1}{2}\sigma^{2})V_{x}+\frac{1}{2}\sigma^{2}V_{xx}-rV=0$.")},
    ])
    replace_sequence("18.4", "18.13", [
        {"type": "problem", "num": "18.13", "title": "Pathwise Delta Estimator",
         "runs": md_runs(r"Differentiate $C=e^{-rT}E[\max(S_{T}-K,0)]$ inside the expectation with respect to $S_{0}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Since $\partial S_{T}/\partial S_{0}=S_{T}/S_{0}$, the pathwise estimator is $\hat\Delta=e^{-rT}\frac{1}{N}\sum_{i}I(S_{T}^{(i)}>K)S_{T}^{(i)}/S_{0}$.")},
    ])
    replace_sequence("18.4", "18.14", [
        {"type": "problem", "num": "18.14", "title": "Likelihood-Ratio Greeks",
         "runs": md_runs(r"How do we compute Monte Carlo delta when the payoff $I(S_{T}>K)$ is discontinuous?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Differentiate the log-density: the score is $Z/(S_{0}\sigma\sqrt{T})$, so $\hat\Delta=e^{-rT}\frac{1}{N}\sum_{i}I(S_{T}^{(i)}>K)Z_{i}/(S_{0}\sigma\sqrt{T})$.")},
    ])
    replace_sequence("18.4", "18.15", [
        {"type": "problem", "num": "18.15", "title": "Richardson Extrapolation",
         "runs": md_runs(r"Combine first-order estimates $A(h)=A^{*}+c_{1}h+O(h^{2})$ and $A(h/2)$ to eliminate the $O(h)$ bias.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Since $A(h/2)=A^{*}+c_{1}h/2+O(h^{2})$, we get $2A(h/2)-A(h)=A^{*}+O(h^{2})$.")},
    ])
    replace_sequence("18.4", "18.16", [
        {"type": "problem", "num": "18.16", "title": "Milstein Correction for GBM",
         "runs": md_runs(r"Write the explicit Milstein step for $dS_{t}=rS_{t}dt+\sigma S_{t}dW_{t}$ and compare it to the exact exponential.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$S_{n+1}=S_{n}[1+r\Delta t+\sigma\Delta W_{n}+\frac{1}{2}\sigma^{2}((\Delta W_{n})^{2}-\Delta t)]$, matching $S_{n}\exp((r-\frac{1}{2}\sigma^{2})\Delta t+\sigma\Delta W_{n})$ to $O(\Delta t)$.")},
    ])
    replace_sequence("18.4", "18.17", [
        {"type": "problem", "num": "18.17", "title": "Optimal Importance Tilt",
         "runs": md_runs(r"To estimate $P(Z>4)$ for $Z\sim\mathcal{N}(0,1)$, what shifted proposal $\mathcal{N}(\mu,1)$ centers sampling on the threshold?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Setting $\mu=4$ centers half the samples inside the rare region $Z>4$; each sample is weighted by the likelihood ratio $e^{-4Z+8}$.")},
    ])
    replace_sequence("18.4", "18.18", [
        {"type": "problem", "num": "18.18", "title": "Stratified Sampling Decomposition",
         "runs": md_runs(r"Explain why stratified sampling across $K$ strata always has variance at most that of crude Monte Carlo.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"By the law of total variance, $\operatorname{Var}(Y)=E[\operatorname{Var}(Y\mid S)]+\operatorname{Var}(E[Y\mid S])$. Stratified sampling eliminates the second, nonnegative term.")},
    ])
    replace_sequence("18.4", "18.19", [
        {"type": "problem", "num": "18.19", "title": "Simpson Rule Precision",
         "runs": md_runs(r"Evaluate $\int_{0}^{2}x^{3}dx$ using a single panel of Simpson's rule and compare with the exact integral.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Simpson gives $\frac{2}{6}[0+4(1)^{3}+2^{3}]=4$, equal to the exact value $2^{4}/4=4$, since Simpson's rule is exact for cubics.")},
    ])
    replace_sequence("18.4", "18.20", [
        {"type": "problem", "num": "18.20", "title": "Gauss-Legendre Nodes",
         "runs": md_runs(r"Find the 2-point Gauss-Legendre nodes and weights on $[-1,1]$ that integrate polynomials up to degree 3 exactly.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Matching $\int_{-1}^{1}1\,dx=2$ gives $w_{1}=w_{2}=1$, and matching $\int_{-1}^{1}x^{2}dx=2/3$ gives $x_{1,2}=\pm1/\sqrt{3}$.")},
    ])
    replace_sequence("18.4", "18.21", [
        {"type": "problem", "num": "18.21", "title": "Longstaff-Schwartz Basis",
         "runs": md_runs(r"In pricing an American put at step $t_{k}$, which paths are included in the cross-sectional regression of continuation value on $(1,S,S^{2})$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Only in-the-money paths ($S_{t_{k}}<K$) are included, since early exercise is relevant only when immediate exercise value $K-S_{t_{k}}$ is positive.")},
    ])
    replace_sequence("18.4", "18.22", [
        {"type": "problem", "num": "18.22", "title": "Multilevel Monte Carlo Identity",
         "runs": md_runs(r"Write the telescoping identity for $E[P_{L}]$ across grid levels $l=0,\ldots,L$ in multilevel Monte Carlo.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$E[P_{L}]=E[P_{0}]+\sum_{l=1}^{L}E[P_{l}-P_{l-1}]$. Coupling fine and coarse paths with the same Brownian increments makes $\operatorname{Var}(P_{l}-P_{l-1})$ small.")},
    ])
    replace_sequence("18.4", "18.23", [
        {"type": "problem", "num": "18.23", "title": "Central Gamma Stencil",
         "runs": md_runs(r"Prove via Taylor expansion that $\frac{V(S+h)-2V(S)+V(S-h)}{h^{2}}=V''(S)+\frac{h^{2}}{12}V^{(4)}(S)+O(h^{4})$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Adding $V(S\pm h)=V(S)\pm hV'+h^{2}V''/2\pm h^{3}V'''/6+h^{4}V^{(4)}/24$ cancels odd derivatives and leaves $h^{2}V''+h^{4}V^{(4)}/12$.")},
    ])
    replace_sequence("18.4", "18.24", [
        {"type": "problem", "num": "18.24", "title": "Quasi-Monte Carlo Convergence",
         "runs": md_runs(r"If $N=10{,}000$, compare the theoretical QMC error scale $1/N$ with the Monte Carlo scale $1/\sqrt{N}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$1/N=10^{-4}$ versus $1/\sqrt{N}=10^{-2}$: the QMC scale is $100\times$ smaller in low-to-moderate dimensions.")},
    ])
    replace_sequence("18.4", "18.25", [
        {"type": "problem", "num": "18.25", "title": "Upwind Differencing Drill",
         "runs": md_runs(r"When drift is large relative to diffusion, why can central differencing produce negative transition probabilities?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"When the cell Peclet number $|\mathrm{Pe}|=|\mu|\Delta x/\sigma^{2}$ exceeds $1$, one off-diagonal tridiagonal weight flips sign; one-sided upwind differencing restores positivity.")},
    ])

    replace_sequence("19.4", "19.1", [
        {"type": "problem", "num": "19.1", "title": "Attention Variance Scaling",
         "runs": md_runs(r"If $d_{k}=256$ and $q_{i},k_{i}\sim\mathcal{N}(0,1)$ i.i.d., find $\operatorname{Std}(q^{T}k)$ before scaling.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$q^{T}k=\sum_{i=1}^{256}q_{i}k_{i}$ is a sum of $256$ unit-variance terms, so $\operatorname{Std}(q^{T}k)=\sqrt{256}=16$. Dividing by $\sqrt{d_{k}}=16$ restores unit variance.")},
    ])
    replace_sequence("19.4", "19.2", [
        {"type": "problem", "num": "19.2", "title": "Softmax Shift Invariance",
         "runs": md_runs(r"Prove $\operatorname{softmax}(z+c\mathbf{1})=\operatorname{softmax}(z)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"The numerator becomes $e^{z_{i}+c}=e^{c}e^{z_{i}}$ and the denominator becomes $e^{c}\sum_{k}e^{z_{k}}$; the factor $e^{c}$ cancels.")},
    ])
    replace_sequence("19.4", "19.3", [
        {"type": "problem", "num": "19.3", "title": "LayerNorm Drill",
         "runs": md_runs(r"Apply standard LayerNorm to $x=[2,4,6,8]^{T}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"The mean is $\mu=5$ and the centered vector is $[-3,-1,1,3]^{T}$. The standard deviation is $\sqrt{5}$, so $\hat x=\frac{1}{\sqrt{5}}[-3,-1,1,3]^{T}$.")},
    ])
    replace_sequence("19.4", "19.4", [
        {"type": "problem", "num": "19.4", "title": "Multi-Head Dimension Split",
         "runs": md_runs(r"For $d_{\mathrm{model}}=4096$ and $h=32$ heads, find $d_{k}$ and $1/\sqrt{d_{k}}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$d_{k}=4096/32=128$, so $1/\sqrt{d_{k}}=1/\sqrt{128}=1/(8\sqrt{2})\approx0.0884$.")},
    ])
    replace_sequence("19.4", "19.5", [
        {"type": "problem", "num": "19.5", "title": "Inverted Dropout Scaling",
         "runs": md_runs(r"If dropout zeros $p=20\%$ of neurons during training, what multiplier keeps test-time expectation unchanged?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Multiply kept neurons by $1/(1-0.20)=1.25$, so the expected activation is unchanged.")},
    ])
    replace_sequence("19.4", "19.6", [
        {"type": "problem", "num": "19.6", "title": "Softmax Cross-Entropy Gradient",
         "runs": md_runs(r"Prove $\nabla_{z}\mathcal{L}=p-y$ for $\mathcal{L}(z)=-\sum_{k=1}^{K}y_{k}\ln p_{k}(z)$ with $\sum_{k}y_{k}=1$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Differentiating gives $\partial\mathcal{L}/\partial z_{j}=-y_{j}(1-p_{j})-\sum_{i\neq j}y_{i}(-p_{j})=p_{j}\sum_{i}y_{i}-y_{j}=p_{j}-y_{j}$.")},
    ])
    replace_sequence("19.4", "19.7", [
        {"type": "problem", "num": "19.7", "title": "RMSNorm Jacobian",
         "runs": md_runs(r"For $y=x/\|x\|_{2}$, prove $J_{y}(x)=\frac{I-yy^{T}}{\|x\|_{2}}$ and $J_{y}(x)x=0$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Differentiating $x(x^{T}x)^{-1/2}$ gives $(I-yy^{T})/\|x\|_{2}$. Multiplying by $x$ gives $(x-y\|x\|_{2})/\|x\|_{2}=0$.")},
    ])
    replace_sequence("19.4", "19.8", [
        {"type": "problem", "num": "19.8", "title": "Kaiming He Initialization",
         "runs": md_runs(r"Prove $y=W\max(0,x)$ preserves variance when $\operatorname{Var}(W_{ij})=2/d_{\mathrm{in}}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Since $E[\max(0,x_{j})^{2}]=\frac{1}{2}\operatorname{Var}(x_{j})$, we have $\operatorname{Var}(y_{i})=d_{\mathrm{in}}\operatorname{Var}(W_{ij})\frac{1}{2}\operatorname{Var}(x_{j})$, so $\operatorname{Var}(W_{ij})=2/d_{\mathrm{in}}$ preserves variance.")},
    ])
    replace_sequence("19.4", "19.9", [
        {"type": "problem", "num": "19.9", "title": "Softmax Temperature Limits",
         "runs": md_runs(r"Find $\lim_{T\to0^{+}}\operatorname{softmax}(z/T)$ and $\lim_{T\to\infty}\operatorname{softmax}(z/T)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"As $T\to0^{+}$, $p\to\mathrm{one\_hot}(\arg\max z)$. As $T\to\infty$, $p\to[1/K,\ldots,1/K]^{T}$.")},
    ])
    replace_sequence("19.4", "19.10", [
        {"type": "problem", "num": "19.10", "title": "MoE Load-Balancing Proof",
         "runs": md_runs(r"Prove $\sum_{i=1}^{E}P_{i}^{2}$ subject to $\sum_{i}P_{i}=1$ is minimized at $P_{i}=1/E$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"By Cauchy-Schwarz, $1=(\sum_{i}1\cdot P_{i})^{2}\leq E\sum_{i}P_{i}^{2}$, so $\sum_{i}P_{i}^{2}\geq1/E$, with equality at $P_{i}=1/E$.")},
    ])
    replace_sequence("19.4", "19.11", [
        {"type": "problem", "num": "19.11", "title": "Xavier Initialization",
         "runs": md_runs(r"Find the Xavier compromise between forward variance $1/d_{\mathrm{in}}$ and backward gradient variance $1/d_{\mathrm{out}}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Taking the harmonic mean gives $\operatorname{Var}(W_{ij})=\frac{2}{d_{\mathrm{in}}+d_{\mathrm{out}}}$.")},
    ])
    replace_sequence("19.4", "19.12", [
        {"type": "problem", "num": "19.12", "title": "KV-Cache Memory",
         "runs": md_runs(r"Compute FP16 KV-cache memory for 32 layers, $h=32$, $d_{k}=128$, $N=8192$ under MHA vs. 8-group GQA.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"MHA needs $2\times32\times32\times128\times8192\times2$ bytes $\approx4.29$ GB. With 8 KV heads instead of 32, GQA cuts this by $32/8=4\times$ to about $1.07$ GB.")},
    ])
    replace_sequence("19.4", "19.13", [
        {"type": "problem", "num": "19.13", "title": "Maximal Update Scaling",
         "runs": md_runs(r"Why must Adam's learning rate scale as $\eta\propto1/d$ as hidden width $d\to\infty$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"A weight update $\Delta Wx$ sums $d$ aligned terms of size $O(\eta)$, growing as $O(d\eta)$ unless $\eta\propto1/d$.")},
    ])
    replace_sequence("19.4", "19.14", [
        {"type": "problem", "num": "19.14", "title": "Speculative Decoding Proof",
         "runs": md_runs(r"Show that accepting draft $q(x)$ with probability $\min(1,p(x)/q(x))$ and resampling proportional to $\max(0,p-q)$ yields exactly $p(x)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$q(x)\min(1,p(x)/q(x))+\max(0,p(x)-q(x))=\min(p(x),q(x))+\max(0,p(x)-q(x))=p(x)$.")},
    ])
    replace_sequence("19.4", "19.15", [
        {"type": "problem", "num": "19.15", "title": "Perplexity Conversion",
         "runs": md_runs(r"Convert validation cross-entropy $\mathcal{L}=2.0$ nats/token into perplexity and bits/token.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\mathrm{PPL}=e^{2.0}\approx7.389$ and $2.0/\ln2\approx2.885$ bits/token.")},
    ])
    replace_sequence("19.4", "19.16", [
        {"type": "problem", "num": "19.16", "title": "RMSNorm Formula",
         "runs": md_runs(r"Write the RMSNorm transformation for $x\in\mathbb{R}^{d}$ with gain $\gamma\in\mathbb{R}^{d}$ and explain why it saves compute over LayerNorm.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\mathrm{RMSNorm}(x)=\frac{x}{\sqrt{\frac{1}{d}\sum_{i=1}^{d}x_{i}^{2}+\epsilon}}\odot\gamma$. It eliminates the mean-centering pass, saving one reduction.")},
    ])
    replace_sequence("19.4", "19.17", [
        {"type": "problem", "num": "19.17", "title": "SwiGLU Parameter Count",
         "runs": md_runs(r"A SwiGLU MLP has three matrices instead of two. Why is $d_{ff}$ set to $\frac{8}{3}d$ instead of $4d$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"With three matrices, $3\times d\times d_{ff}=8d^{2}$ when $d_{ff}=\frac{8}{3}d$, matching the $2\times d\times4d=8d^{2}$ parameters of a standard MLP.")},
    ])
    replace_sequence("19.4", "19.18", [
        {"type": "problem", "num": "19.18", "title": "GQA Memory Reduction",
         "runs": md_runs(r"A 70B LLM has $H_{Q}=64$ query heads and $H_{KV}=8$ key-value heads. By what factor does GQA reduce KV-cache bandwidth versus MHA?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"By $H_{Q}/H_{KV}=64/8=8\times$.")},
    ])
    replace_sequence("19.4", "19.19", [
        {"type": "problem", "num": "19.19", "title": "Perplexity from Loss",
         "runs": md_runs(r"If a language model has test cross-entropy $L=2.0$ nats/token, what is its perplexity $\mathrm{PPL}=e^{L}$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\mathrm{PPL}=e^{2.0}\approx7.389$.")},
    ])
    replace_sequence("19.4", "19.20", [
        {"type": "problem", "num": "19.20", "title": "Chinchilla Scaling Law",
         "runs": md_runs(r"If compute $C\approx6ND$ and loss is $L(N,D)=E+AN^{-\alpha}+BD^{-\beta}$ with $\alpha=\beta=0.34$, how do optimal $N^{*}$ and $D^{*}$ scale when $C$ grows $100\times$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Equal exponents give $N^{*}\propto C^{1/2}$ and $D^{*}\propto C^{1/2}$, so a $100\times$ compute increase multiplies both by $10\times$.")},
    ])
    replace_sequence("19.4", "19.21", [
        {"type": "problem", "num": "19.21", "title": "InfoNCE Lower Bound",
         "runs": md_runs(r"In CLIP/SimCLR with batch size $K$, what is the initial InfoNCE loss $-\ln\frac{e^{s_{ii}}}{\sum_{j=1}^{K}e^{s_{ij}}}$ when all similarity logits are equal?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"When all $s_{ij}=c$, the loss is $-\ln(1/K)=\ln K$.")},
    ])
    replace_sequence("19.4", "19.22", [
        {"type": "problem", "num": "19.22", "title": "DDPM Marginal Variance",
         "runs": md_runs(r"If $\beta_{t}=0.02$ is constant ($\alpha_{t}=0.98$) for $t=1,\ldots,50$, compute $\bar\alpha_{50}=0.98^{50}$ and the noise variance $1-\bar\alpha_{50}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\bar\alpha_{50}=(0.98)^{50}\approx e^{-1}\approx0.364$, so the noise variance is $1-0.364=0.636$.")},
    ])
    replace_sequence("19.4", "19.23", [
        {"type": "problem", "num": "19.23", "title": "Reparameterization Gradient",
         "runs": md_runs(r"Why can we differentiate $E_{\varepsilon\sim\mathcal{N}(0,1)}f(\mu+\sigma\varepsilon)$ pathwise, while $E_{z\sim\mathcal{N}(\mu,\sigma^{2})}f(z)$ cannot be differentiated pathwise without reparameterization?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Reparameterization moves $(\mu,\sigma)$ outside the sampling distribution $\mathcal{N}(0,1)$, so the integral is over a parameter-independent base measure and $\nabla_{\mu,\sigma}$ passes directly inside $f(\mu+\sigma\varepsilon)$.")},
    ])
    replace_sequence("19.4", "19.24", [
        {"type": "problem", "num": "19.24", "title": "Speculative Residual Distribution",
         "runs": md_runs(r"With draft $q(x)$ and target $p(x)$, a token is accepted with probability $\min(1,p(x)/q(x))$. What residual distribution is sampled on rejection?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$p_{\mathrm{res}}(x)\propto\max(0,p(x)-q(x))$, guaranteeing the output follows exactly $p(x)$.")},
    ])
    replace_sequence("19.4", "19.25", [
        {"type": "problem", "num": "19.25", "title": "FlashAttention Rescaling",
         "runs": md_runs(r"Block 1 has $(m_{1}=2,\ell_{1}=3)$ and Block 2 has $(m_{2}=4,\ell_{2}=5)$. Compute the merged global $(m,\ell)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$m=\max(2,4)=4$ and $\ell=e^{2-4}(3)+e^{4-4}(5)=3e^{-2}+5\approx5.406$.")},
    ])

    replace_sequence("20.4", "20.1", [
        {"type": "problem", "num": "20.1", "title": "Effective Horizon Drill",
         "runs": md_runs(r"Find the effective horizon $1/(1-\gamma)$ for $\gamma=0.98$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$1/(1-0.98)=1/0.02=50$ steps.")},
    ])
    replace_sequence("20.4", "20.2", [
        {"type": "problem", "num": "20.2", "title": "TD Error Drill",
         "runs": md_runs(r"Compute $\delta_{t}=r_{t}+\gamma V(s_{t+1})-V(s_{t})$ for $V(s_{t})=12$, $r_{t}=3$, $V(s_{t+1})=10$, $\gamma=0.9$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\delta_{t}=3+0.9(10)-12=0$.")},
    ])
    replace_sequence("20.4", "20.3", [
        {"type": "problem", "num": "20.3", "title": "Zero Mean Advantage",
         "runs": md_runs(r"Prove $E_{a\sim\pi}[A_{\pi}(s,a)]=0$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Since $A_{\pi}(s,a)=Q_{\pi}(s,a)-V_{\pi}(s)$, we have $E_{a}[Q_{\pi}(s,a)]-V_{\pi}(s)=V_{\pi}(s)-V_{\pi}(s)=0$.")},
    ])
    replace_sequence("20.4", "20.4", [
        {"type": "problem", "num": "20.4", "title": "TWAP Inventory Drill",
         "runs": md_runs(r"For $X_{0}=60{,}000$ shares over $T=6$ hours, find the TWAP speed $v$ and inventory at $t=2$ hours.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$v=X_{0}/T=10{,}000$ shares/hour, so inventory at $2$ hours is $x(2)=60{,}000-2\times10{,}000=40{,}000$ shares.")},
    ])
    replace_sequence("20.4", "20.5", [
        {"type": "problem", "num": "20.5", "title": "GAE Endpoints Drill",
         "runs": md_runs(r"What do $\lambda=0$ and $\lambda=1$ give in $\hat A_{t}^{GAE}=\sum_{l=0}^{\infty}(\gamma\lambda)^{l}\delta_{t+l}$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\lambda=0$ gives the 1-step TD error $\delta_{t}$; $\lambda=1$ telescopes to the unbiased Monte Carlo return minus $V(s_{t})$.")},
    ])
    replace_sequence("20.4", "20.6", [
        {"type": "problem", "num": "20.6", "title": "Bellman Contraction Steps",
         "runs": md_runs(r"If $\gamma=0.90$ and $\|V_{0}-V^{*}\|_{\infty}\leq10$, find $k$ so $\|V_{k}-V^{*}\|_{\infty}\leq0.01$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Contraction gives $10(0.90)^{k}\leq0.01$, so $k\geq\ln(10^{-3})/\ln(0.90)\approx65.6$, hence $k=66$ iterations.")},
    ])
    replace_sequence("20.4", "20.7", [
        {"type": "problem", "num": "20.7", "title": "Policy Gradient Baseline",
         "runs": md_runs(r"Prove $E_{a\sim\pi_{\theta}}[\nabla_{\theta}\ln\pi_{\theta}(a\mid s)b(s)]=0$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$b(s)\sum_{a}\nabla_{\theta}\pi_{\theta}(a\mid s)=b(s)\nabla_{\theta}(1)=0$.")},
    ])
    replace_sequence("20.4", "20.8", [
        {"type": "problem", "num": "20.8", "title": "Gaussian Score Gradient",
         "runs": md_runs(r"Compute $\nabla_{\mu}\ln\pi(a\mid s)$ for $a\sim\mathcal{N}(\mu,\sigma^{2})$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\nabla_{\mu}\ln\pi(a\mid s)=\frac{a-\mu}{\sigma^{2}}$.")},
    ])
    replace_sequence("20.4", "20.9", [
        {"type": "problem", "num": "20.9", "title": "Almgren-Chriss TWAP Limit",
         "runs": md_runs(r"Prove $\lim_{\kappa\to0}X_{0}\frac{\sinh(\kappa(T-t))}{\sinh(\kappa T)}=X_{0}(1-t/T)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Since $\sinh(u)=u+O(u^{3})$, the ratio tends to $\kappa(T-t)/(\kappa T)=1-t/T$.")},
    ])
    replace_sequence("20.4", "20.10", [
        {"type": "problem", "num": "20.10", "title": "Merton Allocation",
         "runs": md_runs(r"Maximize $w(\mu-r)-\frac{1}{2}\gamma w^{2}\sigma^{2}$ over $w$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Setting the derivative to zero gives $w^{*}=(\mu-r)/(\gamma\sigma^{2})$.")},
    ])
    replace_sequence("20.4", "20.11", [
        {"type": "problem", "num": "20.11", "title": "One-Step LQR Feedback",
         "runs": md_runs(r"Minimize $x_{0}^{2}+u_{0}^{2}+P(x_{0}+u_{0})^{2}$ ($P>0$) over control $u_{0}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$2u_{0}+2P(x_{0}+u_{0})=0$, so $u_{0}^{*}=-Px_{0}/(1+P)$.")},
    ])
    replace_sequence("20.4", "20.12", [
        {"type": "problem", "num": "20.12", "title": "Permanent Impact Path-Independence",
         "runs": md_runs(r"Prove $\int_{0}^{T}\gamma x(t)x'(t)dt$ depends only on $X_{0}$, not on the path $x(t)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\int_{0}^{T}\gamma x(t)x'(t)dt=\frac{\gamma}{2}[x(t)^{2}]_{0}^{T}=-\frac{1}{2}\gamma X_{0}^{2}$, since $x(T)=0$.")},
    ])
    replace_sequence("20.4", "20.13", [
        {"type": "problem", "num": "20.13", "title": "Soft Actor-Critic Value",
         "runs": md_runs(r"Evaluate $\max_{\pi}\sum_{a}\pi(a\mid s)[Q(s,a)-\alpha\ln\pi(a\mid s)]$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"By Fenchel conjugacy of negative entropy, the optimum is $V^{*}(s)=\alpha\ln\sum_{a}\exp(Q(s,a)/\alpha)$.")},
    ])
    replace_sequence("20.4", "20.14", [
        {"type": "problem", "num": "20.14", "title": "GRPO Group Advantage",
         "runs": md_runs(r"Normalize group rewards $r=[1,1,0,0]$ via $\hat A_{i}=(r_{i}-\mu_{r})/\sigma_{r}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"With $\mu_{r}=0.5$ and $\sigma_{r}=0.5$, $\hat A=[+1,+1,-1,-1]$.")},
    ])
    replace_sequence("20.4", "20.15", [
        {"type": "problem", "num": "20.15", "title": "Avellaneda-Stoikov Skew",
         "runs": md_runs(r"Why does the reservation price $r(s,q,t)=s-q\gamma\sigma^{2}(T-t)$ subtract $q\gamma\sigma^{2}(T-t)$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"When long inventory ($q>0$), the market maker skews quotes down to attract buyers and deter sellers, pushing inventory back toward zero.")},
    ])
    replace_sequence("20.4", "20.16", [
        {"type": "problem", "num": "20.16", "title": "Baseline Unbiasedness",
         "runs": md_runs(r"Prove $E_{a\sim\pi_{\theta}}[\nabla_{\theta}\ln\pi_{\theta}(a\mid s)V(s)]=0$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\sum_{a}\pi_{\theta}(a\mid s)\frac{\nabla_{\theta}\pi_{\theta}(a\mid s)}{\pi_{\theta}(a\mid s)}V(s)=V(s)\nabla_{\theta}(\sum_{a}\pi_{\theta}(a\mid s))=V(s)\nabla_{\theta}(1)=0$.")},
    ])
    replace_sequence("20.4", "20.17", [
        {"type": "problem", "num": "20.17", "title": "GAE Definition",
         "runs": md_runs(r"Write $\hat A_{t}^{GAE}$ in terms of TD residuals $\delta_{t+l}=r_{t+l}+\gamma V(s_{t+l+1})-V(s_{t+l})$ and compare $\lambda=0$ vs. $\lambda=1$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\hat A_{t}^{GAE}=\sum_{l=0}^{\infty}(\gamma\lambda)^{l}\delta_{t+l}$. At $\lambda=0$ it is the low-variance 1-step TD error $\delta_{t}$; at $\lambda=1$ it is the unbiased Monte Carlo return minus $V(s_{t})$.")},
    ])
    replace_sequence("20.4", "20.18", [
        {"type": "problem", "num": "20.18", "title": "PPO Clipped Objective",
         "runs": md_runs(r"With ratio $r_{t}(\theta)$ and $\epsilon=0.2$, what is the PPO objective when $\hat A_{t}>0$ and $r_{t}(\theta)=1.5$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\min(1.5\hat A_{t},\mathrm{clip}(1.5,0.8,1.2)\hat A_{t})=1.2\hat A_{t}$, with flat zero gradient beyond $1.2$.")},
    ])
    replace_sequence("20.4", "20.19", [
        {"type": "problem", "num": "20.19", "title": "Inventory Skew Calculation",
         "runs": md_runs(r"A market maker holds $q=+500$ shares at mid-price $s=100$ with $\gamma=0.01$, $\sigma=2$, $T-t=0.25$. Compute the reservation price.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$r=100-500(0.01)(2^{2})(0.25)=100-5=95$, skewing quotes down by $5$ to offload long inventory.")},
    ])
    replace_sequence("20.4", "20.20", [
        {"type": "problem", "num": "20.20", "title": "Bellman Contraction Proof",
         "runs": md_runs(r"Prove $(\mathcal{T}V)(s)=\max_{a}R(s,a)+\gamma\sum_{s'}P(s'\mid s,a)V(s')$ satisfies $\|\mathcal{T}U-\mathcal{T}V\|_{\infty}\leq\gamma\|U-V\|_{\infty}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\max_{a}Q_{U}-\max_{a}Q_{V}\leq\max_{a}|Q_{U}-Q_{V}|\leq\gamma\max_{a}\sum_{s'}P(s'\mid s,a)|U(s')-V(s')|\leq\gamma\|U-V\|_{\infty}$.")},
    ])
    replace_sequence("20.4", "20.21", [
        {"type": "problem", "num": "20.21", "title": "UCB1 Bonus Calculation",
         "runs": md_runs(r"In UCB1, arm $i$ with empirical mean played $n_{i}$ times out of $t$ total pulls has bonus $\sqrt{2\ln t/n_{i}}$. Compute it for $t=e^{8}$, $n_{i}=16$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\sqrt{2\times8/16}=\sqrt{1}=1.0$.")},
    ])
    replace_sequence("20.4", "20.22", [
        {"type": "problem", "num": "20.22", "title": "Transient Impact Block Trades",
         "runs": md_runs(r"If transient impact $I_{t}$ decays at rate $\rho>0$ ($dI_{t}=-\rho I_{t}dt+\eta dq_{t}$), why does optimal execution include block trades at $t=0$ and $t=T$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"An initial block at $t=0$ triggers exponential resilience decay over $(0,T)$, continuous trading maintains constant impact, and a final block at $T$ liquidates the remainder.")},
    ])
    replace_sequence("20.4", "20.23", [
        {"type": "problem", "num": "20.23", "title": "Scalar Riccati Equation",
         "runs": md_runs(r"For $\dot x=u$ with cost $\int_{0}^{\infty}(qx^{2}+ru^{2})dt$ ($q,r>0$), solve $q-P^{2}/r=0$ for $V(x)=Px^{2}$ and the optimal feedback $u^{*}(x)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$P=\sqrt{qr}>0$ and $u^{*}(x)=-\frac{1}{2r}V'(x)=-\frac{P}{r}x=-\sqrt{q/r}\,x$.")},
    ])
    replace_sequence("20.4", "20.24", [
        {"type": "problem", "num": "20.24", "title": "Soft Bellman Closed Form",
         "runs": md_runs(r"In maximum-entropy RL with temperature $\alpha>0$ and backup $V(s)=\max_{\pi}\sum_{a}\pi(a\mid s)Q(s,a)-\alpha\ln\pi(a\mid s)$, find $V(s)$ in closed form.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$V(s)=\alpha\ln(\sum_{a}\exp(Q(s,a)/\alpha))$.")},
    ])
    replace_sequence("20.4", "20.25", [
        {"type": "problem", "num": "20.25", "title": "Kyle Lambda Equilibrium",
         "runs": md_runs(r"In Kyle's model, fundamental value variance is $\Sigma_{0}=4$ and noise-trader variance is $\sigma_{u}^{2}=16$. Compute $\lambda=\sqrt{\Sigma_{0}}/(2\sigma_{u})$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\lambda=2/(2\times4)=0.25$.")},
    ])

    replace_sequence("21.4", "21.1", [
        {"type": "problem", "num": "21.1", "title": "Zero Yield and Forward Rate",
         "runs": md_runs(r"If $P(0,1)=e^{-0.04}$ and $P(0,2)=e^{-0.10}$, find $Y(0,1)$, $Y(0,2)$, and forward rate $f_{1,2}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$Y(0,1)=0.04$, $Y(0,2)=0.10/2=0.05$, and $f_{1,2}=0.10-0.04=0.06$.")},
    ])
    replace_sequence("21.4", "21.2", [
        {"type": "problem", "num": "21.2", "title": "Heston Long-Run Volatility",
         "runs": md_runs(r"Find the long-run volatility $\sqrt{\theta}$ for $dv_{t}=4(0.09-v_{t})dt+0.3\sqrt{v_{t}}dW_{t}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\sqrt{\theta}=\sqrt{0.09}=0.30$, i.e. $30\%$.")},
    ])
    replace_sequence("21.4", "21.3", [
        {"type": "problem", "num": "21.3", "title": "In-Out Parity Drill",
         "runs": md_runs(r"If an Up-and-Out Call costs Rs. 3.20 and an Up-and-In Call costs Rs. 4.80, find the vanilla Call price.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$C_{\mathrm{vanilla}}=C_{UO}+C_{UI}=3.20+4.80=8.00$.")},
    ])
    replace_sequence("21.4", "21.4", [
        {"type": "problem", "num": "21.4", "title": "Poisson Jump Probability",
         "runs": md_runs(r"With $\lambda=0.5$/yr, find the probability of at least 1 jump in $T=2$ years.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$1-e^{-\lambda T}=1-e^{-1}\approx0.6321$, i.e. $63.21\%$.")},
    ])
    replace_sequence("21.4", "21.5", [
        {"type": "problem", "num": "21.5", "title": "Heston Smile vs Skew",
         "runs": md_runs(r"What values of $\rho$ produce a symmetric smile vs. downward equity skew?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\rho=0$ gives a symmetric smile; $\rho<0$ gives a downward-sloping equity skew.")},
    ])
    replace_sequence("21.4", "21.6", [
        {"type": "problem", "num": "21.6", "title": "Log-Normal Jump Compensator",
         "runs": md_runs(r"If $\ln J\sim\mathcal{N}(\mu_{J},\delta^{2})$, find $k=E[J-1]$ and $\mu_{J}$ such that $k=0$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$k=e^{\mu_{J}+\delta^{2}/2}-1$. Setting $k=0$ gives $\mu_{J}=-\delta^{2}/2$.")},
    ])
    replace_sequence("21.4", "21.7", [
        {"type": "problem", "num": "21.7", "title": "Two-Dimensional Ito Product Rule",
         "runs": md_runs(r"For $dX_{t}=\sigma_{X}dW_{t}^{1}$ and $dY_{t}=\sigma_{Y}dW_{t}^{2}$ with correlation $\rho$, find $d(X_{t}Y_{t})$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$d(X_{t}Y_{t})=X_{t}dY_{t}+Y_{t}dX_{t}+\rho\sigma_{X}\sigma_{Y}dt$.")},
    ])
    replace_sequence("21.4", "21.8", [
        {"type": "problem", "num": "21.8", "title": "Vasicek Duration Limit",
         "runs": md_runs(r"Find $\lim_{\tau\to\infty}B(\tau)$ for $B(\tau)=\frac{1-e^{-\kappa\tau}}{\kappa}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\lim_{\tau\to\infty}B(\tau)=1/\kappa$.")},
    ])
    replace_sequence("21.4", "21.9", [
        {"type": "problem", "num": "21.9", "title": "Reflection Principle Probability",
         "runs": md_runs(r"Find $P(\max_{0\leq t\leq1}W_{t}\geq2)$ given $N(2)=0.97725$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$2P(W_{1}\geq2)=2(1-0.97725)=0.0455$, i.e. $4.55\%$.")},
    ])
    replace_sequence("21.4", "21.10", [
        {"type": "problem", "num": "21.10", "title": "Integrated Brownian Variance",
         "runs": md_runs(r"Prove $\int_{0}^{T}W_{t}dt=\int_{0}^{T}(T-t)dW_{t}$ and compute its variance.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"By integration by parts on $d(tW_{t})$, $\int_{0}^{T}W_{t}dt=\int_{0}^{T}(T-t)dW_{t}$. Its variance is $\int_{0}^{T}(T-t)^{2}dt=T^{3}/3$.")},
    ])
    replace_sequence("21.4", "21.11", [
        {"type": "problem", "num": "21.11", "title": "Margrabe Exchange Option Volatility",
         "runs": md_runs(r"Find the effective volatility $\sigma_{Y}$ for $\max(S_{1}(T)-S_{2}(T),0)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Using $S_{2}$ as numeraire, $\sigma_{Y}=\sqrt{\sigma_{1}^{2}+\sigma_{2}^{2}-2\rho\sigma_{1}\sigma_{2}}$.")},
    ])
    replace_sequence("21.4", "21.12", [
        {"type": "problem", "num": "21.12", "title": "Instantaneous Forward Rate",
         "runs": md_runs(r"Express $f(0,T)=-\partial\ln P(0,T)/\partial T$ in terms of zero yield $Y(0,T)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Since $\ln P(0,T)=-TY(0,T)$, $f(0,T)=Y(0,T)+T\frac{\partial Y(0,T)}{\partial T}$.")},
    ])
    replace_sequence("21.4", "21.13", [
        {"type": "problem", "num": "21.13", "title": "Butterfly Arbitrage Condition",
         "runs": md_runs(r"Why must $\frac{\partial^{2}C}{\partial K^{2}}\geq0$ hold for all strikes $K$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Because $p^{Q}(K)=e^{rT}\frac{\partial^{2}C}{\partial K^{2}}$ is a probability density and cannot be negative.")},
    ])
    replace_sequence("21.4", "21.14", [
        {"type": "problem", "num": "21.14", "title": "Quanto Drift Adjustment",
         "runs": md_runs(r"What drift adjustment arises when an asset with vol $\sigma_{S}$ is paid in a foreign currency with FX vol $\sigma_{X}$ and correlation $\rho$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Cross-variation $dS_{t}dX_{t}=\rho\sigma_{S}\sigma_{X}S_{t}X_{t}dt$ induces the quanto drift adjustment $-\rho\sigma_{S}\sigma_{X}$.")},
    ])
    replace_sequence("21.4", "21.15", [
        {"type": "problem", "num": "21.15", "title": "Merton Default Probability",
         "runs": md_runs(r"If firm equity is $E_{T}=\max(A_{T}-D,0)$, what is the risk-neutral probability of default $A_{T}<D$?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$P^{Q}(A_{T}<D)=1-N(d_{2})=N(-d_{2})$, where $d_{2}$ is the distance to default.")},
    ])
    replace_sequence("21.4", "21.16", [
        {"type": "problem", "num": "21.16", "title": "Dupire Local Volatility",
         "runs": md_runs(r"If $\frac{\partial C}{\partial T}=4.0$, $r=0$, $K=100$, and $\frac{\partial^{2}C}{\partial K^{2}}=0.02$, compute the Dupire local volatility $\sigma_{\mathrm{loc}}(100,T)$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\sigma_{\mathrm{loc}}^{2}=\frac{4.0+0}{ \frac{1}{2}(100)^{2}(0.02)}=\frac{4.0}{100}=0.04$, so $\sigma_{\mathrm{loc}}=0.20$.")},
    ])
    replace_sequence("21.4", "21.17", [
        {"type": "problem", "num": "21.17", "title": "Heston Leverage Effect",
         "runs": md_runs(r"Why do equity index options show a strong negative skew ($\rho\approx-0.70$) while FX shows a symmetric smile ($\rho\approx0$)?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"In equities, market drops raise leverage and panic, driving variance up as spot falls ($dW_{t}^{S}dW_{t}^{v}=\rho dt<0$) and thickening the left tail of $\ln S_{T}$.")},
    ])
    replace_sequence("21.4", "21.18", [
        {"type": "problem", "num": "21.18", "title": "Jump-Diffusion Variance Contribution",
         "runs": md_runs(r"With jump intensity $\lambda=2$/yr, zero-mean jumps, and jump standard deviation $\delta=10\%$, compute the annual jump variance contribution versus diffusive variance $0.02$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Jump variance is $\lambda\delta^{2}=2(0.01)=0.02$, doubling total annual variance from $0.02$ to $0.04$.")},
    ])
    replace_sequence("21.4", "21.19", [
        {"type": "problem", "num": "21.19", "title": "Vasicek Bond Sensitivity",
         "runs": md_runs(r"For Vasicek mean-reversion $\kappa=0.5$/yr and maturity $\tau=2$ yr, compute $B(2)=\frac{1-e^{-\kappa\tau}}{\kappa}$ and its $\tau\to\infty$ limit.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$B(2)=(1-e^{-1})/0.5=2(1-e^{-1})\approx1.264$, and $\lim_{\tau\to\infty}B(\tau)=1/\kappa=2.0$.")},
    ])
    replace_sequence("21.4", "21.20", [
        {"type": "problem", "num": "21.20", "title": "HJM Forward Rate Drift",
         "runs": md_runs(r"Under HJM with flat volatility $\sigma(t,T)=\sigma_{0}$, compute the risk-neutral drift $\alpha(t,T)=\sigma(t,T)\int_{t}^{T}\sigma(t,u)du$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\alpha(t,T)=\sigma_{0}\int_{t}^{T}\sigma_{0}du=\sigma_{0}^{2}(T-t)$, the Ho-Lee forward rate drift.")},
    ])
    replace_sequence("21.4", "21.21", [
        {"type": "problem", "num": "21.21", "title": "CDS Par Spread",
         "runs": md_runs(r"If hazard rate $\lambda=3\%$/yr and recovery $R=40\%$, estimate the par CDS spread $s_{CDS}=(1-R)\lambda$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$s_{CDS}=(1-0.40)(0.03)=0.018$, i.e. $180$ bps.")},
    ])
    replace_sequence("21.4", "21.22", [
        {"type": "problem", "num": "21.22", "title": "Merton Distance to Default",
         "runs": md_runs(r"A firm has $V_{0}=150$, debt $D=100$ due in $T=1$ yr, $r=5\%$, and asset vol $25\%$. Compute $d_{2}$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$d_{2}=\frac{\ln(150/100)+(0.05-\frac{1}{2}(0.25)^{2})(1)}{0.25}=\frac{0.4055+0.01875}{0.25}\approx1.697$.")},
    ])
    replace_sequence("21.4", "21.23", [
        {"type": "problem", "num": "21.23", "title": "SABR ATM Skew",
         "runs": md_runs(r"Under Hagan SABR with $\beta=1$, $\sigma_{\mathrm{imp}}(K)\approx\alpha[1-\frac{1}{2}\rho\nu\ln(K/F)]$ near ATM. If $\alpha=20\%$, $\rho=-0.5$, $\nu=0.8$, find the ATM skew $\partial\sigma_{\mathrm{imp}}/\partial\ln(K/F)$ at $K=F$.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"$\frac{\partial\sigma_{\mathrm{imp}}}{\partial\ln(K/F)}=-\frac{1}{2}\alpha\rho\nu=-\frac{1}{2}(0.20)(-0.5)(0.8)=-0.04$, i.e. $-4\%$ vol per unit log-strike.")},
    ])
    replace_sequence("21.4", "21.24", [
        {"type": "problem", "num": "21.24", "title": "Variance Swap Strike and Skew",
         "runs": md_runs(r"Using $K_{\mathrm{var}}\approx\sigma_{\mathrm{ATM}}^{2}[1+3T\nu^{2}]$, explain why the fair variance strike exceeds $\sigma_{\mathrm{ATM}}^{2}$ when a smile is present.")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Out-of-the-money options in the $1/K^{2}$ replication strip trade at higher implied volatilities than $\sigma_{\mathrm{ATM}}$, so convexity pushes $K_{\mathrm{var}}>\sigma_{\mathrm{ATM}}^{2}$.")},
    ])
    replace_sequence("21.4", "21.25", [
        {"type": "problem", "num": "21.25", "title": "Forward-Measure Pricing",
         "runs": md_runs(r"Why does switching from the money-market numeraire to the $T$-maturity zero-coupon bond numeraire $P(t,T)$ simplify option pricing under stochastic rates?")},
        {"type": "solution", "label": "Step-by-Step Solution",
         "runs": md_runs(r"Under the forward measure $Q_{T}$, the discount factor $P(t,T)$ is absorbed outside the expectation: $V_{0}=P(0,T)E^{Q_{T}}[\mathrm{Payoff}(S_{T})]$, decoupling discounting from the terminal payoff.")},
    ])


    # Theorem 19.1: the PDF split its two formulas across display rows,
    # leaving a stray empty radical. Replace with a clean statement.
    _sec19 = next(s for c in chapters for s in c["sections"] if s["num"] == "19.4")
    _i_th = next(i for i, b in enumerate(_sec19["blocks"]) if b.get("type") == "theorem" and b.get("num") == "19.1")
    _j_tier = next(i for i, b in enumerate(_sec19["blocks"]) if b.get("num") == "19.16" and b.get("type") == "problem")
    _sec19["blocks"][_i_th:_j_tier] = [
        {"type": "theorem", "num": "19.1",
         "title": "FlashAttention Online Softmax Rescaling and Diffusion Score Matching",
         "open": True,
         "runs": md_runs(
             r"1. Online Safe Softmax Recurrence (FlashAttention): Given blocks 1 and 2 "
             r"with local maxima $m_{1},m_{2}$ and local sums "
             r"$\ell_{1}=\sum_{j\in B_{1}}e^{x_{j}-m_{1}}$, "
             r"$\ell_{2}=\sum_{j\in B_{2}}e^{x_{j}-m_{2}}$, the global maximum is "
             r"$m=\max(m_{1},m_{2})$ and the exact global denominator is "
             r"$\ell=e^{m_{1}-m}\ell_{1}+e^{m_{2}-m}\ell_{2}$, computing exact "
             r"attention in a single streaming SRAM pass without materializing the "
             r"$N\times N$ matrix. "
             r"2. Denoising Diffusion Forward Marginals: Under "
             r"$x_{t}=\sqrt{\bar\alpha_{t}}x_{0}+\sqrt{1-\bar\alpha_{t}}\varepsilon$ "
             r"($\varepsilon\sim\mathcal{N}(0,I)$), the score of the noisy marginal is "
             r"$\nabla_{x_{t}}\ln p_{t}(x_{t}\mid x_{0})=-\frac{x_{t}-\sqrt{\bar\alpha_{t}}x_{0}}{1-\bar\alpha_{t}}=-\frac{\varepsilon}{\sqrt{1-\bar\alpha_{t}}}$.")},
    ]

    # Drop the orphaned verification fragments of problem 14.5 that the
    # PDF laid out after the Tier 2 heading; the replacement above already
    # covers the mathematics.
    sec = next(s for c in chapters for s in c["sections"] if s["num"] == "14.4")
    i_tier = next(i for i, b in enumerate(sec["blocks"])
                  if b.get("type") == "tier" and b.get("title", "").startswith(
                      "Tier 2: Core Applied ML"))
    j_problem = next(i for i, b in enumerate(sec["blocks"])
                     if b.get("num") == "14.6")
    sec["blocks"] = sec["blocks"][:i_tier + 1] + sec["blocks"][j_problem:]

    # Normalize the common PDF glyph that KaTeX has no text-mode metric
    # for. Sigma and omega collapse to the same math symbol here.
    ohm_sign = "Ω"
    for c in chapters:
        for sec in c["sections"]:
            for b in sec["blocks"]:
                for r in b.get("runs", []):
                    if r.get("k") == "math":
                        r["latex"] = r["latex"].replace(ohm_sign, "\\Omega")

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
