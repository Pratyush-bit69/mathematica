/* =======================================================================
   MATHEMATICA — glossary, formula sheet, theorem index
   ======================================================================= */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));
  const G = window.GLOSSARY;
  const T = window.TREATISE;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  let mode = "terms";
  let filter = "";

  function renderTerms() {
    const cats = {};
    G.core.forEach(function (e) {
      (cats[e.c] = cats[e.c] || []).push(e);
    });
    const order = Object.keys(cats);
    const html = order.map(function (c) {
      const items = cats[c].filter(function (e) {
        return !filter ||
          (e.t + " " + e.d + " " + e.c).toLowerCase().indexOf(filter) >= 0;
      });
      if (!items.length) return "";
      return '<section style="margin-bottom:44px">' +
        '<div class="eyebrow">' + esc(c) + "</div>" +
        '<div class="grid g-3">' +
        items.map(function (e) {
          return '<div class="card feat">' +
            "<h3>" + esc(e.t) + "</h3>" +
            "<p>" + esc(e.d) + "</p></div>";
        }).join("") + "</div></section>";
    }).join("");
    $("#gTerms").innerHTML = html || '<div class="modal-empty">No concept matches “' + esc(filter) + "”.</div>";
  }

  function renderFormulas() {
    const items = G.formulas.filter(function (f) {
      return !filter || (f.t + " " + f.l).toLowerCase().indexOf(filter) >= 0;
    });
    $("#gFormulas").innerHTML = '<div class="grid g-2">' +
      items.map(function (f) {
        return '<div class="card feat">' +
          "<h3>" + esc(f.t) + "</h3>" +
          '<div class="fmath" data-tex="' + esc(f.l) + '"></div></div>';
      }).join("") + "</div>";
    renderMath($("#gFormulas"));
  }

  function renderTheorems() {
    const out = [];
    T.chapters.forEach(function (ch) {
      (ch.sections || []).forEach(function (sec) {
        (sec.blocks || []).forEach(function (b) {
          if (b.type !== "theorem") return;
          out.push({ ch: ch.num, sec: sec.num, num: b.num, title: b.title, runs: b.runs });
        });
      });
    });
    const items = out.filter(function (t) {
      return !filter || (t.num + " " + t.title).toLowerCase().indexOf(filter) >= 0;
    });
    $("#gTheorems").innerHTML =
      '<div class="panel panel-pad" style="margin-bottom:18px">' +
      '<div class="eyebrow" style="margin-bottom:6px">All ' + out.length +
      " formal theorems</div>" +
      '<p style="color:var(--fg-mute);font-size:0.94rem;margin:0">Each proof is ' +
      "written out in full in the reader — click through to the chapter it lives in.</p></div>" +
      '<div class="grid g-2">' +
      items.map(function (t) {
        return '<a class="card feat" href="reader.html#ch' + t.ch + "-" +
          t.sec.replace(/\./g, "-") + '">' +
          '<div class="n" style="font-family:var(--mono);font-size:11px;color:var(--accent);margin-bottom:8px">THEOREM ' +
          esc(t.num) + " · CHAPTER " + t.ch + "</div>" +
          "<h3>" + esc(t.title) + "</h3>" +
          '<p style="font-family:var(--sans);font-size:12px;color:var(--fg-faint)">Section ' +
          esc(t.sec) + " →</p></a>";
      }).join("") + "</div>";
  }

  function renderMath(root) {
    if (!window.katex) return;
    $$("[data-tex]", root).forEach(function (el) {
      const display = el.classList.contains("block") || !!el.closest(".fmath");
      try {
        katex.render(el.getAttribute("data-tex"), el,
          { throwOnError: false, displayMode: display, strict: false });
      } catch (e) { el.textContent = el.getAttribute("data-tex"); }
    });
  }

  function init() {
    renderTerms();
    renderFormulas();
    renderTheorems();

    $$("[data-mode]").forEach(function (b) {
      b.addEventListener("click", function () {
        $$("[data-mode]").forEach(function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        mode = b.getAttribute("data-mode");
        $("#gTerms").classList.toggle("hide", mode !== "terms");
        $("#gFormulas").classList.toggle("hide", mode !== "formulas");
        $("#gTheorems").classList.toggle("hide", mode !== "theorems");
        if (mode === "formulas") renderMath($("#gFormulas"));
      });
    });

    $("#gSearch").addEventListener("input", function (e) {
      filter = e.target.value.trim().toLowerCase();
      if (mode === "terms") renderTerms();
      else if (mode === "formulas") renderFormulas();
      else renderTheorems();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
