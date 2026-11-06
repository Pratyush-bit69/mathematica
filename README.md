# MATHEMATICA — The Unabridged Four-Volume Mathematical Treatise

**Live:** <https://pratyush-bit69.github.io/mathematica/>
**Source:** <https://github.com/Pratyush-bit69/mathematica> (private)

A complete, self-contained mathematics website built from
`Unabridged_Mathematics_Treatise_Complete.pdf` (280 pages, typeset in LaTeX).

The treatise is not merely republished — every glyph of every formula is
**reconstructed into real LaTeX from the PDF's own geometry** and re-rendered
with KaTeX, so every expression is live, selectable and copy-pasteable.

---

## What's here

| File | What it is |
|---|---|
| `index.html` | Landing page — editorial hero, the four-volume arc, chapter index, live excerpt |
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
total math spans: 7520
parsed cleanly  : 7520 (100.00%)
```

### Fidelity against the source's own statistics

| Claim in the PDF | Extracted |
|---|---|
| 22 chapters | 22 ✓ |
| 21 formal theorem–proof blocks | 21 ✓ |
| 115 worked examples | 115 ✓ |
| 720 worked solutions (115 examples + 605 graded problems) | **720** ✓ |
| 4 volumes | 4 ✓ |
| 280 pages | 280 ✓ |

112,200 characters of prose and 7,520 mathematical expressions are recovered
from the page geometry across the 22 mathematical chapters. The PDF's
video-curriculum appendix (Part II) is intentionally excluded because it is a
link table, not part of the treatise.

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
  ~/Downloads/Unabridged_Mathematics_Treatise_Complete.pdf \
  /tmp/opencode/mathpdf/doc
python3 build/build.py            # → assets/data/treatise.js
node build/validate_tex.js        # 100 % of formulas parse
```

`build/build.py` reads the PDF from `~/Downloads/…`; override it with
`MATHEMATICA_PDF=/path/to/file.pdf`. The `pdftohtml` extracts are cached in
`/tmp/opencode/mathpdf/` (the same directory `build/pdfxml.py` and
`build/extract.py` read), and `build.py` regenerates them automatically when
they are missing.

### Tests

```bash
<python3 build/e2e.py          # 83 checks, all four pages, no console errors
python3 build/verify_push.py  # every blob SHA local vs remote + Pages + live site
python3 build/verify_live.py  # drives a browser against the deployed URL
```

`e2e.py` and `verify_live.py` need Playwright (`pip install playwright &&
playwright install chromium`); `verify_live.py` also accepts a base URL, so the
same checks can be run against the local tunnel:

```bash
python3 build/verify_live.py https://<your-tunnel>.trycloudflare.com
```

`verify_push.py` needs a GitHub token — it reads `GH_TOKEN` from the
environment, falling back to `/tmp/opencode/.gh-token`.

### Deploying

The site is 100% static — no build step, no server runtime. Pick one of these.

#### GitHub Pages (current setup)

1. Repo → **Settings → Pages → Build and deployment**.
2. Source: **Deploy from a branch**.
3. Branch: **`main`**, folder: **`/ (root)`**.
4. Save. Pages rebuilds automatically on every push.

```bash
gh auth setup-git
git add -A
git commit -m "Add support button and accuracy fixes"
git push origin main
```

Live URL: <https://pratyush-bit69.github.io/mathematica/>

> GitHub Pages on a **private** repository requires GitHub Pro, Team or
> Enterprise. If Pages is not available for this repo, make it public or use
> Netlify Drop / Cloudflare Pages, which are free for private repos.

`build/verify_push.py` proves the GitHub Pages deployment: it compares every
local blob SHA against the remote tree, confirms the Pages build matches
`HEAD`, and fetches the live pages.

#### Netlify Drop (fastest, no CLI)

1. Open <https://app.netlify.com/drop>.
2. Drag the project folder (or a zip of it) onto the page.
3. Netlify returns a public URL immediately.
4. Optional: **Site settings → Domain management** to attach a custom domain.

No build command is needed; the publish directory is the repo root.

#### Cloudflare Pages

1. Cloudflare dashboard → **Workers & Pages → Create → Pages**.
2. Connect the Git repo, or choose **Direct Upload**.
3. Framework preset: **None**. Build command: leave blank. Build output
   directory: **`/`**.
4. Deploy. Every push to `main` redeploys automatically.

Or deploy from the CLI:

```bash
npx wrangler pages deploy . --project-name mathematica
```

#### Any static host

The same folder works on S3 + CloudFront, Firebase Hosting, Vercel, Render,
or any ordinary web server. Upload the repo root and serve `index.html`.

---

## Design

* **Ink & Gold.** A deep midnight ground with warm gold accents, echoing
  the source PDF's own palette but rebuilt from scratch.
* **Type.** Newsreader for prose, Inter for the interface, JetBrains Mono for
  code, KaTeX for mathematics. Three axes: display, serif and mono.
* **Motion.** Restrained scroll reveals, a pointer-reactive card glow, and a
  reading-progress ring.
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
./build/tunnel.sh            # supervised, self-restarting (Ctrl-C stops it)
./build/tunnel.sh --daemon   # background; pid in .tunnel.pid
./build/tunnel.sh --stop     # stop the background daemon
```

The current public address is written to `live-url.txt` and served by the
local server at <http://127.0.0.1:8080/live-url> (and at
<http://127.0.0.1:8080/live-url.txt>), so the link is never lost.
