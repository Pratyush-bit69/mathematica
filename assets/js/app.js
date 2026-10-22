/* =======================================================================
   MATHEMATICA — shared behaviour: theme, nav, reveals, global search
   ======================================================================= */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));

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
  const Index = {
    entries: [],
    ready: false,
    build: function () {
      if (this.ready) return;
      const T = window.TREATISE;
      if (!T) return;
      const self = this;
      T.chapters.forEach(function (ch) {
        const anchor = "ch" + ch.num;
        function push(section, block, runs) {
          let txt = "";
          (runs || []).forEach(function (r) {
            if (r.k === "text") txt += r.v;
            else if (r.latex) txt += " " + Index.plain(r.latex) + " ";
          });
          txt = txt.replace(/\s+/g, " ").trim();
          if (txt.length < 3) return;
          self.entries.push({
            title: (section ? section.num + " " + section.title : ch.title),
            ctx: "Ch. " + ch.num + (section ? " · §" + section.num : ""),
            body: txt,
            href: "reader.html#" + anchor + (section ? "-" + section.num.replace(".", "-") : ""),
            block: block
          });
        }
        if (ch.intro) ch.intro.forEach(function (b) { push(null, b, b.runs); });
        (ch.sections || []).forEach(function (sec) {
          (sec.blocks || []).forEach(function (b) { push(sec, b, b.runs); });
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
        const hay = (e.title + " " + e.body).toLowerCase();
        let score = 0;
        let ok = true;
        for (let t = 0; t < terms.length; t++) {
          const p = hay.indexOf(terms[t]);
          if (p < 0) { ok = false; break; }
          score += 1;
          if (e.title.toLowerCase().indexOf(terms[t]) >= 0) score += 6;
        }
        if (!ok) continue;
        out.push({ e: e, score: score, pos: hay.indexOf(terms[0]) });
      }
      out.sort(function (a, b) { return b.score - a.score; });
      return out.slice(0, 40);
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

  function highlight(text, q) {    const terms = q.trim().split(/\s+/).filter(Boolean);
    let html = escapeHtml(text);
    terms.forEach(function (t) {
      const re = new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi");
      html = html.replace(re, "$1");
    });
    return html.replace(//g, "<mark>").replace(//g, "</mark>");
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

    function render(q) {
      if (!q || q.trim().length < 2) {
        results.innerHTML = '<div class="modal-empty">Type at least two characters to search the entire treatise.</div>';
        current = []; sel = 0;
        return;
      }
      current = Index.query(q);
      if (!current.length) {
        results.innerHTML = '<div class="modal-empty">No matches for “' + escapeHtml(q) + '”.</div>';
        return;
      }
      results.innerHTML = current.map(function (r, i) {
        const body = r.e.body.length > 190 ? r.e.body.slice(0, 190) + "…" : r.e.body;
        return '<a class="sr' + (i === sel ? " sel" : "") + '" href="' + r.e.href + '">' +
          '<div class="t">' + highlight(r.e.title, q) + "</div>" +
          '<div class="c"><span class="badge badge-gold">' + escapeHtml(r.e.ctx) + "</span>" +
          "<span>" + highlight(body, q) + "</span></div></a>";
      }).join("");
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

  window.Mathematica = { Index: Index, escapeHtml: escapeHtml, highlight: highlight };
})();
