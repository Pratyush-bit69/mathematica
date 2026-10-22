/* =======================================================================
   MATHEMATICA — landing page
   ======================================================================= */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));
  const T = window.TREATISE;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ====================================================== hero canvas */
  /* Two stacked layers:
     1. a background canvas redrawn every frame — aurora, a warped grid,
        rotating epitrochoid curves with a soft glow and drifting symbols;
     2. a trail canvas that is never cleared but slowly erased, so particles
        trace luminous Lissajous loops across the hero.                      */
  function heroCanvas() {
    const cv = $("#heroCanvas");
    const tc = $("#heroTrail");
    if (!cv || !tc) return;
    const ctx = cv.getContext("2d");
    const tctx = tc.getContext("2d");
    let W = 0, H = 0, dpr = 1;
    let raf = null;
    let running = true;
    let particles = [];
    let glyphs = [];
    let pointer = { x: 0, y: 0, tx: 0, ty: 0 };

    const GLYPHS = ["∫", "∑", "∏", "π", "√", "∂", "∇", "∞", "λ", "θ", "μ",
      "Δ", "Σ", "φ", "ψ", "ω", "∈", "⇒", "ℝ", "ℂ", "α", "β", "γ", "δ", "ε",
      "ζ", "ℤ", "ℚ", "∎", "≠", "≈", "≜"];

    const CURVES = [
      { a: 3, b: 2, r: 0.30, sp: 0.150, w: 1.5, c: "247,192,94" },
      { a: 5, b: 4, r: 0.38, sp: -0.110, w: 1.2, c: "139,123,247" },
      { a: 7, b: 5, r: 0.24, sp: 0.195, w: 1.1, c: "94,234,212" },
      { a: 2, b: 3, r: 0.44, sp: -0.075, w: 0.9, c: "244,190,120" }
    ];

    const LOOPS = [
      { a: 3, b: 2, k: 0.30 }, { a: 5, b: 4, k: 0.38 },
      { a: 7, b: 5, k: 0.24 }, { a: 4, b: 3, k: 0.42 },
      { a: 6, b: 5, k: 0.34 }, { a: 5, b: 3, k: 0.27 },
      { a: 9, b: 7, k: 0.20 }, { a: 8, b: 5, k: 0.36 }
    ];

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      const r = cv.getBoundingClientRect();
      W = r.width; H = r.height;
      [cv, tc].forEach(function (c) {
        c.width = Math.round(W * dpr);
        c.height = Math.round(H * dpr);
        c.getContext("2d").setTransform(dpr, 0, 0, dpr, 0, 0);
      });
      tctx.clearRect(0, 0, W, H);
      buildStatics();
      seed();
    }

    /* --- static layers, rasterised once and blitted afterwards ------- */
    const gridCv = $("#heroGrid");
    const glyphSprites = {}; // one small canvas per glyph

    function buildStatics() {
      // the warped polar grid is painted once; CSS turns the whole layer
      if (!gridCv) return;
      gridCv.width = Math.round(W * dpr);
      gridCv.height = Math.round(H * dpr);
      const g = gridCv.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      const cx = focus(), cy = H * 0.5, R = Math.min(W, H);
      g.strokeStyle = "rgba(148,176,214,0.11)";
      g.lineWidth = 1;
      g.beginPath();
      for (let ring = 1; ring <= 8; ring++) {
        for (let a = 0; a <= 64; a++) {
          const th = (a / 64) * Math.PI * 2;
          const rr = (ring / 8) * R * 0.98;
          const warp = 1 + 0.15 * Math.sin(th * 3) * Math.cos(rr * 0.012);
          const x = cx + Math.cos(th) * rr * warp;
          const y = cy + Math.sin(th) * rr * warp * 0.74;
          if (a === 0) g.moveTo(x, y); else g.lineTo(x, y);
        }
      }
      for (let sp = 0; sp < 20; sp++) {
        const th = (sp / 20) * Math.PI * 2;
        for (let k = 0; k <= 30; k++) {
          const rr = (k / 30) * R * 0.98;
          const warp = 1 + 0.15 * Math.sin(th * 3) * Math.cos(rr * 0.012);
          const x = cx + Math.cos(th) * rr * warp;
          const y = cy + Math.sin(th) * rr * warp * 0.74;
          if (k === 0) g.moveTo(x, y); else g.lineTo(x, y);
        }
      }
      g.stroke();
    }

    function glyphSprite(ch, size) {
      const key = ch + "|" + size;
      if (glyphSprites[key]) return glyphSprites[key];
      const c = document.createElement("canvas");
      const pad = 6;
      c.width = c.height = Math.ceil(size + pad * 2);
      const g = c.getContext("2d");
      g.font = size + "px 'KaTeX_Main', 'Newsreader', Georgia, serif";
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillStyle = "#fff";
      g.fillText(ch, c.width / 2, c.height / 2);
      glyphSprites[key] = c;
      return c;
    }

    /* --- pre-rendered glow sprites (one per tint) --------------------- */
    const SPRITES = {};
    function sprite(rgb) {
      if (SPRITES[rgb]) return SPRITES[rgb];
      const s = 64;
      const c = document.createElement("canvas");
      c.width = c.height = s;
      const g = c.getContext("2d");
      const grd = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
      grd.addColorStop(0, "rgba(" + rgb + ",1)");
      grd.addColorStop(0.18, "rgba(" + rgb + ",0.42)");
      grd.addColorStop(0.45, "rgba(" + rgb + ",0.12)");
      grd.addColorStop(1, "rgba(" + rgb + ",0)");
      g.fillStyle = grd;
      g.fillRect(0, 0, s, s);
      SPRITES[rgb] = c;
      return c;
    }
    ["247,192,94", "139,123,247", "94,234,212"].forEach(sprite);

    function seed() {
      const small = W < 760;
      const n = small ? 54 : 132;
      particles = [];
      for (let i = 0; i < n; i++) {
        const loop = LOOPS[i % LOOPS.length];
        particles.push({
          loop: loop,
          ph: Math.random() * Math.PI * 2,
          sp: 0.16 + Math.random() * 0.22,
          k: loop.k * (0.62 + Math.random() * 0.55),
          xo: (Math.random() - 0.5) * 0.5,
          yo: (Math.random() - 0.5) * 0.5,
          sz: 0.55 + Math.random() * 1.5,
          a: 0.10 + Math.random() * 0.34,
          hue: Math.random() < 0.62 ? "247,192,94"
            : (Math.random() < 0.6 ? "139,123,247" : "94,234,212")
        });
      }
      const g = small ? 9 : 18;
      glyphs = [];
      for (let i = 0; i < g; i++) {
        glyphs.push({
          x: Math.random() * W,
          y: Math.random() * H,
          ch: GLYPHS[(Math.random() * GLYPHS.length) | 0],
          size: 14 + Math.random() * 30,
          a: 0.035 + Math.random() * 0.075,
          vy: -0.05 - Math.random() * 0.13,
          vx: (Math.random() - 0.5) * 0.08,
          ph: Math.random() * Math.PI * 2,
          rot: (Math.random() - 0.5) * 0.4
        });
      }
    }

    /* the visual centre of the field — right of the headline on desktop */
    function focus() {
      return W < 760 ? W * 0.5 : W * 0.715;
    }

    function glow(x, y, r, rgb, a) {
      const s = sprite(rgb);
      tctx.globalAlpha = a;
      tctx.drawImage(s, x - r, y - r, r * 2, r * 2);
      tctx.globalAlpha = 1;
    }

    function drawTrails(t) {
      // slowly erase what is already there so the paths leave fading trails
      tctx.globalCompositeOperation = "destination-out";
      tctx.fillStyle = "rgba(0,0,0,0.030)";
      tctx.fillRect(0, 0, W, H);
      tctx.globalCompositeOperation = "lighter";

      const cx = focus() + pointer.x * 16;
      const cy = H * 0.5 + pointer.y * 12;
      const R = Math.min(W, H) * 0.5;

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        const th = t * p.sp + p.ph;
        const lx = Math.sin(p.loop.a * th);
        const ly = Math.sin(p.loop.b * th);
        const x = cx + (lx + p.xo) * p.k * R * 2;
        const y = cy + (ly + p.yo) * p.k * R * 1.25;
        if (x < -40 || x > W + 40 || y < -40 || y > H + 40) continue;
        const tw = 0.55 + 0.45 * Math.sin(t * 0.0021 * (1 + p.sp) + p.ph);
        glow(x, y, p.sz * 6.5, p.hue, 0.10 * tw * p.a * 2.2);
        tctx.beginPath();
        tctx.arc(x, y, p.sz * tw * 0.85, 0, Math.PI * 2);
        tctx.fillStyle = "rgba(" + p.hue + "," + (0.34 + 0.55 * p.a) * tw + ")";
        tctx.fill();
      }
      tctx.globalCompositeOperation = "source-over";
    }

    function drawBackground(t) {
      ctx.clearRect(0, 0, W, H);
      const cx = focus() + pointer.x * 16;
      const cy = H * 0.5 + pointer.y * 12;
      const R = Math.min(W, H);

      // ---- the warped grid lives on its own static layer

      // ---- rotating epitrochoid curves
      CURVES.forEach(function (cv2) {
        const rot = t * 0.00006 * cv2.sp * 1000;
        const grad = ctx.createLinearGradient(cx - R, cy - R, cx + R, cy + R);
        grad.addColorStop(0, "rgba(" + cv2.c + ",0)");
        grad.addColorStop(0.3, "rgba(" + cv2.c + ",0.40)");
        grad.addColorStop(0.64, "rgba(" + cv2.c + ",0.14)");
        grad.addColorStop(1, "rgba(" + cv2.c + ",0)");
        ctx.beginPath();
        for (let i = 0; i <= 150; i++) {
          const th = (i / 150) * Math.PI * 2;
          const rr = Math.cos(cv2.a * th + rot * 3) * 0.62 +
            Math.cos((cv2.a - cv2.b) * th - rot * 2) * 0.38;
          const x = cx + rr * Math.cos(th + rot) * R * cv2.r * 2.1;
          const y = cy + rr * Math.sin(th + rot) * R * cv2.r * 1.55;
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.strokeStyle = grad;
        ctx.lineWidth = cv2.w;
        ctx.stroke();
      });

      // ---- drifting symbols
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (let i = 0; i < glyphs.length; i++) {
        const g = glyphs[i];
        g.y += g.vy; g.x += g.vx; g.ph += 0.011;
        if (g.y < -70) { g.y = H + 50; g.x = Math.random() * W; }
        if (g.x < -70) g.x = W + 50;
        if (g.x > W + 70) g.x = -50;
        const pulse = 0.45 + 0.55 * Math.sin(g.ph);
        const near = Math.max(0, 1 - Math.abs(g.x - cx) / (W * 0.6));
        const sp = glyphSprite(g.ch, Math.round(g.size));
        ctx.globalAlpha = g.a * pulse * (0.35 + near);
        ctx.drawImage(sp, g.x - sp.width / 2, g.y - sp.height / 2);
      }
      ctx.globalAlpha = 1;
    }

    function frame(ts) {
      if (!running) return;
      const t = ts || 0;
      pointer.x += (pointer.tx - pointer.x) * 0.045;
      pointer.y += (pointer.ty - pointer.y) * 0.045;
      drawBackground(t);
      drawTrails(t);
      raf = requestAnimationFrame(frame);
    }

    resize();
    let rt = null;
    window.addEventListener("resize", function () {
      clearTimeout(rt);
      rt = setTimeout(resize, 160);
    });
    window.addEventListener("pointermove", function (e) {
      pointer.tx = (e.clientX / window.innerWidth - 0.5) * 2;
      pointer.ty = (e.clientY / window.innerHeight - 0.5) * 2;
    }, { passive: true });
    raf = requestAnimationFrame(frame);

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { running = false; cancelAnimationFrame(raf); }
      else if (!running) { running = true; raf = requestAnimationFrame(frame); }
    });

    const io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting && running) {
          running = false; cancelAnimationFrame(raf);
        } else if (e.isIntersecting && !running) {
          running = true; raf = requestAnimationFrame(frame);
        }
      });
    });
    io.observe(cv);
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
      [solved, "Solved"],
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
      " solved problems · " + s.pages + " pages";
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

  function renderVolumes() {
    const g = $("#volumeGrid");
    if (!g) return;
    g.innerHTML = T.volumes.map(function (v) {
      const names = v.chapters.map(function (c) {
        const ch = T.chapters.filter(function (x) { return x.num === c; })[0];
        return '<a href="reader.html#ch' + c + '" title="' + (ch ? ch.title : "") + '">Ch ' + c + "</a>";
      }).join("");
      return '<div class="vol reveal">' +
        '<div class="vol-num">' + v.roman + "</div>" +
        '<h3>' + v.name + "</h3>" +
        "<p>" + v.blurb + "</p>" +
        '<div class="vol-chapters">' + names + "</div>" +
        "</div>";
    }).join("");
  }

  const FEATURES = [
    { i: "book", t: "Proof-driven throughout",
      d: "Every theorem states its hypotheses, proves its claim line by line, and is immediately reused.",
      m: "\\text{Theorem } 1.1:\\; (A\\cup B)^{c}=A^{c}\\cap B^{c}" },
    { i: "check", t: "720 fully solved problems",
      d: "Graded in four tiers from warm-up drills to PhD-level quant research extensions — with every derivation shown.",
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
    g.innerHTML = FEATURES.map(function (f) {
      return '<div class="card feat reveal">' +
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

    function card(c) {
      const n = counts[c.num];
      const desc = c.sections.length
        ? c.sections[0].title + " · " + (c.sections.length - 1) + " more"
        : "";
      return '<a class="ch-card reveal" data-volume="' + c.volume + '" href="reader.html#ch' + c.num + '">' +
        '<div class="n">CHAPTER ' + String(c.num).padStart(2, "0") + " · VOL " + ["I", "II", "III", "IV"][c.volume - 1] + "</div>" +
        "<h3>" + c.title + "</h3>" +
        "<p>" + desc + "</p>" +
        '<div class="meta">' +
        (n.ex ? "<span><b>" + n.ex + "</b> examples</span>" : "") +
        (n.pr ? "<span><b>" + n.pr + "</b> problems</span>" : "") +
        (n.th ? "<span><b>" + n.th + "</b> proof</span>" : "") +
        "<span><b>" + c.sections.length + "</b> sections</span>" +
        "</div></a>";
    }
    function paint(filter) {
      g.innerHTML = T.chapters.filter(function (c) {
        return filter === "all" || String(c.volume) === filter;
      }).map(card).join("");
      $$(".reveal", g).forEach(function (el, i) {
        el.style.transitionDelay = (i % 9) * 40 + "ms";
        requestAnimationFrame(function () { el.classList.add("in"); });
      });
      $("#chCount").textContent = g.children.length + " chapters";
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
    let th = null, ex = null, pr = null, prBody = null;
    (ch.sections || []).forEach(function (s) {
      const bl = s.blocks || [];
      bl.forEach(function (b, i) {
        if (b.type === "theorem" && !th) th = b;
        if (b.type === "example" && !ex) ex = b;
        if (b.type === "problem" && !pr) {
          pr = b;
          for (let j = i + 1; j < bl.length; j++) {
            if (bl[j].type === "question" || bl[j].type === "solution") {
              prBody = bl[j];
              break;
            }
            if (bl[j].type === "problem" || bl[j].type === "example") break;
          }
        }
      });
    });

    function renderRuns(runs) {
      return (runs || []).map(function (r) {
        if (r.k === "text") return '<span class="tx">' + esc(r.v) + "</span>";
        if (r.k === "br") return "<br>";
        return '<span class="mx" data-tex="' + esc(r.latex) + '"></span>';
      }).join("");
    }

    function card(b, kind, body) {
      if (!b) return "";
      return '<div class="tcard ' + kind + '" style="margin-bottom:14px">' +
        '<div class="tcard-head" style="cursor:default">' +
        '<span class="tcard-kind">' + kind.toUpperCase() + "</span>" +
        '<span class="tcard-txt"><span class="tcard-num">' + b.num + "</span>" +
        "<h4>" + esc(b.title) + "</h4></span></div>" +
        '<div class="tcard-body" style="display:block">' +
        (b.runs && b.runs.length
          ? '<div class="prose">' + renderRuns(b.runs) + "</div>" : "") +
        (body ? '<div class="prose">' + renderRuns(body.runs) + "</div>" : "") +
        "</div></div>";
    }

    box.innerHTML =
      '<div class="eyebrow">Chapter 1 — a live excerpt</div>' +
      card(th, "theorem") + card(ex, "ex") + card(pr, "prob", prBody);
    renderMath(box);

    if (detail) {
      detail.innerHTML =
        '<div class="panel panel-pad" style="height:100%">' +
        '<div class="eyebrow">How it works</div>' +
        '<div class="stack" style="--gap:22px">' +
        [
          ["book", "Theorems unfold", "Tap any theorem, worked example or problem and its proof or solution expands in place. Nothing is hidden behind a page turn."],
          ["branch", "Four tiers of drill", "Warm-up → core applied → advanced synthesis → PhD research extensions, so the difficulty curve is explicit rather than implied."],
          ["copy", "Copy any formula", "Every display equation is live KaTeX. Hover it and hit ⌘C to take the LaTeX with you."],
          ["target", "Track your progress", "Your position and completion state are stored locally, so the treatise picks up exactly where you left it."]
        ].map(function (f) {
          return '<div style="display:flex;gap:15px;align-items:flex-start">' +
            '<div class="feat-icon" style="width:36px;height:36px;margin:0;flex:none;border-radius:10px">' +
            svg(ICONS[f[0]]) + "</div>" +
            "<div><h3 style='font-size:1rem;margin-bottom:4px'>" + f[1] + "</h3>" +
            "<p style='font-size:0.9rem;color:var(--fg-mute);margin:0;line-height:1.6'>" + f[2] + "</p></div></div>";
        }).join("") +
        "</div>" +
        '<a class="btn btn-primary" href="reader.html" style="margin-top:26px">Open the reader</a>' +
        "</div>";
    }
  }

  /* -------------------------------------------------------------- init */
  function init() {
    if (!T) return;
    heroCanvas();
    renderStats();
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
