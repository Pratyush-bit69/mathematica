/* =======================================================================
   MATHEMATICA — reader
   ======================================================================= */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));
  const T = window.TREATISE;
  if (!T) return;

  const M = window.Mathematica || {};
  const titleParts = M.titleParts || function (t) {
    return { title: String(t || ""), deck: "" };
  };

  const DONE_KEY = "mathematica:read";
  let done = {};
  try { done = JSON.parse(localStorage.getItem(DONE_KEY) || "{}"); } catch (e) { done = {}; }

  let chapters = T.chapters.slice();
  let current = 0;

  /* ---------------------------------------------------------- helpers */
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  const KIND = {
    theorem: "Theorem", example: "Worked example", problem: "Problem",
    exam: "Exam", proof: "Proof", solution: "Solution", para: "",
    bullet: "", display: "", tier: "", section: ""
  };

  const CARD = { theorem: 1, example: 1, problem: 1, exam: 1 };
  const STATEMENT_BLOCKS = { display: 1, para: 1, bullet: 1 };

  /* Clean the handful of systematic LaTeX artefacts left by the PDF
     reconstruction. These are display-level fixes only — the stored source
     data stays untouched so it can still be rebuilt from the PDF. */
  function tidyTex(tex) {
    return window.Mathematica && window.Mathematica.tidyTex
      ? window.Mathematica.tidyTex(tex)
      : String(tex || "");
  }

  /* Some PDF-reconstructed "math" runs are really long text lines. KaTeX sets
     them in an unbreakable box; mark only those as scrollable so ordinary
     inline formulas keep their natural baseline flow. */
  function isWideMath(tex) {
    return String(tex || "").length > 90 ||
      /\\text\{[^{}]{50,}\}/.test(tex) ||
      /\\mathrm\{[^{}]{50,}\}/.test(tex);
  }

  /* PDF reconstruction routinely drops the space at a text↔math boundary,
     producing strings such as "Product Aand 45". Put the space back when the
     adjacent character is a word character; punctuation stays untouched. */
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

  /* -------------------------------------------------- block rendering */
  function renderRuns(runs) {
    if (!runs || !runs.length) return "";
    return spacedRuns(runs).map(function (r) {
      if (!r) return "";
      if (r.k === "br") return '<br class="run-break">';
      if (r.k === "text") {
        const t = esc(r.v);
        return r.b ? "<strong>" + t + "</strong>" : t;
      }
      const tex = tidyTex(r.latex);
      if (/^\\bullet$/.test(tex.trim())) {
        return '<span class="run-bullet" aria-hidden="true">•</span>';
      }
      return '<span class="mx' + (isWideMath(tex) ? " mx-wide" : "") +
        '" data-tex="' + esc(tex) + '"></span>';
    }).join("");
  }

  function hasText(runs) {
    return (runs || []).some(function (r) {
      return r.k === "text" && r.v && r.v.trim().length > 1;
    });
  }

  /* A display equation can be the end of a sentence. If the question is
     split across a text line and a centred equation, don't leave a lonely
     full stop dangling at the end of the prose. */
  function trimDanglingPeriod(runs, followedByDisplay) {
    if (!followedByDisplay || !runs || !runs.length) return runs;
    const out = runs.slice();
    const last = out[out.length - 1];
    if (!last) return out;
    if (last.k === "math" && /^\s*\.\s*$/.test(tidyTex(last.latex))) {
      out.pop();
      return out;
    }
    if (last.k === "text") {
      const t = last.v.replace(/\s+\.\s*$/, "");
      if (t !== last.v) out[out.length - 1] = Object.assign({}, last, { v: t });
    }
    return out;
  }

  function blockHTML(b) {
    switch (b.type) {
      case "para":
        return '<p class="prose">' + renderRuns(b.runs) + "</p>";
      case "bullet":
        return '<div class="bullet"><span class="mk" aria-hidden="true"></span><div class="tx prose">' +
          renderRuns(b.runs) + "</div></div>";
      case "display":
        return '<div class="display">' + renderRuns(b.runs) + "</div>";
      case "tier":
        return '<div class="tier"><span class="tier-mark" aria-hidden="true">§</span>' + esc(b.title) + "</div>";
      case "proof":
        return '<div class="proof">' +
          (b.title ? '<div class="ptitle">' + esc(b.title) + "</div>" : "") +
          '<div class="prose">' + renderRuns(b.runs) + "</div></div>";
      case "solution":
        return '<div class="label">' + esc(b.label || "Solution") + "</div>" +
          '<div class="prose">' + renderRuns(b.runs) + "</div>";
      case "question":
      case "verify":
        return '<div class="label">' + esc(b.label || "Question") + "</div>" +
          '<div class="prose">' + renderRuns(b.runs) + "</div>";
      default:
        return "";
    }
  }

  /* ------------------------------------------------------- card anatomy */
  function cardParts(b) {
    const kids = b.children || [];
    let qIndex = -1;
    for (let i = 0; i < kids.length; i++) {
      if (kids[i].type === "question") { qIndex = i; break; }
    }

    let statement = b.runs || [];
    let lead = [];
    let restStart = 0;

    if (b.statement && b.statement.length) {
      /* Curated statement: the PDF reconstruction of the surrounding
         fraction rows is unreliable, so use the clean source wording. */
      statement = b.statement;
      restStart = qIndex >= 0 ? qIndex + 1 : 0;
      while (restStart < kids.length && STATEMENT_BLOCKS[kids[restStart].type]) {
        restStart++;
      }
    } else if (qIndex >= 0) {
      /* Worked examples in the source carry their statement in a run-in
         "Problem:" block. Use that instead of the heading formula. Any
         display sitting above the question belongs with the statement. */
      statement = kids[qIndex].runs || [];
      if (!hasText(statement) && hasText(b.runs)) statement = b.runs;
      lead = kids.slice(0, qIndex).filter(function (c) {
        return STATEMENT_BLOCKS[c.type];
      });
      restStart = qIndex + 1;
      while (restStart < kids.length && STATEMENT_BLOCKS[kids[restStart].type]) {
        lead.push(kids[restStart]);
        restStart++;
      }
    } else {
      /* A problem's equation is often laid out below its sentence. Keep
         every display/paragraph before the solution with the statement so
         the question is complete while the card is closed. */
      let i = 0;
      while (i < kids.length && STATEMENT_BLOCKS[kids[i].type]) {
        lead.push(kids[i]);
        i++;
      }
      restStart = i;
    }

    /* Drop empty "Solution:" stubs, but keep a solution if it has a display
       beneath it. The remainder is the expandable proof/derivation. */
    const solution = kids.slice(restStart).filter(function (c) {
      return c.type === "solution" || c.type === "proof" ||
        c.type === "verify" || c.type === "display" ||
        c.type === "para" || c.type === "bullet";
    });

    const leadHasDisplay = lead.some(function (c) { return c.type === "display"; });
    statement = trimDanglingPeriod(statement, leadHasDisplay);

    const hasSolution = solution.length > 0;
    const isProof = b.type === "theorem" || solution.some(function (c) { return c.type === "proof"; });

    return {
      statement: statement,
      lead: lead,
      solution: solution,
      hasSolution: hasSolution,
      isProof: isProof
    };
  }

  function solutionHTML(parts) {
    if (!parts.solution.length) return "";
    return parts.solution.map(function (c) {
      if (c.type === "solution" || c.type === "verify") {
        return '<div class="label' + (c.type === "verify" ? " label-verify" : "") + '">' +
          esc(c.label || (c.type === "verify" ? "Verification" : "Solution")) + "</div>" +
          '<div class="prose">' + renderRuns(c.runs) + "</div>";
      }
      return blockHTML(c);
    }).join("");
  }

  function cardHTML(b, chNum) {
    const kind = b.type === "exam" ? "exam" : b.type === "example" ? "ex" :
      b.type === "problem" ? "prob" : "theorem";
    const parts = cardParts(b);
    const num = String(b.num || "").replace(/\./g, "-");
    const titleId = "t-ch" + chNum + "-" + b.type + "-" + num;
    const bodyId = "b-" + b.type + "-" + num;
    const toggleLabel = parts.isProof ? "Show proof" : "Show solution";
    const hideLabel = parts.isProof ? "Hide proof" : "Hide solution";

    const statement =
      '<div class="tcard-statement">' +
      (parts.statement.length ? '<div class="prose">' + renderRuns(parts.statement) + "</div>" : "") +
      parts.lead.map(blockHTML).join("") +
      "</div>";

    const control = parts.hasSolution
      ? '<div class="tcard-control">' +
        '<button class="tcard-toggle" type="button" aria-expanded="false" aria-controls="' + bodyId + '">' +
        '<span class="toggle-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg></span>' +
        '<span class="toggle-label">' + toggleLabel + "</span>" +
        '<span class="toggle-hint">' + (parts.isProof ? "in full" : "step by step") + "</span>" +
        "</button></div>"
      : "";

    const body = parts.hasSolution
      ? '<div class="tcard-solution" id="' + bodyId + '" hidden>' + solutionHTML(parts) + "</div>"
      : "";

    return '<section class="tcard ' + kind + '" id="' + titleId + '" data-card="1" data-hide-label="' + hideLabel + '" data-show-label="' + toggleLabel + '">' +
      '<header class="tcard-head">' +
      '<span class="tcard-kind">' + (KIND[b.type] || b.type) + "</span>" +
      (b.num ? '<span class="tcard-num">' + esc(b.num) + "</span>" : "") +
      '<h4 class="tcard-title">' + esc(b.title) + "</h4>" +
      "</header>" +
      statement + control + body +
      "</section>";
  }

  /* ------------------------------------------------------- chapter view */
  function groupBlocks(blocks) {
    /* Attach everything that follows a card — its statement, proof,
       solution and verification — into that card. */
    const out = [];
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      if (CARD[b.type]) {
        const kids = [];
        let j = i + 1;
        while (j < blocks.length && !CARD[blocks[j].type] &&
               blocks[j].type !== "section" && blocks[j].type !== "tier") {
          kids.push(blocks[j]);
          j++;
        }
        out.push({
          type: b.type, num: b.num, title: b.title, runs: b.runs,
          statement: b.statement, children: kids, open: b.open
        });
        i = j - 1;
      } else {
        out.push(b);
      }
    }
    return out;
  }

  function chapterHTML(ch) {
    const vol = ["I", "II", "III", "IV"][ch.volume - 1];
    const tp = titleParts(ch.title);
    const counts = { ex: 0, pr: 0, th: 0 };
    (ch.sections || []).forEach(function (s) {
      (s.blocks || []).forEach(function (b) {
        if (b.type === "example") counts.ex++;
        else if (b.type === "problem" || b.type === "exam") counts.pr++;
        else if (b.type === "theorem") counts.th++;
      });
    });

    let html = '<header class="ch-head" id="ch' + ch.num + '">' +
      '<div class="ch-topline"><span class="vol-pill">Volume ' + vol + " · Chapter " + ch.num + "</span>" +
      (ch.page ? '<span class="ch-page">p. ' + ch.page + "</span>" : "") + "</div>" +
      "<h1>" + esc(tp.title) + "</h1>" +
      (tp.deck ? '<p class="ch-deck">' + esc(tp.deck) + "</p>" : "") +
      '<div class="ch-kpis">' +
      '<div><b>' + (ch.sections || []).length + "</b><span>sections</span></div>" +
      (counts.th ? '<div><b>' + counts.th + "</b><span>formal proof" + (counts.th > 1 ? "s" : "") + "</span></div>" : "") +
      (counts.ex ? '<div><b>' + counts.ex + "</b><span>worked examples</span></div>" : "") +
      (counts.pr ? '<div><b>' + counts.pr + "</b><span>solved problems</span></div>" : "") +
      "</div></header>";

    (ch.sections || []).forEach(function (sec) {
      const sid = "ch" + ch.num + "-" + sec.num.replace(/\./g, "-");
      html += '<section class="sec-head" id="' + sid + '">' +
        '<h2><span class="sno">' + esc(sec.num) + "</span>" + esc(sec.title) + "</h2>" +
        '<div class="rule"></div></section>';
      html += '<div class="prose">' + groupBlocks(sec.blocks || []).map(function (b) {
        if (CARD[b.type]) return cardHTML(b, ch.num);
        return blockHTML(b);
      }).join("") + "</div>";
    });

    return html;
  }

  /* ------------------------------------------------------------- TOC */
  function buildTOC() {
    const nav = $("#tocNav");
    let html = "";
    let lastVol = null;
    chapters.forEach(function (ch) {
      if (ch.volume !== lastVol) {
        lastVol = ch.volume;
        const v = T.volumes.filter(function (x) { return x.id === ch.volume; })[0];
        html += '<a class="vol">Volume ' + (v ? v.roman : ch.volume) + "</a>";
      }
      html += '<a href="#ch' + ch.num + '" data-ch="' + ch.num + '">' +
        '<span class="dot" aria-hidden="true"></span><span class="tno">' + ch.num + "</span>" +
        "<span>" + esc(titleParts(ch.title).title) + "</span></a>";
      (ch.sections || []).forEach(function (sec) {
        html += '<a class="sec" href="#ch' + ch.num + "-" + sec.num.replace(/\./g, "-") +
          '" data-sec="ch' + ch.num + "-" + sec.num.replace(/\./g, "-") + '">' +
          esc(sec.num) + " · " + esc(sec.title) + "</a>";
      });
    });
    nav.innerHTML = html;
  }

  function buildRail() {
    const list = $("#railList");
    const ch = chapters[current];
    if (!ch) return;
    list.innerHTML = (ch.sections || []).map(function (sec) {
      const sid = "ch" + ch.num + "-" + sec.num.replace(/\./g, "-");
      return '<li><a href="#' + sid + '" data-rail="' + sid + '">' +
        esc(sec.num) + " · " + esc(sec.title) + "</a></li>";
    }).join("");
    const counts = { ex: 0, pr: 0, th: 0, disp: 0 };
    (ch.sections || []).forEach(function (s) {
      (s.blocks || []).forEach(function (b) {
        if (b.type === "example") counts.ex++;
        else if (b.type === "problem" || b.type === "exam") counts.pr++;
        else if (b.type === "theorem") counts.th++;
        else if (b.type === "display") counts.disp++;
      });
    });
    $("#railStats").innerHTML =
      "<div>" + counts.ex + " worked examples</div>" +
      "<div>" + counts.pr + " solved problems</div>" +
      "<div>" + counts.th + " formal proofs</div>" +
      "<div>" + counts.disp + " display equations</div>";
  }

  /* ------------------------------------------------------- navigation */
  function showChapter(idx, pushHash) {
    idx = Math.max(0, Math.min(chapters.length - 1, idx));
    current = idx;
    const ch = chapters[idx];
    const content = $("#content");
    content.innerHTML = chapterHTML(ch);
    renderMath(content);
    syncAllLabels();
    buildRail();
    $$("[data-ch]").forEach(function (a) {
      a.classList.toggle("active", +a.getAttribute("data-ch") === ch.num);
    });
    $$("[data-ch]").forEach(function (a) {
      a.classList.toggle("done", !!done[a.getAttribute("data-ch")]);
    });
    $("#prevCh").disabled = idx === 0;
    $("#nextCh").disabled = idx === chapters.length - 1;
    $("#markRead").textContent = done[ch.num] ? "✓ Chapter read" : "Mark chapter read";
    const root = document.documentElement;
    const prevBehavior = root.style.scrollBehavior;
    root.style.scrollBehavior = "auto";
    window.scrollTo(0, 0);
    root.style.scrollBehavior = prevBehavior;
    if (pushHash !== false) {
      history.replaceState(null, "", "#ch" + ch.num);
    }
    document.title = "Ch. " + ch.num + " · " + titleParts(ch.title).title + " — MATHEMATICA";
  }

  /* Long text-as-math runs can still be narrower than the 90-character
     heuristic and yet wider than a phone column. Measure what KaTeX actually
     set and cap only the inline formulas that overflow their own paragraph. */
  function containWideMath(root) {
    if (!root) return;
    $$(".mx", root).forEach(function (el) {
      if (el.classList.contains("mx-wide")) return;
      if (el.closest(".display, .katex-display")) return;
      const host = el.parentElement;
      if (!host || !host.clientWidth) return;
      const rect = el.getBoundingClientRect();
      if (rect.width > host.clientWidth + 1) el.classList.add("mx-wide");
    });
  }

  /* --------------------------------------------------------- math render */
  function renderMath(root) {
    if (!window.katex) return;
    $$(".mx", root).forEach(function (el) {
      const tex = tidyTex(el.getAttribute("data-tex"));
      try {
        katex.render(tex, el, {
          throwOnError: false,
          displayMode: false,
          strict: false,
          trust: false
        });
        el.setAttribute("title", tex);
      } catch (e) {
        el.textContent = tex;
      }
    });
    containWideMath(root);
    // copy-LaTeX affordance on display equations
    $$(".display", root).forEach(function (d) {
      if (d.querySelector(".copy-tex")) return;
      const b = document.createElement("button");
      b.className = "copy-tex";
      b.type = "button";
      b.title = "Copy LaTeX";
      b.setAttribute("aria-label", "Copy the LaTeX of this equation");
      b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 012-2h8"/></svg>';
      b.addEventListener("click", function (e) {
        e.stopPropagation();
        const latex = collectLatex(d);
        copy(latex || d.textContent);
        b.classList.add("done");
        setTimeout(function () { b.classList.remove("done"); }, 1200);
      });
      d.appendChild(b);
    });
  }

  function collectLatex(node) {
    const els = node.querySelectorAll(".mx");
    if (!els.length) return "";
    let s = "";
    els.forEach(function (el) {
      const t = el.getAttribute("data-tex");
      s += (s ? " " : "") + t;
    });
    return s;
  }

  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(function () { fallback(text); });
    } else fallback(text);
  }
  function fallback(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
  }

  /* ------------------------------------------------------ interactions */
  function setCardOpen(card, open) {
    const btn = card.querySelector(".tcard-toggle");
    const body = card.querySelector(".tcard-solution");
    if (!btn || !body) return;
    card.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    body.hidden = !open;
    const label = card.getAttribute(open ? "data-hide-label" : "data-show-label");
    const text = btn.querySelector(".toggle-label");
    if (text) text.textContent = label || (open ? "Hide solution" : "Show solution");
    const icon = btn.querySelector(".toggle-icon");
    if (icon) icon.classList.toggle("is-open", open);
    if (open) containWideMath(card);
  }

  function syncAllLabels() {
    const cards = $$(".tcard");
    const allOpen = cards.length > 0 && !cards.some(function (c) {
      return !c.classList.contains("open");
    });
    const all = $("#toggleAll");
    const mobile = $("#tocExpand");
    if (all) all.textContent = allOpen ? "Collapse solutions" : "Expand solutions";
    if (mobile) {
      mobile.textContent = allOpen ? "Collapse all solutions" : "Expand all solutions";
      mobile.setAttribute("data-open", allOpen ? "true" : "false");
    }
  }

  function setAllCards(open) {
    $$(".tcard").forEach(function (card) { setCardOpen(card, open); });
    syncAllLabels();
  }

  function toggleAllCards() {
    const anyClosed = $$(".tcard").some(function (c) {
      return !c.classList.contains("open");
    });
    setAllCards(anyClosed);
  }

  function initCards() {
    document.addEventListener("click", function (e) {
      const btn = e.target.closest(".tcard-toggle");
      if (!btn) return;
      const card = btn.closest(".tcard");
      if (card) {
        setCardOpen(card, !card.classList.contains("open"));
        syncAllLabels();
      }
    });

    const all = $("#toggleAll");
    if (all) all.addEventListener("click", toggleAllCards);
    const mobile = $("#tocExpand");
    if (mobile) mobile.addEventListener("click", toggleAllCards);

    initCardGlow();
  }

  function initCardGlow() {
    document.addEventListener("pointermove", function (e) {
      const card = e.target.closest(".tcard");
      if (!card) return;
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", ((e.clientX - r.left) / r.width) * 100 + "%");
      card.style.setProperty("--my", ((e.clientY - r.top) / r.height) * 100 + "%");
    }, { passive: true });
  }

  /* ------------------------------------------------------ scroll spy */
  function initScrollSpy() {
    function onScroll() {
      const secs = $$(".sec-head");
      const tocSecs = $$("[data-sec]");
      const railSecs = $$("[data-rail]");
      const chLinks = $$("[data-ch]");
      const y = window.scrollY + 150;
      let active = null;
      secs.forEach(function (s) {
        if (s.offsetTop <= y) active = s.id;
      });
      tocSecs.forEach(function (a) {
        a.classList.toggle("active", a.getAttribute("data-sec") === active);
      });
      railSecs.forEach(function (a) {
        a.classList.toggle("active", a.getAttribute("data-rail") === active);
      });
      // chapter highlight
      let cur = null;
      chapters.forEach(function (c) {
        const el = document.getElementById("ch" + c.num);
        if (el && el.offsetTop - 150 <= y) cur = c.num;
      });
      if (cur == null && chapters[current]) cur = chapters[current].num;
      chLinks.forEach(function (a) {
        a.classList.toggle("active", +a.getAttribute("data-ch") === cur);
      });
      // progress
      const h = document.documentElement.scrollHeight - window.innerHeight;
      const p = h > 0 ? Math.min(1, window.scrollY / h) : 0;
      const C = 2 * Math.PI * 15.5;
      const ring = $("#ring");
      if (ring) ring.style.strokeDashoffset = String(C * (1 - p));
      $("#ringPct").textContent = Math.round(p * 100) + "%";
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    onScroll();
  }

  /* ------------------------------------------------------------- init */
  function parseHash() {
    const h = location.hash.replace("#", "");
    if (!h) return null;
    const m = h.match(/^ch(\d+)/);
    return m ? +m[1] : null;
  }

  function parseCardHash(hash) {
    const m = String(hash || "").match(/^#t-ch(\d+)-(theorem|example|problem|exam)-\S+$/);
    return m ? { ch: +m[1], id: hash.slice(1) } : null;
  }

  function scrollInstant(el) {
    const root = document.documentElement;
    const prev = root.style.scrollBehavior;
    root.style.scrollBehavior = "auto";
    el.scrollIntoView({ block: "start" });
    root.style.scrollBehavior = prev;
  }

  function revealHash(hash) {
    const el = document.getElementById(String(hash || "").replace(/^#/, ""));
    if (!el) return;
    if (el.classList.contains("tcard")) setCardOpen(el, true);
    setTimeout(function () {
      scrollInstant(el);
    }, 40);
  }

  function initTOC() {
    const toc = $("#toc");
    const toggle = $("#tocToggle");
    if (!toc || !toggle) return;
    const mq = window.matchMedia("(max-width: 900px)");
    const mobile = function () { return mq.matches; };

    function close(returnFocus) {
      if (!document.body.classList.contains("toc-open")) return;
      document.body.classList.remove("toc-open");
      toggle.setAttribute("aria-expanded", "false");
      if (mobile()) toc.setAttribute("aria-hidden", "true");
      if (returnFocus && mobile()) toggle.focus({ preventScroll: true });
    }

    toggle.addEventListener("click", function () {
      const open = !document.body.classList.contains("toc-open");
      document.body.classList.toggle("toc-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (mobile()) toc.setAttribute("aria-hidden", open ? "false" : "true");
      if (open) {
        const target = toc.querySelector("a.active") || toc.querySelector("a");
        if (target) setTimeout(function () { target.focus({ preventScroll: true }); }, 60);
      }
    });

    toc.addEventListener("click", function (e) {
      if (e.target.closest("a") && mobile()) close(false);
    });

    document.addEventListener("click", function (e) {
      if (!document.body.classList.contains("toc-open")) return;
      if (e.target.closest("#toc") || e.target.closest("#tocToggle")) return;
      close(true);
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && document.body.classList.contains("toc-open")) close(true);
    });

    function sync() {
      if (!mobile()) {
        document.body.classList.remove("toc-open");
        toc.removeAttribute("aria-hidden");
        toggle.setAttribute("aria-expanded", "false");
      } else if (!document.body.classList.contains("toc-open")) {
        toc.setAttribute("aria-hidden", "true");
        toggle.setAttribute("aria-expanded", "false");
      }
    }
    sync();
    if (mq.addEventListener) mq.addEventListener("change", sync);
    else if (mq.addListener) mq.addListener(sync);
  }

  function init() {
    buildTOC();
    initCards();

    const start = parseHash();
    const cardStart = parseCardHash(location.hash);
    let idx = 0;
    if (start) {
      idx = chapters.findIndex(function (c) { return c.num === start; });
      if (idx < 0) idx = 0;
    } else if (cardStart) {
      idx = chapters.findIndex(function (c) { return c.num === cardStart.ch; });
      if (idx < 0) idx = 0;
    }
    showChapter(idx, false);
    initScrollSpy();
    initTOC();

    let resizeTimer = null;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        containWideMath($("#content"));
      }, 160);
    });

    // Landing on a card link (from search) opens that card and scrolls to it.
    // Section links land at the section heading instead.
    if (cardStart) {
      revealHash(location.hash);
    } else if (/^#ch\d+-/.test(location.hash)) {
      const target = location.hash;
      setTimeout(function () {
        const el = document.querySelector(target);
        if (el) scrollInstant(el);
      }, 80);
    }

    $("#prevCh").addEventListener("click", function () { showChapter(current - 1); });
    $("#nextCh").addEventListener("click", function () { showChapter(current + 1); });
    $("#markRead").addEventListener("click", function () {
      const ch = chapters[current];
      if (done[ch.num]) delete done[ch.num]; else done[ch.num] = Date.now();
      try { localStorage.setItem(DONE_KEY, JSON.stringify(done)); } catch (e) { /* ignore */ }
      $("#markRead").textContent = done[ch.num] ? "✓ Chapter read" : "Mark chapter read";
      $$("[data-ch]").forEach(function (a) {
        a.classList.toggle("done", !!done[a.getAttribute("data-ch")]);
      });
    });

    // section deep links
    document.addEventListener("click", function (e) {
      const a = e.target.closest("a[href^='#ch']");
      if (!a) return;
      const href = a.getAttribute("href");
      e.preventDefault();
      const m = href.match(/^#ch(\d+)(?:-(.*))?$/);
      if (!m) return;
      const num = +m[1];
      const ci = chapters.findIndex(function (c) { return c.num === num; });
      if (ci < 0) return;
      if (ci !== current) {
        showChapter(ci, false);
        setTimeout(function () { jump(href); }, 60);
      } else {
        jump(href);
      }
    });

    function jump(href) {
      const el = document.querySelector(href);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
      el.focus({ preventScroll: true });
    }

    window.addEventListener("hashchange", function () {
      const card = parseCardHash(location.hash);
      if (card) {
        const ci = chapters.findIndex(function (c) { return c.num === card.ch; });
        if (ci >= 0) {
          if (ci !== current) showChapter(ci, false);
          setTimeout(function () { revealHash(location.hash); }, 60);
        }
        return;
      }
      const num = parseHash();
      if (!num) return;
      const ci = chapters.findIndex(function (c) { return c.num === num; });
      if (ci >= 0 && ci !== current) showChapter(ci, false);
    });

    document.addEventListener("keydown", function (e) {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
      if (document.body.classList.contains("toc-open")) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "j" || e.key === "ArrowRight") { showChapter(current + 1); }
      if (e.key === "k" || e.key === "ArrowLeft") { showChapter(current - 1); }
      if (e.key === "m") { $("#markRead").click(); }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
