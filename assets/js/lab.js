/* =======================================================================
   MATHEMATICA — interactive math lab
   ======================================================================= */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));
  const E = window.Expr;

  const css = (n, p) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || p;

  /* ------------------------------------------------------ canvas util */
  function setup(cv) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const r = cv.getBoundingClientRect();
    const w = cv.clientWidth || 600;
    const h = cv.clientHeight || parseInt(cv.getAttribute("height"), 10) || 460;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: w, h: h };
  }

  function plotFrame(g, opts) {
    const { ctx, w, h } = g;
    const o = opts || {};
    const x0 = o.x0, x1 = o.x1, y0 = o.y0, y1 = o.y1;
    const sx = (x) => (x - x0) / (x1 - x0) * w;
    const sy = (y) => h - (y - y0) / (y1 - y0) * h;
    ctx.clearRect(0, 0, w, h);
    // background
    ctx.fillStyle = css("--bg-inset", "rgba(0,0,0,.4)");
    ctx.fillRect(0, 0, w, h);
    if (o.grid !== false) {
      ctx.strokeStyle = "rgba(148,176,214,0.09)";
      ctx.lineWidth = 1;
      const stepX = niceStep((x1 - x0) / 10);
      const stepY = niceStep((y1 - y0) / 8);
      ctx.beginPath();
      for (let x = Math.ceil(x0 / stepX) * stepX; x <= x1; x += stepX) {
        const px = Math.round(sx(x)) + 0.5;
        ctx.moveTo(px, 0); ctx.lineTo(px, h);
      }
      for (let y = Math.ceil(y0 / stepY) * stepY; y <= y1; y += stepY) {
        const py = Math.round(sy(y)) + 0.5;
        ctx.moveTo(0, py); ctx.lineTo(w, py);
      }
      ctx.stroke();
      // labels
      ctx.fillStyle = css("--fg-faint", "#56657c");
      ctx.font = "10px 'JetBrains Mono', monospace";
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      for (let x = Math.ceil(x0 / stepX) * stepX; x <= x1; x += stepX) {
        if (Math.abs(x) > stepX / 2) ctx.fillText(fmt(x), sx(x), h + 4);
      }
      ctx.textAlign = "left"; ctx.textBaseline = "middle";
      for (let y = Math.ceil(y0 / stepY) * stepY; y <= y1; y += stepY) {
        if (Math.abs(y) > stepY / 2) ctx.fillText(fmt(y), 6, sy(y));
      }
    }
    // axes
    ctx.strokeStyle = "rgba(148,176,214,0.34)";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    if (y0 <= 0 && y1 >= 0) {
      const py = Math.round(sy(0)) + 0.5;
      ctx.moveTo(0, py); ctx.lineTo(w, py);
    }
    if (x0 <= 0 && x1 >= 0) {
      const px = Math.round(sx(0)) + 0.5;
      ctx.moveTo(px, 0); ctx.lineTo(px, h);
    }
    ctx.stroke();
    return { sx: sx, sy: sy };
  }

  function niceStep(raw) {
    const p = Math.pow(10, Math.floor(Math.log10(Math.abs(raw) || 1)));
    const n = raw / p;
    return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * p;
  }

  function fmt(v) {
    if (!isFinite(v)) return "—";
    const a = Math.abs(v);
    if (a === 0) return "0";
    if (a >= 1000 || a < 0.01) return v.toExponential(1);
    return (Math.round(v * 1000) / 1000).toString();
  }

  function normCdf(z) {
    // Abramowitz & Stegun 7.1.26
    const s = z < 0 ? -1 : 1, x = Math.abs(z) / Math.SQRT2;
    const t = 1 / (1 + 0.3275911 * x);
    const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) *
      t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
    return 0.5 * (1 + s * y);
  }

  function normPdf(z) {
    return Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI);
  }

  /* ====================================================== 1. PLOTTER */
  const Plot = (function () {
    const cv = $("#pCanvas");
    let ast = null, dast = null, err = null;
    const state = { range: 10, x0: 1.5, tangent: true, deriv: true, area: false, grid: true };

    function compile() {
      try {
        ast = E.parse($("#pFn").value);
        dast = E.differentiate(ast);
        err = null;
        $("#pFn").classList.remove("invalid");
        $("#pFnHint").textContent = "f′(x) = " + E.toString(dast);
      } catch (e) {
        err = e.message;
        ast = null;
        $("#pFn").classList.add("invalid");
        $("#pFnHint").textContent = "⚠ " + e.message;
      }
    }

    function draw() {
      const g = setup(cv);
      const R = state.range;
      const ymax = 9;
      const p = plotFrame(g, { x0: -R, x1: R, y0: -ymax, y1: ymax, grid: state.grid });
      const gold = css("--accent", "#f0b458");
      const teal = css("--accent-2", "#5eead4");
      const violet = css("--accent-3", "#b4a1ff");

      if (err || !ast) {
        $("#pReadout").innerHTML = "Enter a valid expression, e.g. <b>sin(x) + 0.25*x</b>";
        return;
      }

      const f = (x) => E.evaluate(ast, x);
      const df = (x) => E.evaluate(dast, x);

      // area under the curve between 0 and x0
      if (state.area) {
        const N = 800;
        ctx = g.ctx;
        g.ctx.beginPath();
        let started = false;
        for (let i = 0; i <= N; i++) {
          const x = (i / N) * state.x0;
          const y = f(x);
          if (!isFinite(y)) continue;
          const px = p.sx(x), py = p.sy(Math.max(y, -ymax));
          if (!started) { g.ctx.moveTo(p.sx(0), p.sy(0)); started = true; }
          g.ctx.lineTo(px, py);
        }
        g.ctx.lineTo(p.sx(state.x0), p.sy(0));
        g.ctx.closePath();
        g.ctx.fillStyle = "rgba(240,180,88,0.14)";
        g.ctx.fill();
      }

      // curve
      g.ctx.beginPath();
      let pen = false;
      for (let i = 0; i <= 1400; i++) {
        const x = -R + (2 * R) * i / 1400;
        let y = f(x);
        if (!isFinite(y)) { pen = false; continue; }
        y = Math.max(-ymax, Math.min(ymax, y));
        const px = p.sx(x), py = p.sy(y);
        if (!pen) { g.ctx.moveTo(px, py); pen = true; } else g.ctx.lineTo(px, py);
      }
      g.ctx.strokeStyle = gold;
      g.ctx.lineWidth = 2.2;
      g.ctx.lineJoin = "round";
      g.ctx.stroke();

      const x0 = state.x0, y0 = f(x0), m = df(x0);
      const X = Math.min(ymax, Math.max(-ymax, y0));

      // derivative curve
      if (state.deriv) {
        g.ctx.beginPath();
        pen = false;
        for (let i = 0; i <= 900; i++) {
          const x = -R + (2 * R) * i / 900;
          let y = df(x);
          if (!isFinite(y)) { pen = false; continue; }
          y = Math.max(-ymax, Math.min(ymax, y));
          const px = p.sx(x), py = p.sy(y);
          if (!pen) { g.ctx.moveTo(px, py); pen = true; } else g.ctx.lineTo(px, py);
        }
        g.ctx.strokeStyle = violet;
        g.ctx.lineWidth = 1.5;
        g.ctx.setLineDash([5, 4]);
        g.ctx.stroke();
        g.ctx.setLineDash([]);
      }

      // tangent
      if (state.tangent && isFinite(X) && isFinite(m)) {
        const dx = R * 0.22;
        g.ctx.beginPath();
        g.ctx.moveTo(p.sx(x0 - dx), p.sy(X - m * dx));
        g.ctx.lineTo(p.sx(x0 + dx), p.sy(X + m * dx));
        g.ctx.strokeStyle = teal;
        g.ctx.lineWidth = 1.8;
        g.ctx.stroke();
      }

      // point
      g.ctx.beginPath();
      g.ctx.arc(p.sx(x0), p.sy(X), 5, 0, Math.PI * 2);
      g.ctx.fillStyle = teal;
      g.ctx.fill();
      g.ctx.strokeStyle = css("--bg", "#05080f");
      g.ctx.lineWidth = 2;
      g.ctx.stroke();

      const area = simpson(f, Math.min(0, x0), Math.max(0, x0), 600);
      $("#pReadout").innerHTML =
        "f(x₀) = <b>" + fmt(y0) + "</b>     f′(x₀) = <b>" + fmt(m) + "</b>\n" +
        "∫ from " + fmt(Math.min(0, x0)) + " to " + fmt(Math.max(0, x0)) +
        " f dx = <b>" + fmt(area) + "</b>\n" +
        "f′(x) = <b>" + E.toString(dast) + "</b>";
    }

    function simpson(f, a, b, n) {
      if (b <= a) return 0;
      n = n % 2 ? n + 1 : n;
      const h = (b - a) / n;
      let s = f(a) + f(b);
      for (let i = 1; i < n; i++) s += f(a + i * h) * (i % 2 ? 4 : 2);
      return s * h / 3;
    }

    function init() {
      compile();
      $("#pFn").addEventListener("input", function () { compile(); draw(); });
      $("#pRange").addEventListener("input", function (e) {
        state.range = +e.target.value;
        $("#pRangeV").textContent = "−" + state.range + " … " + state.range;
        draw();
      });
      $("#pX0").addEventListener("input", function (e) {
        state.x0 = +e.target.value;
        $("#pX0V").textContent = state.x0.toFixed(2);
        draw();
      });
      $$("[data-tg]").forEach(function (b) {
        if (!b.closest(".tabpane[data-pane='plot']")) return;
        b.addEventListener("click", function () {
          const k = b.getAttribute("data-tg");
          state[k] = !state[k];
          b.classList.toggle("on", state[k]);
          draw();
        });
      });
      window.addEventListener("resize", draw);
      draw();
    }
    return { init: init, draw: draw };
  })();

  /* ====================================================== 2. RIEMANN */
  const Riemann = (function () {
    const cv = $("#rCanvas");
    const state = { n: 12, rule: "left", a: 0, b: 2 * Math.PI };

    function evaluate() {
      try {
        const ast = E.parse($("#rFn").value);
        state.a = parseFloat($("#rA").value);
        state.b = parseFloat($("#rB").value);
        if (!isFinite(state.a) || !isFinite(state.b)) throw new Error("Bad interval");
        return ast;
      } catch (e) {
        return null;
      }
    }

    function draw() {
      const g = setup(cv);
      const ast = evaluate();
      const gold = css("--accent", "#f0b458");
      const teal = css("--accent-2", "#5eead4");
      if (!ast) { $("#rReadout").textContent = "Invalid expression"; return; }
      const f = (x) => E.evaluate(ast, x);
      const a = state.a, b = state.b;
      let lo = Infinity, hi = -Infinity;
      for (let i = 0; i <= 300; i++) {
        const y = f(a + (b - a) * i / 300);
        if (isFinite(y)) { lo = Math.min(lo, y); hi = Math.max(hi, y); }
      }
      if (!isFinite(lo)) { lo = -1; hi = 1; }
      const pad = (hi - lo) * 0.18 + 0.2;
      const p = plotFrame(g, { x0: a, x1: b, y0: lo - pad, y1: hi + pad });
      const ctx = g.ctx;

      // curve
      ctx.beginPath();
      let pen = false;
      for (let i = 0; i <= 1200; i++) {
        const x = a + (b - a) * i / 1200;
        const y = f(x);
        if (!isFinite(y)) { pen = false; continue; }
        const px = p.sx(x), py = p.sy(y);
        if (!pen) { ctx.moveTo(px, py); pen = true; } else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = gold;
      ctx.lineWidth = 2.2;
      ctx.stroke();

      const n = state.n;
      const h = (b - a) / n;
      let sum = 0;
      for (let i = 0; i < n; i++) {
        let x, y;
        if (state.rule === "left") { x = a + i * h; y = f(x); }
        else if (state.rule === "right") { x = a + (i + 1) * h; y = f(x); }
        else if (state.rule === "mid") { x = a + (i + 0.5) * h; y = f(x); }
        else if (state.rule === "trap") {
          const y1 = f(a + i * h), y2 = f(a + (i + 1) * h);
          x = a + i * h; y = (y1 + y2) / 2; sum += (y1 + y2) / 2 * h; continue;
        } else { // simpson on pairs
          if (i % 2) continue;
          const x0 = a + i * h, x1 = a + (i + 1) * h, xm = (x0 + x1) / 2;
          sum += (h / 3) * (f(x0) + 4 * f(xm) + f(x1));
          continue;
        }
        sum += y * h;
        // rectangle
        const rx = p.sx(x), rw = p.sx(x + h) - rx;
        const ry = p.sy(y), r0 = p.sy(0);
        ctx.fillStyle = "rgba(94,234,212,0.13)";
        ctx.strokeStyle = "rgba(94,234,212,0.55)";
        ctx.lineWidth = 1;
        ctx.fillRect(rx, Math.min(ry, r0), rw, Math.abs(r0 - ry));
        ctx.strokeRect(rx, Math.min(ry, r0), rw, Math.abs(r0 - ry));
      }

      const exact = numericInt(f, a, b);
      $("#rReadout").innerHTML =
        "rule: <b>" + state.rule + "</b>   n = <b>" + n + "</b>\n" +
        "sum ≈ <b>" + fmt(sum) + "</b>     exact ≈ <b>" + fmt(exact) + "</b>\n" +
        "error = <b>" + fmt(Math.abs(sum - exact)) + "</b>";
    }

    function numericInt(f, a, b) {
      const n = 4000;
      const h = (b - a) / n;
      let s = f(a) + f(b);
      for (let i = 1; i < n; i++) s += f(a + i * h) * (i % 2 ? 4 : 2);
      return s * h / 3;
    }

    function init() {
      $("#rN").addEventListener("input", function (e) {
        state.n = +e.target.value;
        $("#rNVal").textContent = state.n;
        draw();
      });
      ["#rFn", "#rA", "#rB"].forEach(function (s) {
        $(s).addEventListener("input", draw);
      });
      $$("[data-rule]").forEach(function (b) {
        b.addEventListener("click", function () {
          $$("[data-rule]").forEach(function (x) { x.classList.remove("on"); });
          b.classList.add("on");
          state.rule = b.getAttribute("data-rule");
          draw();
        });
      });
      window.addEventListener("resize", draw);
      draw();
    }
    return { init: init, draw: draw };
  })();

  /* ====================================================== 3. DESCENT */
  const Descent = (function () {
    const cv = $("#dCanvas");
    const state = { lr: 0.12, mom: 0, loss: "bowl", start: "a", x: 0, y: 0, vx: 0, vy: 0, path: [], running: false, iter: 0 };

    function loss(x, y) {
      switch (state.loss) {
        case "bowl": return 0.5 * (x * x + 2 * y * y);
        case "saddle": return 0.5 * (x * x - y * y);
        case "rosen": return (1 - x) * (1 - x) + 100 * (y - x * x) * (y - x * x);
      }
      return 0;
    }
    function grad(x, y) {
      switch (state.loss) {
        case "bowl": return [x, 2 * y];
        case "saddle": return [x, -y];
        case "rosen": return [-2 * (1 - x) - 400 * x * (y - x * x), 200 * (y - x * x)];
      }
      return [0, 0];
    }
    const STARTS = { a: [-2.4, 1.9], b: [2.6, -1.7], c: [0.4, 2.4] };

    function reset() {
      const s = STARTS[state.start];
      state.x = s[0]; state.y = s[1];
      state.vx = 0; state.vy = 0;
      state.path = [[state.x, state.y]];
      state.iter = 0;
    }

    function step() {
      const g = grad(state.x, state.y);
      state.vx = state.mom * state.vx - state.lr * g[0];
      state.vy = state.mom * state.vy - state.lr * g[1];
      state.x += state.vx;
      state.y += state.vy;
      state.path.push([state.x, state.y]);
      state.iter++;
      if (state.path.length > 900) state.path.shift();
    }

    function draw() {
      const g = setup(cv);
      const gold = css("--accent", "#f0b458");
      const teal = css("--accent-2", "#5eead4");
      const R = 4;
      const p = plotFrame(g, { x0: -R, x1: R, y0: -R, y1: R });
      const ctx = g.ctx;

      // contour rings — traced level by level along rays from the minimum
      ctx.lineWidth = 1;
      const base = loss(0, 0);
      for (let k = 1; k <= 10; k++) {
        const lvl = base + k * (state.loss === "rosen" ? 2.2 : 0.45);
        ctx.beginPath();
        let started = false;
        for (let i = 0; i <= 300; i++) {
          const th = i / 300 * Math.PI * 2;
          const c = Math.cos(th), s = Math.sin(th);
          let lo = 0, hi = R * 1.4;
          if (loss(0, 0) > lvl) { started = false; continue; }
          if (loss(hi * c, hi * s) < lvl) { started = false; continue; }
          for (let it = 0; it < 26; it++) {
            const mid = (lo + hi) / 2;
            if (loss(mid * c, mid * s) < lvl) lo = mid; else hi = mid;
          }
          const r = (lo + hi) / 2;
          const px = p.sx(r * c), py = p.sy(r * s);
          if (!started) { ctx.moveTo(px, py); started = true; }
          else ctx.lineTo(px, py);
        }
        ctx.strokeStyle = "rgba(148,176,214," + (0.22 - k * 0.015).toFixed(3) + ")";
        ctx.stroke();
      }

      // path
      if (state.path.length > 1) {
        ctx.beginPath();
        state.path.forEach(function (pt, i) {
          const px = p.sx(pt[0]), py = p.sy(pt[1]);
          if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        });
        ctx.strokeStyle = teal;
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // current point
      const cx = p.sx(state.x), cy = p.sy(state.y);
      ctx.beginPath();
      ctx.arc(cx, cy, 6, 0, Math.PI * 2);
      ctx.fillStyle = gold;
      ctx.fill();
      ctx.strokeStyle = css("--bg", "#05080f");
      ctx.lineWidth = 2;
      ctx.stroke();

      $("#dReadout").innerHTML =
        "surface: <b>" + state.loss + "</b>    η = <b>" + state.lr.toFixed(2) +
        "</b>    momentum = <b>" + state.mom.toFixed(2) + "</b>\n" +
        "iterations: <b>" + state.iter + "</b>    ‖∇L‖ = <b>" +
        fmt(Math.hypot(grad(state.x, state.y)[0], grad(state.x, state.y)[1])) + "</b>\n" +
        "L(θ) = <b>" + fmt(loss(state.x, state.y)) + "</b>    θ = (<b>" +
        fmt(state.x) + "</b>, <b>" + fmt(state.y) + "</b>)";
    }

    let timer = null;
    function init() {
      $("#dLr").addEventListener("input", function (e) {
        state.lr = +e.target.value / 100;
        $("#dLrV").textContent = state.lr.toFixed(2);
        draw();
      });
      $("#dMom").addEventListener("input", function (e) {
        state.mom = +e.target.value / 100;
        $("#dMomV").textContent = state.mom.toFixed(2);
        draw();
      });
      $$("[data-loss]").forEach(function (b) {
        b.addEventListener("click", function () {
          $$("[data-loss]").forEach(function (x) { x.classList.remove("on"); });
          b.classList.add("on");
          state.loss = b.getAttribute("data-loss");
          reset(); draw();
        });
      });
      $$("[data-start]").forEach(function (b) {
        b.addEventListener("click", function () {
          $$("[data-start]").forEach(function (x) { x.classList.remove("on"); });
          b.classList.add("on");
          state.start = b.getAttribute("data-start");
          reset(); draw();
        });
      });
      $("#dPlay").addEventListener("click", function () {
        if (timer) { clearInterval(timer); timer = null; $("#dPlay").textContent = "Run"; return; }
        $("#dPlay").textContent = "Pause";
        timer = setInterval(function () { step(); draw(); }, 16);
      });
      $("#dReset").addEventListener("click", function () { reset(); draw(); });
      window.addEventListener("resize", draw);
      reset(); draw();
    }
    return { init: init, draw: draw };
  })();

  /* ======================================================= 4. OPTION */
  const Option = (function () {
    const cv = $("#oCanvas");
    const state = { type: "call", S: 100, K: 100, vol: 0.25, r: 0.05, T: 1 };

    function price() {
      const { S, K, vol, r, T } = state;
      const d1 = (Math.log(S / K) + (r + 0.5 * vol * vol) * T) / (vol * Math.sqrt(T));
      const d2 = d1 - vol * Math.sqrt(T);
      const df = Math.exp(-r * T);
      const call = S * normCdf(d1) - K * df * normCdf(d2);
      const put = K * df * normCdf(-d2) - S * normCdf(-d1);
      return { call: call, put: put, d1: d1, d2: d2 };
    }

    function draw() {
      const g = setup(cv);
      const gold = css("--accent", "#f0b458");
      const teal = css("--accent-2", "#5eead4");
      const violet = css("--accent-3", "#b4a1ff");
      const { S, K, T, vol, r } = state;
      const lo = Math.max(1, K * 0.35), hi = K * 1.7;
      const p = plotFrame(g, { x0: lo, x1: hi, y0: -K * 0.12, y1: K * 0.9 });
      const ctx = g.ctx;
      const pr = price();

      // payoff at expiry
      ctx.beginPath();
      for (let i = 0; i <= 400; i++) {
        const x = lo + (hi - lo) * i / 400;
        const pay = state.type === "call" ? Math.max(0, x - K) : Math.max(0, K - x);
        const px = p.sx(x), py = p.sy(pay);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = "rgba(148,176,214,0.55)";
      ctx.lineWidth = 1.6;
      ctx.setLineDash([6, 4]);
      ctx.stroke();
      ctx.setLineDash([]);

      // price curve
      ctx.beginPath();
      for (let i = 0; i <= 400; i++) {
        const x = lo + (hi - lo) * i / 400;
        const y = blackScholes(x, K, T, vol, r, state.type);
        const px = p.sx(x), py = p.sy(y);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = gold;
      ctx.lineWidth = 2.6;
      ctx.stroke();

      // vertical at spot
      ctx.beginPath();
      ctx.moveTo(p.sx(S), 0); ctx.lineTo(p.sx(S), p.sy(0));
      ctx.strokeStyle = violet;
      ctx.lineWidth = 1.4;
      ctx.stroke();

      const spotY = state.type === "call" ? pr.call : pr.put;
      ctx.beginPath();
      ctx.arc(p.sx(S), p.sy(spotY), 6, 0, Math.PI * 2);
      ctx.fillStyle = teal;
      ctx.fill();

      // labels
      ctx.fillStyle = css("--fg-mute", "#7d8ea6");
      ctx.font = "11px 'JetBrains Mono', monospace";
      ctx.textAlign = "left"; ctx.textBaseline = "middle";
      ctx.fillText("payoff at T", Math.min(p.sx(hi) - 78, g.w - 92), p.sy(K * 0.55));
      ctx.fillStyle = gold;
      ctx.fillText("price today", Math.min(p.sx(hi) - 78, g.w - 92), p.sy(K * 0.45));

      const delta = state.type === "call" ? normCdf(pr.d1) : normCdf(pr.d1) - 1;
      const vega = S * normPdf(pr.d1) * Math.sqrt(T) / 100;
      $("#oReadout").innerHTML =
        "Black–Scholes–Merton:  V = <b>" + fmt(spotY) + "</b>   (S₀=" + S +
        ", K=" + K + ", σ=" + (vol * 100).toFixed(0) + "%, r=" +
        (r * 100).toFixed(1) + "%, T=" + T.toFixed(1) + "y)\n" +
        "d₁ = <b>" + fmt(pr.d1) + "</b>   d₂ = <b>" + fmt(pr.d2) + "</b>\n" +
        "Δ = <b>" + fmt(delta) + "</b>   Vega = <b>" + fmt(vega) +
        "</b> per 1% vol   put–call parity: C − P = <b>" +
        fmt(pr.call - pr.put) + "</b>";
    }

    function blackScholes(S, K, T, vol, r, type) {
      const d1 = (Math.log(S / K) + (r + 0.5 * vol * vol) * T) / (vol * Math.sqrt(T));
      const d2 = d1 - vol * Math.sqrt(T);
      const df = Math.exp(-r * T);
      const call = S * normCdf(d1) - K * df * normCdf(d2);
      return type === "call" ? call : K * df * normCdf(-d2) - S * normCdf(-d1);
    }

    function init() {
      function upd() {
        state.S = +$("#oS").value; state.K = +$("#oK").value;
        state.vol = +$("#oVol").value / 100; state.r = +$("#oR").value / 100;
        state.T = +$("#oT").value / 10;
        $("#oSV").textContent = state.S; $("#oKV").textContent = state.K;
        $("#oVolV").textContent = Math.round(state.vol * 100) + "%";
        $("#oRV").textContent = (state.r * 100).toFixed(1) + "%";
        $("#oTV").textContent = state.T.toFixed(1);
        draw();
      }
      ["#oS", "#oK", "#oVol", "#oR", "#oT"].forEach(function (s) {
        $(s).addEventListener("input", upd);
      });
      $$("[data-opt]").forEach(function (b) {
        b.addEventListener("click", function () {
          $$("[data-opt]").forEach(function (x) { x.classList.remove("on"); });
          b.classList.add("on");
          state.type = b.getAttribute("data-opt");
          draw();
        });
      });
      window.addEventListener("resize", draw);
      upd();
    }
    return { init: init, draw: draw };
  })();

  /* ======================================================== 5. PROB */
  const Prob = (function () {
    const cv = $("#bCanvas");
    const state = { dist: "normal", n: 4000, bins: 30, hist: true, clt: true, gauss: true };

    function sample() {
      const out = [];
      for (let i = 0; i < state.n; i++) {
        switch (state.dist) {
          case "uniform": out.push(Math.random()); break;
          case "normal": out.push(randn()); break;
          case "exp": out.push(-Math.log(1 - Math.random())); break;
          case "cauchy": out.push(Math.tan(Math.PI * (Math.random() - 0.5))); break;
          case "poisson": out.push(poisson(3)); break;
        }
      }
      return out;
    }
    function randn() {
      let u = 0, v = 0;
      while (u === 0) u = Math.random();
      while (v === 0) v = Math.random();
      return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    }
    function poisson(lambda) {
      let L = Math.exp(-lambda), k = 0, p = 1;
      do { k++; p *= Math.random(); } while (p > L);
      return k - 1;
    }

    function draw() {
      const g = setup(cv);
      const gold = css("--accent", "#f0b458");
      const teal = css("--accent-2", "#5eead4");
      const violet = css("--accent-3", "#b4a1ff");
      const ctx = g.ctx;
      const data = sample();

      let lo = Infinity, hi = -Infinity;
      data.forEach(function (v) { lo = Math.min(lo, v); hi = Math.max(hi, v); });
      const pad = (hi - lo) * 0.06 + 0.2;
      lo -= pad; hi += pad;
      const p = plotFrame(g, { x0: lo, x1: hi, y0: 0, y1: 1 });
      const px = (x) => p.sx(x);

      // histogram
      if (state.hist) {
        const B = state.bins;
        const counts = new Array(B).fill(0);
        data.forEach(function (v) {
          let k = Math.floor((v - lo) / (hi - lo) * B);
          k = Math.max(0, Math.min(B - 1, k));
          counts[k]++;
        });
        const mx = Math.max.apply(null, counts) || 1;
        const bw = (hi - lo) / B;
        ctx.fillStyle = "rgba(240,180,88,0.22)";
        ctx.strokeStyle = "rgba(240,180,88,0.6)";
        ctx.lineWidth = 1;
        for (let k = 0; k < B; k++) {
          const x = lo + k * bw;
          const y = counts[k] / mx;
          ctx.fillRect(px(x), p.sy(y), px(x + bw) - px(x) - 1, p.sy(0) - p.sy(y));
          ctx.strokeRect(px(x), p.sy(y), px(x + bw) - px(x) - 1, p.sy(0) - p.sy(y));
        }
        ctx.fillStyle = "rgba(240,180,88,0.85)";
        ctx.font = "11px 'JetBrains Mono', monospace";
        ctx.textAlign = "left"; ctx.textBaseline = "top";
        ctx.fillText("histogram", px(lo) + 8, 6);
      }

      // theoretical density
      if (state.gauss) {
        const dens = state.dist === "normal" ? normPdf
          : state.dist === "uniform" ? function (x) { return (x >= 0 && x <= 1) ? 1 : 0; }
          : state.dist === "exp" ? function (x) { return x >= 0 ? Math.exp(-x) : 0; }
          : state.dist === "cauchy" ? function (x) { return 1 / (Math.PI * (1 + x * x)); }
          : null;
        if (dens) {
          const peak = state.dist === "uniform" ? 1 : state.dist === "cauchy" ? 0.318 :
            state.dist === "exp" ? 1 : 0.399;
          ctx.beginPath();
          for (let i = 0; i <= 500; i++) {
            const x = lo + (hi - lo) * i / 500;
            const y = dens(x) / peak;
            const X = px(x), Y = p.sy(y);
            if (i === 0) ctx.moveTo(X, Y); else ctx.lineTo(X, Y);
          }
          ctx.strokeStyle = violet;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      }

      // CLT: means of k samples
      if (state.clt) {
        const groups = 40;
        const means = [];
        const per = Math.max(2, Math.floor(state.n / groups));
        for (let g = 0; g < groups; g++) {
          let s = 0;
          for (let i = 0; i < per; i++) {
            let v;
            switch (state.dist) {
              case "uniform": v = Math.random(); break;
              case "normal": v = randn(); break;
              case "exp": v = -Math.log(1 - Math.random()); break;
              case "cauchy": v = Math.tan(Math.PI * (Math.random() - 0.5)); break;
              case "poisson": v = poisson(3); break;
            }
            s += v;
          }
          means.push(s / per);
        }
        const mlo = Math.min.apply(null, means), mhi = Math.max.apply(null, means);
        const B = 24;
        const counts = new Array(B).fill(0);
        means.forEach(function (v) {
          let k = Math.floor((v - mlo) / ((mhi - mlo) || 1) * B);
          k = Math.max(0, Math.min(B - 1, k));
          counts[k]++;
        });
        const bw = ((mhi - mlo) || 1) / B;
        const mmax = Math.max.apply(null, counts) || 1;
        // inset panel in the upper-left corner
        const iw = Math.min(300, g.w * 0.34), ih = Math.min(120, g.h * 0.26);
        const ix = 14, iy = 14;
        ctx.save();
        ctx.fillStyle = "rgba(7,12,23,0.86)";
        ctx.strokeStyle = "rgba(148,176,214,0.22)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(ix, iy, iw, ih, 8);
        else ctx.rect(ix, iy, iw, ih);
        ctx.fill(); ctx.stroke();
        ctx.beginPath();
        ctx.rect(ix, iy, iw, ih);
        ctx.clip();
        for (let k = 0; k < B; k++) {
          const x = ix + (k / B) * iw;
          const hh = (counts[k] / mmax) * (ih - 22);
          ctx.fillStyle = "rgba(94,234,212,0.42)";
          ctx.fillRect(x + 1, iy + ih - 18 - hh, iw / B - 2, hh);
        }
        ctx.fillStyle = "rgba(94,234,212,0.95)";
        ctx.font = "10px 'JetBrains Mono', monospace";
        ctx.textAlign = "left"; ctx.textBaseline = "top";
        ctx.fillText("means of " + per + " draws", ix + 8, iy + 6);
        ctx.fillStyle = "rgba(255,255,255,0.45)";
        ctx.textAlign = "right";
        ctx.fillText("→ normal", ix + iw - 8, iy + 6);
        ctx.restore();
      }

      const mean = data.reduce(function (a, b) { return a + b; }, 0) / data.length;
      const sd = Math.sqrt(data.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / data.length);
      $("#bReadout").innerHTML =
        "distribution: <b>" + state.dist + "</b>    n = <b>" + state.n + "</b>\n" +
        "sample mean μ̂ = <b>" + fmt(mean) + "</b>    sample sd σ̂ = <b>" +
        fmt(sd) + "</b>\n" +
        "theoretical: " + (state.dist === "normal" ? "μ = 0, σ = 1" :
          state.dist === "uniform" ? "μ = 0.5, σ = 0.289" :
          state.dist === "exp" ? "μ = 1, σ = 1" :
          state.dist === "cauchy" ? "μ, σ undefined (heavy tails)" :
          "μ = 3, σ = √3") +
        (state.dist === "cauchy" ? "  ← the CLT does not apply here" : "");
    }

    function init() {
      $("#bDist").addEventListener("change", function (e) {
        state.dist = e.target.value; draw();
      });
      $("#bN").addEventListener("input", function (e) {
        state.n = +e.target.value; $("#bNV").textContent = state.n; draw();
      });
      $("#bB").addEventListener("input", function (e) {
        state.bins = +e.target.value; $("#bBV").textContent = state.bins; draw();
      });
      $$("[data-tg]").forEach(function (b) {
        if (!b.closest(".tabpane[data-pane='prob']")) return;
        b.addEventListener("click", function () {
          const k = b.getAttribute("data-tg");
          state[k] = !state[k];
          b.classList.toggle("on", state[k]);
          draw();
        });
      });
      window.addEventListener("resize", draw);
      draw();
    }
    return { init: init, draw: draw };
  })();

  /* ====================================================== 6. LINALG */
  const Linalg = (function () {
    const cv = $("#lCanvas");
    const state = { a: 1.2, b: 0.4, c: -0.3, d: 1.0, grid: true, eig: true, anim: true, t: 0 };

    function draw() {
      const g = setup(cv);
      const gold = css("--accent", "#f0b458");
      const teal = css("--accent-2", "#5eead4");
      const violet = css("--accent-3", "#b4a1ff");
      const ctx = g.ctx;
      const R = 3;
      const p = plotFrame(g, { x0: -R, x1: R, y0: -R, y1: R });
      const A = state.anim ? matAt(state.t) : { a: state.a, b: state.b, c: state.c, d: state.d };

      // source grid
      ctx.strokeStyle = "rgba(148,176,214,0.13)";
      ctx.lineWidth = 1;
      for (let i = -6; i <= 6; i++) {
        const v = i * 0.5;
        ctx.beginPath();
        ctx.moveTo(p.sx(-R), p.sy(v)); ctx.lineTo(p.sx(R), p.sy(v));
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(p.sx(v), p.sy(-R)); ctx.lineTo(p.sx(v), p.sy(R));
        ctx.stroke();
      }

      // image grid
      if (state.grid) {
        ctx.strokeStyle = "rgba(240,180,88,0.30)";
        ctx.lineWidth = 1;
        for (let i = -6; i <= 6; i++) {
          const v = i * 0.5;
          let x1 = A.a * -R + A.b * v, y1 = A.c * -R + A.d * v;
          let x2 = A.a * R + A.b * v, y2 = A.c * R + A.d * v;
          ctx.beginPath();
          ctx.moveTo(p.sx(x1), p.sy(y1)); ctx.lineTo(p.sx(x2), p.sy(y2));
          ctx.stroke();
          x1 = A.a * v + A.b * -R; y1 = A.c * v + A.d * -R;
          x2 = A.a * v + A.b * R; y2 = A.c * v + A.d * R;
          ctx.beginPath();
          ctx.moveTo(p.sx(x1), p.sy(y1)); ctx.lineTo(p.sx(x2), p.sy(y2));
          ctx.stroke();
        }
      }

      // unit circle image
      ctx.beginPath();
      for (let i = 0; i <= 120; i++) {
        const th = i / 120 * Math.PI * 2;
        const x = A.a * Math.cos(th) + A.b * Math.sin(th);
        const y = A.c * Math.cos(th) + A.d * Math.sin(th);
        const X = p.sx(x), Y = p.sy(y);
        if (i === 0) ctx.moveTo(X, Y); else ctx.lineTo(X, Y);
      }
      ctx.closePath();
      ctx.strokeStyle = gold;
      ctx.lineWidth = 2.4;
      ctx.stroke();
      ctx.fillStyle = "rgba(240,180,88,0.08)";
      ctx.fill();

      // eigenvectors
      const ev = eigen(A);
      if (state.eig) {
        ev.forEach(function (e) {
          ctx.beginPath();
          ctx.moveTo(p.sx(-e.v[0] * 2.6), p.sy(-e.v[1] * 2.6));
          ctx.lineTo(p.sx(e.v[0] * 2.6), p.sy(e.v[1] * 2.6));
          ctx.strokeStyle = e.real ? violet : teal;
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.fillStyle = e.real ? violet : teal;
          ctx.font = "11px 'JetBrains Mono', monospace";
          ctx.textAlign = "left"; ctx.textBaseline = "middle";
          const lx = Math.min(p.sx(e.v[0] * 2.6) + 8, g.w - 78);
          const ly = Math.max(12, Math.min(g.h - 10, p.sy(e.v[1] * 2.6)));
          ctx.fillText("λ = " + fmt(e.lam), lx, ly);
        });
      }

      const det = A.a * A.d - A.b * A.c;
      const tr = A.a + A.d;
      $("#lE1").textContent = ev[0] ? fmt(ev[0].lam) : "—";
      $("#lE2").textContent = ev[1] ? fmt(ev[1].lam) : "—";
      $("#lDet").textContent = fmt(det);
      $("#lTr").textContent = fmt(tr);
      $("#lReadout").innerHTML =
        (state.anim ? "A(t) = [[" : "A = [[") + "<b>" + fmt(A.a) + "</b>, <b>" +
        fmt(A.b) + "</b>], [<b>" + fmt(A.c) + "</b>, <b>" + fmt(A.d) + "</b>]]\n" +
        "det A = <b>" + fmt(det) + "</b>   tr A = <b>" + fmt(tr) + "</b>   " +
        (Math.abs(det) < 1e-9 ? "singular — the grid collapses to a line" :
          Math.abs(det - 1) < 1e-6 ? "area-preserving (det = 1)" :
          det > 0 ? "orientation-preserving" : "orientation-reversing") + "\n" +
        "λ₁ = <b>" + (ev[0] ? fmt(ev[0].lam) : "—") + "</b>   λ₂ = <b>" +
        (ev[1] ? fmt(ev[1].lam) : "—") + "</b>";
    }

    function matAt(t) {
      const s = 0.6 + 0.4 * Math.sin(t * 0.7);
      return {
        a: state.a * s + 0.3 * Math.cos(t * 0.5),
        b: state.b * s,
        c: state.c * s,
        d: state.d * s + 0.3 * Math.sin(t * 0.6)
      };
    }

    function eigen(A) {
      const tr = A.a + A.d, det = A.a * A.d - A.b * A.c;
      const disc = tr * tr - 4 * det;
      const out = [];
      if (disc >= 0) {
        const r = Math.sqrt(disc);
        const l1 = (tr + r) / 2, l2 = (tr - r) / 2;
        out.push({ lam: l1, v: vecFor(A, l1), real: true });
        out.push({ lam: l2, v: vecFor(A, l2), real: true });
      } else {
        const re = tr / 2, im = Math.sqrt(-disc) / 2;
        out.push({ lam: re, v: [1, 0], real: false });
        out.push({ lam: re, v: [1, 0], real: false });
      }
      return out;
    }
    function vecFor(A, l) {
      let x, y;
      if (Math.abs(A.b) > 1e-9) { x = 1; y = (l - A.a) / A.b; }
      else if (Math.abs(A.c) > 1e-9) { y = 1; x = (l - A.d) / A.c; }
      else { x = 1; y = 0; }
      const n = Math.hypot(x, y) || 1;
      return [x / n, y / n];
    }

    function init() {
      function upd() {
        state.a = parseFloat($("#m00").value) || 0;
        state.b = parseFloat($("#m01").value) || 0;
        state.c = parseFloat($("#m10").value) || 0;
        state.d = parseFloat($("#m11").value) || 0;
        draw();
      }
      ["#m00", "#m01", "#m10", "#m11"].forEach(function (s) {
        $(s).addEventListener("input", upd);
      });
      $$("[data-tg]").forEach(function (b) {
        if (!b.closest(".tabpane[data-pane='linalg']")) return;
        b.addEventListener("click", function () {
          const k = b.getAttribute("data-tg");
          state[k] = !state[k];
          b.classList.toggle("on", state[k]);
          draw();
        });
      });
      window.addEventListener("resize", draw);
      (function loop(ts) {
        if (state.anim) { state.t = (ts || 0) / 1000; draw(); }
        requestAnimationFrame(loop);
      })(0);
      upd();
    }
    return { init: init, draw: draw };
  })();

  /* -------------------------------------------------------------- tabs */
  function initTabs() {
    const tabs = $$("#labTabs .tab");
    tabs.forEach(function (t) {
      t.addEventListener("click", function () {
        const name = t.getAttribute("data-tab");
        tabs.forEach(function (x) { x.classList.toggle("on", x === t); });
        $$(".tabpane").forEach(function (p) {
          p.classList.toggle("on", p.getAttribute("data-pane") === name);
        });
        const pane = $('.tabpane[data-pane="' + name + '"]');
        if (pane) {
          const map = { plot: Plot, riemann: Riemann, descent: Descent,
            option: Option, prob: Prob, linalg: Linalg };
          if (map[name]) map[name].draw();
        }
      });
    });
  }

  function init() {
    initTabs();
    Plot.init();
    Riemann.init();
    Descent.init();
    Option.init();
    Prob.init();
    Linalg.init();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
