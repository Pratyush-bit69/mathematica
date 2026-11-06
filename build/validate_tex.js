/* Validate every LaTeX span in the treatise with KaTeX. */
const fs = require("fs");
const path = require("path");
const katex = require(path.join(__dirname, "..", "assets", "katex", "katex.min.js"));

global.window = {};
const src = fs.readFileSync(path.join(__dirname, "..", "assets", "data", "treatise.js"), "utf8");
eval(src.replace(/^window\.TREATISE\s*=/, "globalThis.TREATISE ="));
const T = globalThis.TREATISE;

let total = 0, ok = 0;
const failures = {};
const samples = [];

function check(tex, where) {
  total++;
  try {
    katex.renderToString(tex, { throwOnError: true, strict: false });
    ok++;
  } catch (e) {
    const key = String(e.message).slice(0, 90);
    failures[key] = (failures[key] || 0) + 1;
    if (samples.length < 40) samples.push({ tex: tex.slice(0, 170), msg: key, where });
  }
}

function runs(list, where) {
  (list || []).forEach(function (r) {
    if (r.k === "math") check(r.latex, where);
  });
}

T.chapters.forEach(function (ch) {
  runs(ch.intro, "ch" + ch.num);
  (ch.sections || []).forEach(function (s) {
    (s.blocks || []).forEach(function (b) {
      runs(b.runs, "ch" + ch.num + " §" + s.num);
      runs(b.statement, "ch" + ch.num + " §" + s.num + " [statement]");
    });
  });
});

console.log("total math spans:", total);
console.log("parsed cleanly  :", ok, "(" + ((ok / total) * 100).toFixed(2) + "%)");
console.log("\n--- failure modes ---");
Object.entries(failures).sort((a, b) => b[1] - a[1]).slice(0, 25).forEach(function (e) {
  console.log(String(e[1]).padStart(6), e[0]);
});
console.log("\n--- samples ---");
samples.slice(0, 25).forEach(function (s) {
  console.log("[" + s.where + "] " + s.tex);
  console.log("    -> " + s.msg);
});
