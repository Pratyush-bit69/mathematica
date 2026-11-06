/* =======================================================================
   MATHEMATICA — landing page
   ======================================================================= */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));
  const T = window.TREATISE;
  const M = window.Mathematica || {};
  const titleParts = M.titleParts || function (t) {
    return { title: String(t || ""), deck: "" };
  };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ======================================================== home data */
  function renderStats() {
    const s = T.meta.stats;
    const solved = s.problems + s.examples;
    const items = [
      [s.chapters, "Chapters"],
      [s.sections, "Sections"],
      [s.examples, "Examples"],
      [s.theorems, "Proofs"],
      [solved, "Solutions"],
      [s.pages, "Pages"]
    ];
    const strip = $("#statStrip");
    if (strip) {
      strip.innerHTML = items.map(function (i) {
        return '<div class="stat"><b data-count="' + i[0] + '">0</b><span>' + i[1] + "</span></div>";
      }).join("");
      countUp(strip);
    }
    const f = $("#footStats");
    if (f) f.textContent = s.chapters + " chapters · " + solved +
      " worked solutions · " + s.pages + " pages";
  }

  function countUp(root) {
    const els = $$("[data-count]", root);
    if (!els.length) return;
    if (!("IntersectionObserver" in window)) {
      els.forEach(function (e) { e.textContent = e.getAttribute("data-count"); });
      return;
    }
    const io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        const target = parseInt(e.target.getAttribute("data-count"), 10);
        const t0 = performance.now();
        const dur = 1100;
        (function step(now) {
          const p = Math.min(1, (now - t0) / dur);
          const eased = 1 - Math.pow(1 - p, 3);
          e.target.textContent = Math.round(target * eased).toLocaleString();
          if (p < 1) requestAnimationFrame(step);
        })(t0);
      });
    }, { threshold: 0.4 });
    els.forEach(function (e) { io.observe(e); });
  }

  const ICONS = {
    book: '<path d="M4 4.5A2.5 2.5 0 016.5 2H20v18H6.5A2.5 2.5 0 004 22z"/><path d="M4 17.5A2.5 2.5 0 016.5 15H20"/>',
    check: '<path d="M20 6L9 17l-5-5"/>',
    layers: '<path d="M12 2l9 5-9 5-9-5 9-5z"/><path d="M3 12l9 5 9-5"/><path d="M3 17l9 5 9-5"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>',
    graph: '<path d="M3 20h18M6 20V10M11 20V4M16 20v-7M21 20v-4"/>',
    zap: '<path d="M13 2L4.5 13.5H11l-1 8.5 8.5-11.5H12l1-8.5z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 012-2h8"/>',
    branch: '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M6 9v3a6 6 0 006 6h3"/>'
  };
  const svg = function (d) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + d + "</svg>";
  };

  const VOLUME_OUTCOMES = {
    1: "Write clean proofs, work fluently in the complex plane, count without casework, and compute with matrices.",
    2: "Move between coordinates, conics and calculus, then solve first-order ODEs and area problems with confidence.",
    3: "Prove identities, reason geometrically in three dimensions, solve linear programmes, and model uncertainty.",
    4: "Derive and implement the mathematics behind modern machine learning and quantitative finance."
  };

  const HERO_VOLUMES = {
    1: { name: "Foundations", note: "Sets, proofs, series, linear algebra, spectral theory" },
    2: { name: "Geometry & Calculus", note: "Conics, limits, derivatives, integrals, ODEs and PDEs" },
    3: { name: "Trigonometry & Probability", note: "Identities, vectors, distributions, Markov chains" },
    4: { name: "AI & Quantitative Finance", note: "Optimisation, Itô calculus, deep learning, markets" }
  };

  function renderHeroIndex() {
    const root = $("#heroIndex");
    if (!root) return;
    const pad = function (n) { return String(n).padStart(2, "0"); };
    root.innerHTML = T.volumes.map(function (v) {
      const all = v.chapters.map(function (num) {
        return T.chapters.filter(function (c) { return c.num === num; })[0];
      }).filter(Boolean);
      const info = HERO_VOLUMES[v.id] || {};
      const first = all[0];
      const last = all[all.length - 1];
      const range = first && last
        ? pad(first.num) + (first === last ? "" : "–" + pad(last.num))
        : "";
      return '<li class="hero-vol">' +
        '<a href="#vol-' + v.id + '" aria-label="Volume ' + v.roman + ", " +
          esc(info.name || v.name) + ": " + esc(info.note || "") +
          ". Chapters " + range + '.">' +
          '<span class="hero-vol-no" aria-hidden="true">' + v.roman + "</span>" +
          '<span class="hero-vol-copy">' +
            '<span class="hero-vol-name">' + esc(info.name || v.name) + "</span>" +
            '<span class="hero-vol-note">' + esc(info.note || "") + "</span>" +
          "</span>" +
          '<span class="hero-vol-meta">' +
            '<span class="hero-vol-range">' + range + "</span>" +
          "</span>" +
          '<span class="hero-vol-arrow" aria-hidden="true">→</span>' +
        "</a></li>";
    }).join("");
    const meta = $("#heroIndexMeta");
    if (meta && T.meta.stats) {
      meta.textContent = T.meta.stats.chapters + " chapters · " + T.meta.stats.sections + " sections";
    }
  }

  function renderVolumes() {
    const g = $("#volumeGrid");
    if (!g) return;
    g.innerHTML = T.volumes.map(function (v) {
      const all = v.chapters.map(function (c) {
        return T.chapters.filter(function (x) { return x.num === c; })[0];
      }).filter(Boolean);
      const sections = all.reduce(function (n, ch) {
        return n + (ch.sections || []).length;
      }, 0);
      const tally = { ex: 0, pr: 0, th: 0 };
      all.forEach(function (ch) {
        (ch.sections || []).forEach(function (s) {
          (s.blocks || []).forEach(function (b) {
            if (b.type === "example") tally.ex++;
            else if (b.type === "problem" || b.type === "exam") tally.pr++;
            else if (b.type === "theorem") tally.th++;
          });
        });
      });
      const shown = all.slice(0, 4);
      const more = all.length - shown.length;
      const rows = shown.map(function (ch) {
        const tp = titleParts(ch.title);
        return '<li><a href="reader.html#ch' + ch.num + '" title="' + esc(ch.title) + '">' +
          '<span class="vol-ch">' + String(ch.num).padStart(2, "0") + "</span>" +
          "<span>" + esc(tp.title) + "</span>" +
          '<span class="vol-arrow" aria-hidden="true">↗</span></a></li>';
      }).join("");
      const moreRow = more > 0
        ? '<li class="vol-more"><a href="reader.html#ch' + all[shown.length].num + '">' +
          "+" + more + " more chapter" + (more > 1 ? "s" : "") + ' <span aria-hidden="true">→</span></a></li>'
        : "";
      return '<article class="vol reveal" id="vol-' + v.id + '" data-roman="' + v.roman + '">' +
        '<div class="vol-head">' +
        '<span class="vol-num">' + v.roman + "</span>" +
        '<span class="vol-headtext">' +
        '<span class="vol-kicker">Volume ' + v.roman + "</span>" +
        '<span class="vol-meta">' + all.length + " chapters · " + sections + " sections</span>" +
        "</span></div>" +
        "<h3>" + esc(v.name) + "</h3>" +
        '<p class="vol-blurb">' + esc(v.blurb) + "</p>" +
        '<p class="vol-outcome"><b>Outcome</b><span>' + esc(VOLUME_OUTCOMES[v.id] || "") + "</span></p>" +
        '<ul class="vol-list">' + rows + moreRow + "</ul>" +
        '<div class="vol-foot">' +
        '<div class="vol-stats">' +
        "<span><b>" + sections + "</b> sections</span>" +
        "<span><b>" + tally.ex + "</b> examples</span>" +
        "<span><b>" + tally.pr + "</b> problems</span>" +
        (tally.th ? "<span><b>" + tally.th + "</b> proofs</span>" : "") +
        "</div>" +
        '<a class="vol-open" href="reader.html#ch' + v.chapters[0] + '">' +
        "Explore Volume " + v.roman + ' <span aria-hidden="true">→</span></a>' +
        "</div></article>";
    }).join("");
  }

  const FEATURES = [
    { i: "book", t: "Proof-driven throughout",
      d: "Every theorem states its hypotheses, proves its claim line by line, and is immediately reused.",
      m: "\\text{Theorem } 1.1:\\; (A\\cup B)^{c}=A^{c}\\cap B^{c}" },
    { i: "check", t: "720 worked solutions",
      d: "115 worked examples and 605 graded problems, arranged in four tiers from warm-up drills to PhD-level quant research extensions — with every derivation shown.",
      m: "\\sum_{k=0}^{n}\\binom{n}{k}B_k" },
    { i: "layers", t: "A real arc, not fragments",
      d: "Algebra → Calculus → Trigonometry → Vectors & Probability → Optimisation → Itô → Deep Learning.",
      m: "\\mathcal{A}\\to\\mathcal{C}\\to\\mathcal{T}\\to\\mathcal{P}\\to\\mathcal{Q}" },
    { i: "target", t: "Built for engineers and quants",
      d: "Spectral SVD, KKT duality, AdamW, Markowitz, Kelly, Heston, jump-diffusion and the Black-Scholes PDE.",
      m: "\\frac{\\partial V}{\\partial t}+\\tfrac12\\sigma^2S^2\\frac{\\partial^2V}{\\partial S^2}=rV" },
    { i: "search", t: "Instantly searchable",
      d: "One keystroke reaches every theorem, formula, worked example and solved problem in the compendium.",
      m: "\\text{search}:\\; 720\\;\\text{solutions},\\; 280\\;\\text{pages}" },
    { i: "zap", t: "An interactive laboratory",
      d: "Plot, integrate, optimise, sample and price — real mathematics you can push on directly.",
      m: "\\nabla_{\\theta}\\mathcal{L}=\\mathbb{E}[\\nabla_{\\theta}\\log\\pi_\\theta]" }
  ];

  function renderFeatures() {
    const g = $("#featureGrid");
    if (!g) return;
    g.innerHTML = FEATURES.map(function (f, i) {
      return '<div class="card feat feat-' + (i + 1) + ' reveal">' +
        '<span class="feat-no" aria-hidden="true">' + String(i + 1).padStart(2, "0") + "</span>" +
        '<div class="feat-icon">' + svg(ICONS[f.i]) + "</div>" +
        "<h3>" + f.t + "</h3><p>" + f.d + "</p>" +
        '<div class="fmath" data-tex="' + f.m.replace(/"/g, "&quot;") + '"></div>' +
        "</div>";
    }).join("");
    renderMath(g);
  }

  function renderMath(root) {
    if (!window.katex) return;
    $$("[data-tex]", root || document).forEach(function (el) {
      const display = el.classList.contains("block") || !!el.closest(".fmath");
      try {
        katex.render(el.getAttribute("data-tex"), el, {
          throwOnError: false, displayMode: display, strict: false
        });
      } catch (e) { el.textContent = el.getAttribute("data-tex"); }
    });
  }

  function renderChapters() {
    const g = $("#chapterGrid");
    if (!g) return;
    const counts = {};
    let read = {};
    try { read = JSON.parse(localStorage.getItem("mathematica:read") || "{}"); } catch (e) { read = {}; }
    T.chapters.forEach(function (c) {
      const n = { ex: 0, pr: 0, th: 0 };
      (c.sections || []).forEach(function (s) {
        (s.blocks || []).forEach(function (b) {
          if (b.type === "example") n.ex++;
          else if (b.type === "problem" || b.type === "exam") n.pr++;
          else if (b.type === "theorem") n.th++;
        });
      });
      counts[c.num] = n;
    });

    function card(c, isFinal) {
      const n = counts[c.num];
      const tp = titleParts(c.title);
      const first = (c.sections && c.sections[0]) ? c.sections[0] : null;
      const desc = first ? first.title : "";
      return '<a class="ch-card reveal' + (read[c.num] ? " is-read" : "") + (isFinal ? " ch-final" : "") + '" data-volume="' + c.volume + '" href="reader.html#ch' + c.num + '">' +
        '<span class="ch-num" aria-hidden="true">' + String(c.num).padStart(2, "0") + "</span>" +
        '<span class="ch-body">' +
        '<span class="ch-meta">' +
        '<span class="ch-vol">VOL ' + ["I", "II", "III", "IV"][c.volume - 1] + "</span>" +
        '<span aria-hidden="true">·</span><span>' + c.sections.length + " sections</span>" +
        (read[c.num] ? '<span class="ch-read">Read</span>' : "") +
        "</span>" +
        "<h3>" + esc(tp.title) + "</h3>" +
        (tp.deck ? '<span class="ch-deck">' + esc(tp.deck) + "</span>" : "") +
        '<span class="ch-desc">' + esc(desc) + "</span>" +
        '<span class="ch-stats">' +
        (n.ex ? "<span><b>" + n.ex + "</b> examples</span>" : "") +
        (n.pr ? "<span><b>" + n.pr + "</b> problems</span>" : "") +
        (n.th ? "<span><b>" + n.th + "</b> proof</span>" : "") +
        "</span></span>" +
        '<span class="ch-side">' +
        '<span class="ch-count"><b>' + c.sections.length + "</b><small>sections</small></span>" +
        '<span class="ch-go" aria-hidden="true">↗</span></span></a>';
    }
    function paint(filter) {
      const list = T.chapters.filter(function (c) {
        return filter === "all" || String(c.volume) === filter;
      });
      const finalAlone = filter === "all" && list.length % 3 === 1;
      g.innerHTML = list.map(function (c, i) {
        return card(c, finalAlone && i === list.length - 1);
      }).join("");
      $$(".reveal", g).forEach(function (el, i) {
        el.style.transitionDelay = (i % 9) * 40 + "ms";
        requestAnimationFrame(function () { el.classList.add("in"); });
      });
      $("#chCount").textContent = g.children.length + " chapter" + (g.children.length === 1 ? "" : "s");
    }
    paint("all");

    $$("[data-vol]").forEach(function (btn) {
      if (!btn.classList.contains("chip")) return;
      btn.addEventListener("click", function () {
        $$(".chip").forEach(function (b) { b.classList.remove("on"); });
        btn.classList.add("on");
        paint(btn.getAttribute("data-vol"));
      });
    });
  }

  /* --------------------------------------------------- live sample */
  function renderSample() {
    const box = $("#liveSample");
    const detail = $("#featureDetail");
    if (!box) return;
    const ch = T.chapters[0];
    let th = null, ex = null, pr = null;
    (ch.sections || []).forEach(function (s) {
      const bl = s.blocks || [];
      bl.forEach(function (b, i) {
        if (b.type === "theorem" && !th) th = b;
        if (b.type === "example" && !ex) ex = b;
        if (b.type === "problem" && !pr) pr = b;
      });
    });

    function spacedRuns(runs) {
      return (runs || []).map(function (r, i, all) {
        if (!r || r.k !== "text") return r;
        let v = String(r.v == null ? "" : r.v);
        const prev = all[i - 1];
        const next = all[i + 1];
        const nextPunct = next && next.k === "math" &&
          /^\s*[.,;:!?]\s*$/.test(String(next.latex || ""));
        if (prev && prev.k !== "text" && prev.k !== "br" && /^[A-Za-z0-9]/.test(v)) v = " " + v;
        if (prev && prev.k === "math" && /^[.,;:!?]/.test(v)) v = v.replace(/^\s+/, "");
        if (nextPunct) v = v.replace(/\s+$/, "");
        else if (next && next.k !== "text" && next.k !== "br" && /[A-Za-z0-9]$/.test(v)) v = v + " ";
        return Object.assign({}, r, { v: v });
      });
    }

    function runsHTML(runs) {
      return spacedRuns(runs).map(function (r) {
        if (r.k === "text") return r.b ? "<strong>" + esc(r.v) + "</strong>" : esc(r.v);
        if (r.k === "br") return "<br>";
        const tex = window.Mathematica && window.Mathematica.tidyTex
          ? window.Mathematica.tidyTex(r.latex)
          : String(r.latex || "");
        if (/^\\bullet$/.test(tex.trim())) return '<span class="run-bullet" aria-hidden="true">•</span>';
        const wide = tex.length > 90 || /\\text\{[^{}]{50,}\}/.test(tex) || /\\mathrm\{[^{}]{50,}\}/.test(tex);
        return '<span class="mx' + (wide ? " mx-wide" : "") + '" data-tex="' + esc(tex) + '"></span>';
      }).join("");
    }

    function partsFor(b) {
      const kids = [];
      if (!b) return { statement: [], solution: [], question: null };
      /* collect the following blocks just as the reader does */
      const sec = (ch.sections || []).filter(function (s) {
        return (s.blocks || []).indexOf(b) >= 0;
      })[0];
      if (sec) {
        const idx = sec.blocks.indexOf(b);
        for (let i = idx + 1; i < sec.blocks.length; i++) {
          const t = sec.blocks[i].type;
          if (["theorem", "example", "problem", "exam", "section", "tier"].indexOf(t) >= 0) break;
          kids.push(sec.blocks[i]);
        }
      }
      const q = kids.filter(function (k) { return k.type === "question"; })[0] || null;
      let statement = b.runs || [];
      if (q) statement = q.runs || statement;
      let inStatement = true;
      const solution = [];
      kids.forEach(function (k) {
        if (q && k === q) return;
        if (inStatement && (k.type === "display" || k.type === "para" || k.type === "bullet")) {
          return; /* these lead the statement; omitted from the compact sample */
        }
        inStatement = false;
        if (k.type === "solution" || k.type === "verify" || k.type === "proof" ||
            k.type === "display" || k.type === "para" || k.type === "bullet") {
          solution.push(k);
        }
      });
      return { statement: statement, solution: solution, question: q };
    }

    function sampleCard(b, kind, opts) {
      if (!b) return "";
      const p = partsFor(b);
      const kindLabel = kind === "ex" ? "Worked example" : kind === "prob" ? "Problem" : "Theorem";
      const isProof = kind === "theorem";
      const showLabel = isProof ? "Show proof" : "Show solution";
      const hideLabel = isProof ? "Hide proof" : "Hide solution";
      const sol = p.solution.slice(0, 3);
      const hasSol = opts && opts.solution && sol.length;
      const id = "sample-" + kind;
      return '<article class="tcard ' + kind + ' sample-card" data-show-label="' + showLabel +
        '" data-hide-label="' + hideLabel + '">' +
        '<header class="tcard-head">' +
        '<span class="tcard-kind">' + kindLabel + "</span>" +
        '<span class="tcard-num">' + esc(b.num) + "</span>" +
        '<h4 class="tcard-title">' + esc(b.title) + "</h4></header>" +
        '<div class="tcard-statement"><div class="prose">' + runsHTML(p.statement) + "</div></div>" +
        (hasSol
          ? '<div class="tcard-control"><button class="tcard-toggle" type="button" aria-expanded="false" aria-controls="' + id + '-body">' +
            '<span class="toggle-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg></span>' +
            '<span class="toggle-label">' + showLabel + "</span>" +
            '<span class="toggle-hint">' + (isProof ? "in full" : "step by step") + "</span></button></div>" +
            '<div class="tcard-solution" id="' + id + '-body" hidden>' +
            sol.map(function (c) {
              if (c.type === "solution" || c.type === "verify") {
                return '<div class="label">' + esc(c.label || "Solution") + "</div>" +
                  '<div class="prose">' + runsHTML(c.runs) + "</div>";
              }
              if (c.type === "proof") {
                return '<div class="proof"><div class="prose">' + runsHTML(c.runs) + "</div></div>";
              }
              if (c.type === "display") return '<div class="display">' + runsHTML(c.runs) + "</div>";
              return '<div class="prose">' + runsHTML(c.runs) + "</div>";
            }).join("") + "</div>"
          : "") +
        "</article>";
    }

    const sampleCards = [
      { label: "Theorem", html: sampleCard(th, "theorem", { solution: true }) },
      { label: "Worked example", html: sampleCard(ex, "ex", { solution: true }) },
      { label: "Problem", html: sampleCard(pr, "prob", { solution: true }) }
    ].filter(function (c) { return !!c.html; });

    const secs = (ch.sections || []).slice(0, 3);
    box.innerHTML =
      '<div class="sample-tabs" role="tablist" aria-label="Live excerpt">' +
      sampleCards.map(function (c, i) {
        return '<button class="sample-tab' + (i === 1 ? " on" : "") + '" type="button" role="tab" data-sample-tab="' + i + '" aria-selected="' + (i === 1) + '">' + c.label + "</button>";
      }).join("") +
      "</div>" +
      '<div class="sample-stack">' + sampleCards.map(function (c) {
        return c.html;
      }).join("") + "</div>" +
      '<div class="sample-map">' +
      '<div class="sample-map-head"><span>Chapter ' + ch.num + " · " + (ch.sections || []).length + " sections</span>" +
      '<a href="reader.html#ch' + ch.num + '">Full chapter <span aria-hidden="true">↗</span></a></div>' +
      '<div class="sample-map-list">' +
      secs.map(function (s) {
        return '<a href="reader.html#ch' + ch.num + '">' +
          '<span class="sample-map-no">' + esc(s.num) + "</span>" +
          '<span class="sample-map-title">' + esc(s.title) + "</span>" +
          '<span class="sample-map-go" aria-hidden="true">→</span></a>';
      }).join("") +
      "</div></div>" +
      '<div class="sample-foot"><span>One chapter. Every proof and solution in reach.</span>' +
      '<a href="reader.html">Open the reader <span aria-hidden="true">→</span></a></div>';
    renderMath(box);

    const cards = $$(".sample-card", box);
    const tabs = $$(".sample-tab", box);
    function selectSample(i) {
      cards.forEach(function (card, j) { card.hidden = j !== i; });
      tabs.forEach(function (tab, j) {
        const on = j === i;
        tab.classList.toggle("on", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
        tab.tabIndex = on ? 0 : -1;
      });
    }
    selectSample(Math.min(1, cards.length - 1));

    box.addEventListener("click", function (e) {
      const tab = e.target.closest("[data-sample-tab]");
      if (!tab) return;
      selectSample(parseInt(tab.getAttribute("data-sample-tab"), 10));
    });

    box.addEventListener("click", function (e) {
      const btn = e.target.closest(".tcard-toggle");
      if (!btn) return;
      const card = btn.closest(".tcard");
      const body = document.getElementById(btn.getAttribute("aria-controls"));
      if (!card || !body) return;
      const open = body.hidden;
      body.hidden = !open;
      card.classList.toggle("open", open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      const label = btn.querySelector(".toggle-label");
      if (label) label.textContent = card.getAttribute(open ? "data-hide-label" : "data-show-label") ||
        (open ? "Hide solution" : "Show solution");
      const icon = btn.querySelector(".toggle-icon");
      if (icon) icon.classList.toggle("is-open", open);
      if (open) renderMath(body);
    });

    if (detail) {
      detail.innerHTML =
        '<div class="how-panel">' +
        '<div class="eyebrow">How it works</div>' +
        '<h3 class="how-title">A reader built for solving, not skimming.</h3>' +
        '<div class="stack" style="--gap:22px">' +
        [
          ["book", "The question stays in view", "Every problem statement is printed in full. Only the worked solution folds away — so you always know exactly what is being asked."],
          ["branch", "Four tiers of drill", "Warm-up → core applied → advanced synthesis → PhD research extensions, so the difficulty curve is explicit rather than implied."],
          ["copy", "Copy any formula", "Every display equation is live KaTeX. Hover it, hit the copy button, and take the LaTeX with you."],
          ["target", "Track your progress", "Your position and completion state are stored locally, so the treatise picks up exactly where you left it."]
        ].map(function (f) {
          return '<div class="how-row">' +
            '<div class="feat-icon">' + svg(ICONS[f[0]]) + "</div>" +
            '<div><h3>' + f[1] + "</h3>" +
            "<p>" + f[2] + "</p></div></div>";
        }).join("") +
        "</div>" +
        "</div>";
    }
  }

  /* -------------------------------------------------------------- init */
  function init() {
    if (!T) return;
    renderStats();
    renderHeroIndex();
    renderVolumes();
    renderFeatures();
    renderChapters();
    renderSample();
    // reveals that were injected after DOMContentLoaded
    $$(".reveal").forEach(function (el, i) {
      el.style.transitionDelay = (i % 8) * 50 + "ms";
    });
    const io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.04 });
    $$(".reveal").forEach(function (e) { io.observe(e); });
    requestAnimationFrame(function () {
      $$(".reveal").forEach(function (e) {
        const r = e.getBoundingClientRect();
        if (r.top < window.innerHeight * 1.05 && r.bottom > -50) {
          e.classList.add("in"); io.unobserve(e);
        }
      });
    });
    setTimeout(function () {
      $$(".reveal").forEach(function (e) {
        const r = e.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) e.classList.add("in");
      });
    }, 1400);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
