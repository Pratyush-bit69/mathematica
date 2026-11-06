/* =======================================================================
   MATHEMATICA — shared behaviour: theme, nav, reveals, global search
   ======================================================================= */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));

  /* ------------------------------------------------------------ titles */
  /* The source PDF repeats "Complete Theory, Proofs & Applications" in every
     chapter title. It is useful metadata but a terrible headline: split it
     into a clean title plus a deck, and strip it from cards and controls. */
  function titleParts(raw) {
    const full = String(raw == null ? "" : raw).replace(/\s+/g, " ").trim();
    const m = full.match(/^(.*?):\s*(Complete Theory, Proofs & Applications)\.?$/i);
    if (m) return { title: m[1].trim(), deck: m[2] };
    return { title: full, deck: "" };
  }
  function shortTitle(raw) { return titleParts(raw).title; }

  /* ------------------------------------------------------------- LaTeX */
  /* PDF reconstruction often glues adjacent \text groups together, turns
     "\in/" into \notin, and leaves an Omega glyph where \Omega belongs.
     Repair only unambiguous patterns so real formulas stay untouched. */
  const GLUE_WORDS = /^(a|an|and|are|as|at|be|by|cos|cot|csc|even|every|exp|for|from|gives|if|iff|in|is|lim|ln|log|max|min|not|odd|of|on|or|sec|sin|tan|the|then|to|where|with|arcsin|arccos|arctan|foci|vertices)$/i;

  function tidyTex(tex) {
    let out = String(tex || "")
      .replace(/\\in\//g, "\\notin ")
      .replace(/Ω/g, "\\Omega ")
      .replace(/\\bullet(?![a-zA-Z])/g, "\\bullet")
      /* R_d / R_k are PDF-loss subscripts for R^d / R^k. */
      .replace(/\\mathbb\{R\}_\{d\}/g, "\\mathbb{R}^{d}")
      .replace(/\\mathbb\{R\}_\{k\}/g, "\\mathbb{R}^{k}")
      /* Inverse notation lost its minus sign in the source. */
      .replace(/f\^\{1\}/g, "f^{-1}")
      /* PDF row-split artifacts: metric duplication commas and
         differential markers set as text. */
      .replace(/=,/g, "=")
      .replace(/,,/g, ",")
      .replace(/\\text\{d([a-zA-Z])\}/g, "\\mathrm{d}$1")
      .replace(/\\mathrm\{d\}(?![a-zA-Z\\{])/g, "\\mathrm{d}")
      /* A hyphenated English phrase set as math renders as a minus sign. */
      .replace(/\\ well-defined/g, "\\text{ well-defined}");

    // Adjacent text groups without any whitespace are almost always a lost
    // word boundary ("\text{in}\text{Roster}"); add an explicit math space.
    // Look ahead instead of consuming pairs so every boundary is inspected.
    out = out.replace(/(\\text\{([^{}]*)\})(?=\\text\{([^{}]*)\})/g, function (m, whole, a, b) {
      if (/\s$/.test(a) || /^\s/.test(b)) return m;
      const prose = /[^\S]/.test(a) || /[^\S]/.test(b) ||
        GLUE_WORDS.test(a.trim()) || GLUE_WORDS.test(b.trim());
      return whole + (prose ? "\\ " : "");
    });

    // A word group immediately followed by "(" needs the space inside the
    // group: math mode would otherwise discard it.
    out = out.replace(/\\text\{([^{}]*[A-Za-z0-9])\}\(/g, "\\text{$1 }(");
    out = out.replace(/\\text\{([^{}]*)\}\)([A-Za-z])/g, "\\text{$1})\\ $2");
    return out;
  }

  /* ------------------------------------------------------------ theme */
  const THEME_KEY = "mathematica:theme";
  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    const meta = $('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", t === "light" ? "#f7f3ea" : "#05080f");
    $$("[data-theme-icon]").forEach(function (el) {
      el.innerHTML = t === "light" ? SUN : MOON;
    });
  }
  const SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.4M12 19.6V22M4.2 4.2l1.7 1.7M18.1 18.1l1.7 1.7M2 12h2.4M19.6 12H22M4.2 19.8l1.7-1.7M18.1 5.9l1.7-1.7"/></svg>';
  const MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 14.6A8.6 8.6 0 0 1 9.4 3.5a8.6 8.6 0 1 0 11.1 11.1z"/></svg>';

  function initTheme() {
    let t = null;
    try { t = localStorage.getItem(THEME_KEY); } catch (e) { /* ignore */ }
    if (!t) t = "dark";          // dark is the signature look
    applyTheme(t);
    document.addEventListener("click", function (e) {
      const btn = e.target.closest("[data-theme-toggle]");
      if (!btn) return;
      const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
      applyTheme(next);
      try { localStorage.setItem(THEME_KEY, next); } catch (err) { /* ignore */ }
      document.dispatchEvent(new CustomEvent("themechange", { detail: next }));
    });
  }

  /* -------------------------------------------------------------- nav */
  function initNav() {
    const nav = $(".nav");
    if (!nav) return;

    /* Mark the current page so the navigation is never an undifferentiated
       row of links. */
    const here = (location.pathname.split("/").pop() || "index.html").toLowerCase();
    $$(".nav-links a").forEach(function (a) {
      const href = (a.getAttribute("href") || "").split("#")[0].toLowerCase();
      if (href && href === here) a.classList.add("active");
      else if (href === "reader.html" && here.indexOf("reader") === 0) a.classList.add("active");
    });

    /* A compact menu for tablets and phones. The tray is built from the
       page's own links, so every page keeps its own navigation. */
    const links = $(".nav-links");
    const tools = $(".nav-tools");
    if (links && tools && !$(".nav-menu-btn")) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "icon-btn nav-menu-btn";
      btn.setAttribute("aria-label", "Open menu");
      btn.setAttribute("aria-expanded", "false");
      btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
      tools.appendChild(btn);

      const tray = document.createElement("div");
      tray.className = "nav-tray";
      tray.setAttribute("aria-hidden", "true");
      tray.innerHTML = '<div class="nav-tray-inner">' +
        '<div class="nav-tray-head"><span>Navigate</span><button class="icon-btn" type="button" data-nav-close aria-label="Close menu"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>' +
        '<nav class="nav-tray-links">' +
        Array.prototype.map.call(links.querySelectorAll("a"), function (a) {
          const href = a.getAttribute("href");
          const active = a.classList.contains("active") ? " active" : "";
          return '<a class="' + active.trim() + '" href="' + href + '">' + escapeHtml(a.textContent.trim()) + '<span aria-hidden="true">→</span></a>';
        }).join("") +
        '<a class="nav-tray-support" href="https://www.buymeachai.in/pratyush" target="_blank" rel="noopener noreferrer">Buy Pratyush a chai<span aria-hidden="true">→</span></a>' +
        "</nav></div>";
      document.body.appendChild(tray);

      function setOpen(v) {
        document.body.classList.toggle("nav-open", v);
        btn.setAttribute("aria-expanded", v ? "true" : "false");
        btn.setAttribute("aria-label", v ? "Close menu" : "Open menu");
        tray.setAttribute("aria-hidden", v ? "false" : "true");
      }
      btn.addEventListener("click", function () {
        setOpen(!document.body.classList.contains("nav-open"));
      });
      tray.addEventListener("click", function (e) {
        if (e.target.closest("a") || e.target.closest("[data-nav-close]") || e.target === tray) setOpen(false);
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && document.body.classList.contains("nav-open")) setOpen(false);
      });
    }

    const onScroll = function () {
      nav.classList.toggle("scrolled", window.scrollY > 12);
      const top = $(".scroll-top");
      if (top) top.classList.toggle("show", window.scrollY > 700);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    const st = $(".scroll-top");
    if (st) {
      st.addEventListener("click", function () {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
  }

  /* ----------------------------------------------------------- reveals */
  function initReveals() {
    const els = $$(".reveal");
    if (!els.length) return;
    if (!("IntersectionObserver" in window)) {
      els.forEach(function (e) { e.classList.add("in"); });
      return;
    }
    const io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add("in");
          io.unobserve(en.target);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.06 });
    els.forEach(function (e, i) {
      e.style.transitionDelay = Math.min(i % 8, 7) * 55 + "ms";
      io.observe(e);
    });
    // safety: anything already on screen (or above it) is shown at once
    requestAnimationFrame(function () {
      els.forEach(function (e) {
        const r = e.getBoundingClientRect();
        if (r.top < window.innerHeight * 1.05 && r.bottom > -50) {
          e.classList.add("in");
          io.unobserve(e);
        }
      });
    });
    // and a last-resort sweep so nothing can stay invisible
    setTimeout(function () {
      els.forEach(function (e) {
        const r = e.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) e.classList.add("in");
      });
    }, 1200);
  }

  /* -------------------------------------------------------- card glow */
  function initCardGlow() {
    document.addEventListener("pointermove", function (e) {
      const card = e.target.closest(".card, .ch-card");
      if (!card) return;
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", ((e.clientX - r.left) / r.width) * 100 + "%");
      card.style.setProperty("--my", ((e.clientY - r.top) / r.height) * 100 + "%");
    }, { passive: true });
  }

  /* ----------------------------------------------------------- search */
  /* One index entry per card (statement + proof/solution together) and one
     per section's running prose. Indexing every raw block produced a dozen
     identical "§1.1" rows for a single query; grouping keeps results distinct
     and lets the title name the actual theorem or worked example. */
  const CARD_TYPES = { theorem: 1, example: 1, problem: 1, exam: 1 };
  const CARD_LABEL = {
    theorem: "Theorem", example: "Worked example", problem: "Problem", exam: "Exam"
  };

  function runsText(runs) {
    let txt = "";
    (runs || []).forEach(function (r) {
      if (r.k === "text") txt += r.v;
      else if (r.k === "math" && r.latex) txt += " " + Index.plain(r.latex) + " ";
    });
    return txt.replace(/\s+/g, " ").trim();
  }

  const Index = {
    entries: [],
    ready: false,
    build: function () {
      if (this.ready) return;
      const T = window.TREATISE;
      if (!T) return;
      const self = this;

      T.chapters.forEach(function (ch) {
        const chapterTitle = titleParts(ch.title).title;
        const chapterCtx = "Ch. " + ch.num;

        function push(entry) {
          if (!entry.body || entry.body.length < 3) return;
          self.entries.push(entry);
        }

        const intro = (ch.intro || []).map(function (b) { return runsText(b.runs); })
          .filter(Boolean).join(" ");
        if (intro) {
          push({
            title: chapterTitle,
            kicker: "Chapter opener",
            ctx: chapterCtx,
            body: intro,
            href: "reader.html#ch" + ch.num
          });
        }

        (ch.sections || []).forEach(function (sec) {
          const secHref = "reader.html#ch" + ch.num + "-" + sec.num.replace(/\./g, "-");
          const blocks = sec.blocks || [];
          const prose = [];

          for (let i = 0; i < blocks.length; i++) {
            const b = blocks[i];
            if (CARD_TYPES[b.type]) {
              /* A card owns every following non-card block: its statement,
                 proof, solution and verification. */
              const parts = [runsText(b.runs)];
              let j = i + 1;
              while (j < blocks.length && !CARD_TYPES[blocks[j].type]) {
                if (blocks[j].type !== "tier") parts.push(runsText(blocks[j].runs));
                j++;
              }
              const kind = CARD_LABEL[b.type];
              const label = kind + (b.num ? " " + b.num : "");
              const slug = String(b.num || "0").replace(/\./g, "-");
              push({
                title: b.title || label,
                kicker: label,
                ctx: chapterCtx + " · §" + sec.num,
                body: parts.filter(Boolean).join(" "),
                href: "reader.html#t-ch" + ch.num + "-" + b.type + "-" + slug
              });
              i = j - 1;
            } else if (b.type !== "tier") {
              const t = runsText(b.runs);
              if (t) prose.push(t);
            }
          }

          if (prose.length) {
            push({
              title: sec.title,
              kicker: "Section " + sec.num,
              ctx: chapterCtx + " · §" + sec.num,
              body: prose.join(" "),
              href: secHref
            });
          }
        });
      });
      this.ready = true;
    },
    query: function (q) {
      this.build();
      const s = q.trim().toLowerCase();
      if (s.length < 2) return [];
      const terms = s.split(/\s+/);
      const out = [];
      for (let i = 0; i < this.entries.length; i++) {
        const e = this.entries[i];
        const title = (e.kicker + " " + e.title).toLowerCase();
        const hay = title + " " + e.body.toLowerCase();
        let score = 0;
        let ok = true;
        for (let t = 0; t < terms.length; t++) {
          const p = hay.indexOf(terms[t]);
          if (p < 0) { ok = false; break; }
          score += 1;
          if (title.indexOf(terms[t]) >= 0) score += 7;
        }
        if (!ok) continue;
        out.push({ e: e, score: score, pos: hay.indexOf(terms[0]) });
      }
      out.sort(function (a, b) { return b.score - a.score; });
      const total = out.length;
      const items = out.slice(0, 40);
      items.total = total;
      return items;
    }
  };

  Index.plain = function (tex) {
    return String(tex)
      .replace(/\\[a-zA-Z]+/g, " ")
      .replace(/\\([{}(),;:!])/g, " $1 ")
      .replace(/[{}_^]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  };

  function highlight(text, q) {
    const terms = q.trim().split(/\s+/).filter(Boolean);
    let html = escapeHtml(text);
    terms.forEach(function (t) {
      const esc = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      html = html.replace(new RegExp("(" + esc + ")", "gi"), "<mark>$1</mark>");
    });
    return html;
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function initSearch() {
    const modal = $("#searchModal");
    if (!modal) return;
    const input = $("#searchInput");
    const results = $("#searchResults");
    let sel = 0;
    let current = [];

    function open() {
      modal.classList.add("open");
      document.body.style.overflow = "hidden";
      render(input.value);
      setTimeout(function () { input.focus(); input.select(); }, 40);
    }
    function close() {
      modal.classList.remove("open");
      document.body.style.overflow = "";
    }
    document.addEventListener("click", function (e) {
      if (e.target.closest("[data-search-open]")) { e.preventDefault(); open(); }
      if (e.target.closest("[data-search-close]")) { e.preventDefault(); close(); }
    });
    modal.addEventListener("click", function (e) { if (e.target === modal) close(); });

    function snippet(text, q, max) {
      const clean = String(text || "");
      const terms = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
      let p = -1;
      for (let i = 0; i < terms.length && p < 0; i++) p = clean.toLowerCase().indexOf(terms[i]);
      if (p <= 40) return clean.length > max ? clean.slice(0, max) + "…" : clean;
      const start = Math.max(0, p - 45);
      const end = Math.min(clean.length, start + max);
      return (start > 0 ? "…" : "") + clean.slice(start, end) + (end < clean.length ? "…" : "");
    }

    function setFoot(n, q) {
      const foot = $("#searchFoot");
      if (!foot) return;
      if (!q || q.trim().length < 2) foot.textContent = "Searches the full treatise";
      else if (!n) foot.textContent = "No results";
      else if (n > 40) foot.textContent = "40 of " + n + " results";
      else foot.textContent = n + " result" + (n === 1 ? "" : "s");
    }

    function render(q) {
      if (!q || q.trim().length < 2) {
        results.innerHTML = '<div class="modal-empty">Type at least two characters to search the entire treatise.</div>';
        current = []; sel = 0;
        setFoot(0, q);
        return;
      }
      current = Index.query(q);
      if (!current.length) {
        results.innerHTML = '<div class="modal-empty">No matches for “' + escapeHtml(q) + '”.</div>';
        setFoot(0, q);
        return;
      }
      results.innerHTML = current.map(function (r, i) {
        const body = snippet(r.e.body, q, 190);
        return '<a class="sr' + (i === sel ? " sel" : "") + '" href="' + r.e.href + '">' +
          '<div class="t"><span class="sr-kind">' + highlight(r.e.kicker, q) + '</span>' +
          '<span class="sr-title">' + highlight(r.e.title, q) + "</span></div>" +
          '<div class="c"><span class="badge badge-gold">' + escapeHtml(r.e.ctx) + "</span>" +
          '<span class="snippet">' + highlight(body, q) + "</span></div></a>";
      }).join("");
      setFoot(current.total == null ? current.length : current.total, q);
    }

    input.addEventListener("input", function () { sel = 0; render(input.value); });

    function move(d) {
      if (!current.length) return;
      sel = (sel + d + current.length) % current.length;
      const items = $$(".sr", results);
      items.forEach(function (el, i) { el.classList.toggle("sel", i === sel); });
      if (items[sel]) items[sel].scrollIntoView({ block: "nearest" });
    }

    document.addEventListener("keydown", function (e) {
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault(); open(); return;
      }
      if ((e.key === "/" || e.key === "'") && !/^(INPUT|TEXTAREA|SELECT)$/.test(
        document.activeElement.tagName) && !document.activeElement.isContentEditable) {
        e.preventDefault(); open(); return;
      }
      if (e.key === "Escape" && modal.classList.contains("open")) { close(); return; }
      if (!modal.classList.contains("open")) return;
      if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Enter") {
        e.preventDefault();
        const item = $$(".sr", results)[sel];
        if (item) { location.href = item.getAttribute("href"); close(); }
      }
    });
  }

  /* --------------------------------------------------------------- init */
  function init() {
    initTheme();
    initNav();
    initReveals();
    initCardGlow();
    initSearch();
    document.documentElement.classList.add("ready");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.Mathematica = {
    Index: Index,
    escapeHtml: escapeHtml,
    highlight: highlight,
    titleParts: titleParts,
    shortTitle: shortTitle,
    tidyTex: tidyTex
  };
})();
