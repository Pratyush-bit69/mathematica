/* =======================================================================
   MATHEMATICA — reader
   ======================================================================= */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));
  const T = window.TREATISE;
  if (!T) return;

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
    theorem: "Theorem", example: "Worked Example", problem: "Problem",
    exam: "Exam", proof: "Proof", solution: "Solution", para: "",
    bullet: "", display: "", tier: "", section: ""
  };

  /* -------------------------------------------------- block rendering */
  function renderRuns(runs, cls) {
    if (!runs || !runs.length) return "";
    return (runs || []).map(function (r) {
      if (r.k === "br") return '<br>';
      if (r.k === "text") {
        const t = esc(r.v);
        return r.b ? "<strong>" + t + "</strong>" : t;
      }
      return '<span class="mx" data-tex="' + esc(r.latex) + '"></span>';
    }).join(cls ? ' class="' + cls + '"' : "");
  }

  function blockHTML(b) {
    switch (b.type) {
      case "para":
        return '<p class="prose">' + renderRuns(b.runs) + "</p>";
      case "bullet":
        return '<div class="bullet"><span class="mk"></span><div class="tx prose">' +
          renderRuns(b.runs) + "</div></div>";
      case "display":
        return '<div class="display">' + renderRuns(b.runs) + "</div>";
      case "tier":
        return '<div class="tier">' + esc(b.title) + "</div>";
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

  function cardHTML(b) {
    const kind = b.type === "exam" ? "exam" : b.type === "example" ? "ex" :
      b.type === "problem" ? "prob" : "theorem";
    const open = b.open ? " open" : "";
    const titleId = "t" + b.type + "-" + b.num.replace(/\./g, "-");
    return '<section class="tcard ' + kind + open + '" id="' + titleId + '" data-card="1">' +
      '<button class="tcard-head" aria-expanded="' + (b.open ? "true" : "false") + '">' +
      '<span class="tcard-kind">' + (KIND[b.type] || b.type) + "</span>" +
      '<span class="tcard-txt"><span class="tcard-num">' + esc(b.num) + "</span>" +
      "<h4>" + esc(b.title) + "</h4></span>" +
      '<svg class="tcard-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>' +
      "</button>" +
      '<div class="tcard-body">' + cardBody(b) + "</div></section>";
  }

  function cardBody(b) {
    let html = "";
    if (b.runs && b.runs.length) {
      html += '<div class="prose">' + renderRuns(b.runs) + "</div>";
    }
    // following blocks (proof / solution / steps) belong to the card
    if (b.children) {
      html += b.children.map(function (c) {
        if (c.type === "solution" || c.type === "question" || c.type === "verify") {
          return '<div class="label">' + esc(c.label || "Solution") + "</div>" +
            '<div class="prose">' + renderRuns(c.runs) + "</div>";
        }
        if (c.type === "proof") {
          return '<div class="proof">' +
            (c.title ? '<div class="ptitle">' + esc(c.title) + "</div>" : "") +
            '<div class="prose">' + renderRuns(c.runs) + "</div></div>";
        }
        return blockHTML(c);
      }).join("");
    }
    return html;
  }

  /* ------------------------------------------------------- chapter view */
  function groupBlocks(blocks) {
    /* Attach everything that follows a card — its statement, proof,
       solution and verification — into that card. */
    const CARD = { theorem: 1, example: 1, problem: 1, exam: 1 };
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
        out.push({ type: b.type, num: b.num, title: b.title, runs: b.runs,
          children: kids, open: b.open });
        i = j - 1;
      } else {
        out.push(b);
      }
    }
    return out;
  }

  function chapterHTML(ch) {
    const vol = ["I", "II", "III", "IV"][ch.volume - 1];
    const counts = { ex: 0, pr: 0, th: 0 };
    (ch.sections || []).forEach(function (s) {
      (s.blocks || []).forEach(function (b) {
        if (b.type === "example") counts.ex++;
        else if (b.type === "problem" || b.type === "exam") counts.pr++;
        else if (b.type === "theorem") counts.th++;
      });
    });

    let html = '<header class="ch-head">' +
      '<div class="vol-pill">Volume ' + vol + " · Chapter " + ch.num + "</div>" +
      "<h1>" + esc(ch.title) + "</h1>" +
      '<div class="ch-kpis">' +
      "<div><b>" + (ch.sections || []).length + "</b>sections</div>" +
      (counts.th ? "<div><b>" + counts.th + "</b>formal proof" + (counts.th > 1 ? "s" : "") + "</div>" : "") +
      (counts.ex ? "<div><b>" + counts.ex + "</b>worked examples</div>" : "") +
      (counts.pr ? "<div><b>" + counts.pr + "</b>solved problems</div>" : "") +
      "</div></header>";

    if (ch.intro && ch.intro.length) {
      html += '<div class="prose" style="margin-bottom:8px">' +
        ch.intro.map(blockHTML).join("") + "</div>";
    }

    (ch.sections || []).forEach(function (sec) {
      const sid = "ch" + ch.num + "-" + sec.num.replace(/\./g, "-");
      html += '<section class="sec-head" id="' + sid + '">' +
        '<h2><span class="sno">' + esc(sec.num) + "</span>" + esc(sec.title) + "</h2>" +
        '<div class="rule"></div></section>';
      html += '<div class="prose">' + groupBlocks(sec.blocks || []).map(function (b) {
        if (b.type === "theorem" || b.type === "example" || b.type === "problem" ||
            b.type === "exam") return cardHTML(b);
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
    chapters.forEach(function (ch, i) {
      if (ch.volume !== lastVol) {
        lastVol = ch.volume;
        const v = T.volumes.filter(function (x) { return x.id === ch.volume; })[0];
        html += '<a class="vol">Volume ' + (v ? v.roman : ch.volume) + "</a>";
      }
      html += '<a href="#ch' + ch.num + '" data-ch="' + ch.num + '">' +
        '<span class="dot"></span><span class="tno">' + ch.num + "</span>" +
        "<span>" + esc(ch.title) + "</span></a>";
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
    window.scrollTo({ top: 0, behavior: "auto" });
    if (pushHash !== false) {
      history.replaceState(null, "", "#ch" + ch.num);
    }
    document.title = "Ch. " + ch.num + " · " + ch.title + " — MATHEMATICA";
  }

  /* --------------------------------------------------------- math render */
  function renderMath(root) {
    if (!window.katex) return;
    $$(".mx", root).forEach(function (el) {
      const tex = el.getAttribute("data-tex");
      try {
        katex.render(tex, el, {
          throwOnError: false,
          displayMode: el.classList.contains("block"),
          strict: false,
          trust: false
        });
        el.setAttribute("title", tex);
      } catch (e) {
        el.textContent = tex;
      }
    });
    // copy-LaTeX affordance on display equations
    $$(".display", root).forEach(function (d) {
      if (d.querySelector(".copy-tex")) return;
      const b = document.createElement("button");
      b.className = "copy-tex";
      b.type = "button";
      b.title = "Copy LaTeX";
      b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 012-2h8"/></svg>';
      b.addEventListener("click", function (e) {
        e.stopPropagation();
        const tex = d.textContent;
        const latex = collectLatex(d);
        copy(latex || tex);
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
  function initCards() {
    document.addEventListener("click", function (e) {
      const head = e.target.closest(".tcard-head");
      if (!head) return;
      const card = head.closest(".tcard");
      const open = card.classList.toggle("open");
      head.setAttribute("aria-expanded", open ? "true" : "false");
    });
    const all = $("#toggleAll");
    if (all) {
      all.addEventListener("click", function () {
        const cards = $$(".tcard");
        const anyClosed = cards.some(function (c) { return !c.classList.contains("open"); });
        cards.forEach(function (c) {
          c.classList.toggle("open", anyClosed);
          const h = c.querySelector(".tcard-head");
          if (h) h.setAttribute("aria-expanded", anyClosed ? "true" : "false");
        });
        all.textContent = anyClosed ? "Collapse all" : "Expand all";
      });
    }
  }

  /* ------------------------------------------------------ scroll spy */
  function initScrollSpy() {
    const secs = $$(".sec-head");
    const tocSecs = $$("[data-sec]");
    const railSecs = $$("[data-rail]");
    const chLinks = $$("[data-ch]");
    function onScroll() {
      const y = window.scrollY + 140;
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
      const ch = chapters[current];
      if (ch) {
        let cur = ch.num;
        chapters.forEach(function (c) {
          const el = document.getElementById("ch" + c.num);
          if (el && el.offsetTop - 140 <= y) cur = c.num;
        });
        chLinks.forEach(function (a) {
          a.classList.toggle("active", +a.getAttribute("data-ch") === cur);
        });
      }
      // progress
      const h = document.documentElement.scrollHeight - window.innerHeight;
      const p = h > 0 ? Math.min(1, window.scrollY / h) : 0;
      const C = 2 * Math.PI * 15.5;
      $("#ring").style.strokeDashoffset = String(C * (1 - p));
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

  function init() {
    buildTOC();
    initCards();

    const start = parseHash();
    let idx = 0;
    if (start) {
      idx = chapters.findIndex(function (c) { return c.num === start; });
      if (idx < 0) idx = 0;
    }
    showChapter(idx, false);
    initScrollSpy();

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
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    window.addEventListener("hashchange", function () {
      const num = parseHash();
      if (!num) return;
      const ci = chapters.findIndex(function (c) { return c.num === num; });
      if (ci >= 0 && ci !== current) showChapter(ci, false);
    });

    document.addEventListener("keydown", function (e) {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
      if (e.key === "j" || e.key === "ArrowRight") { if (e.shiftKey) showChapter(current + 1); }
      if (e.key === "k" || e.key === "ArrowLeft") { if (e.shiftKey) showChapter(current - 1); }
      if (e.key === "m") { $("#markRead").click(); }
    });

    // mobile TOC
    $("#tocToggle").addEventListener("click", function () {
      document.body.classList.toggle("toc-open");
      $("#toc").setAttribute("aria-hidden",
        document.body.classList.contains("toc-open") ? "false" : "true");
    });
    $("#toc").addEventListener("click", function (e) {
      if (e.target.closest("a") && window.innerWidth <= 900) {
        document.body.classList.remove("toc-open");
      }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
