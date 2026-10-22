# MATHEMATICA — The Unabridged Four-Volume Mathematical Treatise

**Live:** <https://pratyush-bit69.github.io/mathematica/>
**Source:** <https://github.com/Pratyush-bit69/mathematica> (private)

A complete, self-contained mathematics website built from
`Unabridged_Mathematics_Treatise_Complete.pdf` (280 pages, LaTeX source).

The treatise is not merely republished — every glyph of every formula is
**reconstructed into real LaTeX from the PDF's own geometry** and re-rendered
with KaTeX, so every expression is live, selectable and copy-pasteable.

---

## What's here

| File | What it is |
|---|---|
| `index.html` | Landing page — animated hero, the four-volume arc, chapter index, live excerpt |
| `reader.html` | The treatise reader — 22 chapters, collapsible proofs & solutions, section rail, progress |
| `lab.html` | **The Math Lab** — six working instruments, all computed live in the browser |
| `glossary.html` | Glossary of every concept, a formula sheet, and the complete theorem index |
| `assets/data/treatise.js` | The reconstructed treatise (generated) |
| `assets/data/glossary.js` | Curated glossary + formula sheet |
| `assets/css/main.css` | The "Ink & Gold" design system |
| `assets/js/` | app (theme/search) · reader · home · lab · glossary · expr (expression engine) |
| `assets/katex/` | Vendored KaTeX 0.16.11 (works offline) |
| `assets/fonts/` | Vendored Newsreader, Inter, JetBrains Mono (latin subsets) |
| `build/` | The PDF → LaTeX reconstruction pipeline |

Everything is static: no server, no CDN, no network at runtime. Open
`index.html` straight from disk and it works.

---

## The reconstruction pipeline

The source PDF has no LaTeX source available, so the mathematics is
recovered from the page description itself.

```
build/
  pdfxml.py        parse pdftohtml -xml  →  positioned text items + global font table
  extract.py       words → roles → lines → math AST (fractions, scripts,
                   radicals, limits, matrices, accents, big operators)
  mathast.py       the AST and its two serializers (LaTeX and HTML/Unicode)
  docbuild.py      blocks: paragraphs, bullets, displays, theorems,
                   worked examples, graded problems, proofs, solutions
  build.py         driver → assets/data/treatise.js
  fonts.py         vendor Google Fonts locally
  validate_tex.js  parse every generated formula with KaTeX
  e2e.py           Playwright end-to-end test of the whole site
```

### How the mathematics is recovered

* **Font roles.** `pdftohtml` reports the font of every glyph run. Computer
  Modern (`CMSY10`, `CMEX10`, `CMR10`, `CMMI10`), Palatino Math, and the
  blackboard-bold subset are mapped to math roles; Palatino text is prose.
* **Script detection.** Superscripts and subscripts are glyph runs roughly
  25 % smaller and vertically offset from their base; they are attached to
  the nearest base glyph.
* **Fractions.** A numerator and denominator are two stacked script groups
  whose centres agree. A gap of 10–34 px separates a real fraction from a
  superscript/subscript pair on one base.
* **Radicals.** The `√` glyph anchors the radicand, which is delimited by a
  balanced parenthesis group or by the extent of the overline rule.
* **Accents.** `ˆ ˜ ¯ ˙ ¨` are bound to the symbol they sit above and
  re-emitted as `\hat{}`, `\tilde{}`, `\bar{}`, `\dot{}`, `\ddot{}`.
* **Big operators.** `∑ ∏ ∫` pick up their upper and lower limits from the
  script rows directly above and below.
* **Matrices.** A grid of base-sized runs with consistent column positions is
  re-emitted as a `bmatrix`.
* **Negations.** The slash LaTeX draws over `=` and `∈` is folded back into
  `≠` and `∉`.

The result is validated by parsing **every** generated formula with KaTeX:

```
$ node build/validate_tex.js
total math spans: 18747
parsed cleanly  : 18747 (100.00%)
```

### Fidelity against the source's own statistics

| Claim in the PDF | Extracted |
|---|---|
| 22 chapters | 22 ✓ |
| 21 formal theorem–proof blocks | 21 ✓ |
| 115 worked examples | 115 ✓ |
| 720 solved problems | 115 examples + 605 graded drills = **720** ✓ |
| 4 volumes | 4 ✓ |
| 280 pages | 280 ✓ |

314,974 characters of prose and 18,747 mathematical expressions are recovered
from the page geometry, with no line of the original text dropped.

---

## The Math Lab

Six instruments, all written from scratch in plain JavaScript — no plotting
library, no symbolic-algebra package.

| Instrument | What it does |
|---|---|
| **Function plotter** | Parses `sin(x) + 0.25*x`, differentiates it symbolically, draws the curve, its derivative, a tangent and a signed area, and reports the Simpson integral. |
| **Riemann sums** | Left, right, midpoint, trapezoid and Simpson rules with an adjustable partition; shows the error shrinking against the true value. |
| **Gradient descent** | Contour-traced loss surfaces (bowl, saddle, Rosenbrock) with a learning-rate and momentum sweep, animating the trajectory to the minimum. |
| **Option pricing** | Black–Scholes–Merton with the payoff at expiry, the price curve, Δ and Vega, and put–call parity checked live. |
| **Probability & CLT** | Sampler for five distributions, histogram against the theoretical density, and an inset panel showing the means of many draws converging to a normal. |
| **Linear algebra** | A live 2×2 matrix acting on the grid: the image of the lattice, the image of the unit circle, real eigenvectors, determinant and trace. |

The expression engine (`assets/js/expr.js`) is a recursive-descent parser
with symbolic differentiation and constant folding.

---

## Running it

```bash
# any static server works; this one is bundled
python3 build/serve.py            # → http://127.0.0.1:8080

# or, with no server at all
open index.html                   # data is plain JS, so file:// works
```

### Rebuilding the treatise from the PDF

```bash
pdftohtml -xml -noframes -i -hidden -q \
  ~/Downloads/Unabridged_Mathematics_Treatise_Complete.pdf /tmp/mathpdf/doc
python3 build/build.py            # → assets/data/treatise.js
node build/validate_tex.js        # 100 % of formulas parse
```

### Tests

```bash
python3 build/e2e.py          # 36 checks, all four pages, no console errors
python3 build/verify_push.py  # every blob SHA local vs remote + Pages + live site
python3 build/verify_live.py  # drives a browser against the deployed URL
```

### Deploying

The site is static, so GitHub Pages serves it directly from the repo root.

```bash
gh auth setup-git
git push origin main            # Pages rebuilds automatically
```

`build/verify_push.py` then proves the deployment: it compares every local
blob SHA against the remote tree, confirms the Pages build matches `HEAD`,
and fetches the live pages.

---

## Design

* **Ink & Gold.** A deep midnight ground with warm gold accents, echoing
  the source PDF's own palette but rebuilt from scratch.
* **Type.** Newsreader for prose, Inter for the interface, JetBrains Mono for
  code, KaTeX for mathematics. Three axes: display, serif and mono.
* **Motion.** Scroll reveals, a pointer-reactive card glow, a live
  rose-curve field behind the hero, and a reading-progress ring.
* **Two themes.** Dark by default; light is a warm paper theme, not an
  inversion.
* **Accessibility.** Semantic landmarks, visible focus rings, `prefers-
  reduced-motion` honoured, print styles that expand every collapsed proof.

### Keyboard

| Key | Action |
|---|---|
| `/` or `⌘K` | Search the whole treatise |
| `↑` `↓` `↵` | Navigate search results |
| `esc` | Close the palette |
| `J` / `K` | Next / previous chapter |
| `M` | Mark the current chapter read |

---

*Mathematics: From Foundational Algebra, Analytic Geometry & Real Calculus to
Deep Learning, Stochastic Processes & Quantitative Finance.*

---

## Live tunnel

```bash
./build/tunnel.sh          # supervised, self-restarting
./build/tunnel.sh --daemon # background
```

The current public address is written to `live-url.txt` and served by the
local server at <http://127.0.0.1:8080/live-url>, so the link is never lost.
