/* =======================================================================
   MATHEMATICA — tiny expression engine (parse, evaluate, differentiate)
   ======================================================================= */
(function (global) {
  "use strict";

  /* ------------------------------------------------------------- lexer */
  const FUNCS = {
    sin: 1, cos: 1, tan: 1, asin: 1, acos: 1, atan: 1,
    exp: 1, log: 1, ln: 1, sqrt: 1, abs: 1, sign: 1,
    floor: 1, ceil: 1, round: 1, min: 2, max: 2, pow: 2
  };
  const CONSTS = { pi: Math.PI, e: Math.E, tau: Math.PI * 2 };

  function lex(src) {
    const toks = [];
    let i = 0;
    while (i < src.length) {
      const c = src[i];
      if (/\s/.test(c)) { i++; continue; }
      if (/[0-9.]/.test(c)) {
        let j = i;
        while (j < src.length && /[0-9.]/.test(src[j])) j++;
        toks.push({ t: "num", v: parseFloat(src.slice(i, j)) });
        i = j; continue;
      }
      if (/[a-zA-Z]/.test(c)) {
        let j = i;
        while (j < src.length && /[a-zA-Z]/.test(src[j])) j++;
        toks.push({ t: "id", v: src.slice(i, j) });
        i = j; continue;
      }
      if ("+-*/^(),".indexOf(c) >= 0) { toks.push({ t: c }); i++; continue; }
      throw new Error("Unexpected character “" + c + "”");
    }
    return toks;
  }

  /* ------------------------------------------------------------ parser */
  function parse(src) {
    const toks = lex(src);
    let p = 0;
    const peek = () => toks[p];
    const eat = (t) => {
      if (toks[p] && toks[p].t === t) { p++; return true; }
      return false;
    };

    function parseExpr() { return parseAdd(); }

    function parseAdd() {
      let left = parseMul();
      for (;;) {
        if (eat("+")) left = { k: "add", a: left, b: parseMul() };
        else if (eat("-")) left = { k: "sub", a: left, b: parseMul() };
        else return left;
      }
    }

    function parseMul() {
      let left = parseUnary();
      for (;;) {
        if (eat("*")) left = { k: "mul", a: left, b: parseUnary() };
        else if (eat("/")) left = { k: "div", a: left, b: parseUnary() };
        else if (peek() && (peek().t === "num" || peek().t === "id" ||
               peek().t === "(")) {
          left = { k: "mul", a: left, b: parseUnary() };   // implicit
        } else return left;
      }
    }

    function parseUnary() {
      if (eat("-")) return { k: "neg", a: parseUnary() };
      if (eat("+")) return parseUnary();
      return parsePow();
    }

    function parsePow() {
      const base = parseAtom();
      if (eat("^")) return { k: "pow", a: base, b: parseUnary() };
      return base;
    }

    function parseAtom() {
      const t = peek();
      if (!t) throw new Error("Unexpected end of expression");
      if (t.t === "num") { p++; return { k: "num", v: t.v }; }
      if (t.t === "(") {
        p++;
        const e = parseExpr();
        if (!eat(")")) throw new Error("Missing closing parenthesis");
        return e;
      }
      if (t.t === "id") {
        p++;
        const name = t.v;
        if (FUNCS[name] === 2) {
          if (!eat("(")) throw new Error(name + " needs two arguments");
          const a = parseExpr();
          if (!eat(",")) throw new Error(name + " needs two arguments");
          const b = parseExpr();
          if (!eat(")")) throw new Error("Missing closing parenthesis");
          return { k: "fn", name: name, args: [a, b] };
        }
        if (FUNCS[name]) {
          if (!eat("(")) throw new Error(name + " needs an argument");
          const a = parseExpr();
          if (!eat(")")) throw new Error("Missing closing parenthesis");
          return { k: "fn", name: name, args: [a] };
        }
        if (name in CONSTS) return { k: "num", v: CONSTS[name] };
        if (name === "x") return { k: "var" };
        throw new Error("Unknown name “" + name + "”");
      }
      throw new Error("Unexpected token “" + t.t + "”");
    }

    const ast = parseExpr();
    if (p < toks.length) throw new Error("Unexpected trailing input");
    return ast;
  }

  /* ---------------------------------------------------------- evaluate */
  function evaluate(node, x) {
    switch (node.k) {
      case "num": return node.v;
      case "var": return x;
      case "add": return evaluate(node.a, x) + evaluate(node.b, x);
      case "sub": return evaluate(node.a, x) - evaluate(node.b, x);
      case "mul": return evaluate(node.a, x) * evaluate(node.b, x);
      case "div": return evaluate(node.a, x) / evaluate(node.b, x);
      case "neg": return -evaluate(node.a, x);
      case "pow": return Math.pow(evaluate(node.a, x), evaluate(node.b, x));
      case "fn": {
        const a = node.args.map(function (g) { return evaluate(g, x); });
        switch (node.name) {
          case "sin": return Math.sin(a[0]);
          case "cos": return Math.cos(a[0]);
          case "tan": return Math.tan(a[0]);
          case "asin": return Math.asin(a[0]);
          case "acos": return Math.acos(a[0]);
          case "atan": return Math.atan(a[0]);
          case "exp": return Math.exp(a[0]);
          case "log": return Math.log10(a[0]);
          case "ln": return Math.log(a[0]);
          case "sqrt": return Math.sqrt(a[0]);
          case "abs": return Math.abs(a[0]);
          case "sign": return Math.sign(a[0]);
          case "floor": return Math.floor(a[0]);
          case "ceil": return Math.ceil(a[0]);
          case "round": return Math.round(a[0]);
          case "min": return Math.min(a[0], a[1]);
          case "max": return Math.max(a[0], a[1]);
          case "pow": return Math.pow(a[0], a[1]);
        }
        return NaN;
      }
    }
    return NaN;
  }

  /* ------------------------------------------------------ differentiate */
  function differentiate(node) {
    switch (node.k) {
      case "num": return { k: "num", v: 0 };
      case "var": return { k: "num", v: 1 };
      case "add": return { k: "add", a: differentiate(node.a), b: differentiate(node.b) };
      case "sub": return { k: "sub", a: differentiate(node.a), b: differentiate(node.b) };
      case "neg": return { k: "neg", a: differentiate(node.a) };
      case "mul":
        return { k: "add",
          a: { k: "mul", a: differentiate(node.a), b: node.b },
          b: { k: "mul", a: node.a, b: differentiate(node.b) } };
      case "div": {
        const u = node.a, v = node.b;
        return { k: "div",
          a: { k: "sub",
            a: { k: "mul", a: differentiate(u), b: v },
            b: { k: "mul", a: u, b: differentiate(v) } },
          b: { k: "pow", a: v, b: { k: "num", v: 2 } } };
      }
      case "pow": {
        const u = node.a, v = node.b;
        if (v.k === "num") {
          return { k: "mul",
            a: { k: "num", v: v.v },
            b: { k: "pow", a: u, b: { k: "num", v: v.v - 1 } } };
        }
        return { k: "mul",
          a: { k: "pow", a: u, b: v },
          b: { k: "add",
            a: { k: "mul", a: differentiate(u), b: v },
            b: { k: "mul", a: u, b: differentiate(v) } } };
      }
      case "fn": {
        const a = node.args[0];
        const da = differentiate(a);
        const u = { k: "fn", name: node.name, args: [a] };
        const inner = { k: "fn", name: node.name, args: [a] };
        switch (node.name) {
          case "sin": return { k: "mul", a: { k: "fn", name: "cos", args: [a] }, b: da };
          case "cos": return { k: "neg", a: { k: "mul", a: { k: "fn", name: "sin", args: [a] }, b: da } };
          case "tan":
            return { k: "div",
              a: da,
              b: { k: "pow", a: { k: "fn", name: "cos", args: [a] }, b: { k: "num", v: 2 } } };
          case "exp": return { k: "mul", a: u, b: da };
          case "ln": return { k: "div", a: da, b: a };
          case "log": return { k: "div", a: da, b: { k: "mul", a: a, b: { k: "num", v: Math.LN10 } } };
          case "sqrt": return { k: "div", a: da, b: { k: "mul", a: { k: "num", v: 2 }, b: { k: "fn", name: "sqrt", args: [a] } } };
          case "abs": return { k: "mul", a: { k: "fn", name: "sign", args: [a] }, b: da };
          default: return { k: "num", v: 0 };
        }
      }
    }
    return { k: "num", v: 0 };
  }

  /* ---------------------------------------------------------- simplify */
  function simplify(node) {
    if (!node) return node;
    const s = (n) => simplify(n);
    switch (node.k) {
      case "add": {
        const a = s(node.a), b = s(node.b);
        if (a.k === "num" && a.v === 0) return b;
        if (b.k === "num" && b.v === 0) return a;
        if (a.k === "num" && b.k === "num") return { k: "num", v: a.v + b.v };
        return { k: "add", a: a, b: b };
      }
      case "sub": {
        const a = s(node.a), b = s(node.b);
        if (b.k === "num" && b.v === 0) return a;
        if (a.k === "num" && a.v === 0) return { k: "neg", a: b };
        if (a.k === "num" && b.k === "num") return { k: "num", v: a.v - b.v };
        return { k: "sub", a: a, b: b };
      }
      case "neg": {
        const a = s(node.a);
        if (a.k === "num") return { k: "num", v: -a.v };
        if (a.k === "neg") return a.a;
        return { k: "neg", a: a };
      }
      case "mul": {
        const a = s(node.a), b = s(node.b);
        if ((a.k === "num" && a.v === 0) || (b.k === "num" && b.v === 0)) {
          return { k: "num", v: 0 };
        }
        if (a.k === "num" && a.v === 1) return b;
        if (b.k === "num" && b.v === 1) return a;
        if (a.k === "num" && b.k === "num") return { k: "num", v: a.v * b.v };
        return { k: "mul", a: a, b: b };
      }
      case "div": {
        const a = s(node.a), b = s(node.b);
        if (a.k === "num" && a.v === 0) return { k: "num", v: 0 };
        if (b.k === "num" && b.v === 1) return a;
        if (a.k === "num" && b.k === "num") return { k: "num", v: a.v / b.v };
        return { k: "div", a: a, b: b };
      }
      case "pow": {
        const a = s(node.a), b = s(node.b);
        if (b.k === "num" && b.v === 1) return a;
        if (b.k === "num" && b.v === 0) return { k: "num", v: 1 };
        if (a.k === "num" && b.k === "num") return { k: "num", v: Math.pow(a.v, b.v) };
        return { k: "pow", a: a, b: b };
      }
      case "fn": {
        const args = node.args.map(s);
        if (args.every(function (g) { return g.k === "num"; })) {
          const v = evaluate({ k: "fn", name: node.name, args: args }, 0);
          if (isFinite(v)) return { k: "num", v: v };
        }
        return { k: "fn", name: node.name, args: args };
      }
      default:
        return node;
    }
  }

  /* ---------------------------------------------------------- stringify */
  const PREC = { add: 1, sub: 1, mul: 2, div: 2, neg: 3, pow: 4, atom: 6 };

  function toString(node, parentPrec) {
    parentPrec = parentPrec || 0;
    const p = PREC[node.k] || 6;
    let body;
    switch (node.k) {
      case "num":
        body = (Number.isInteger(node.v))
          ? String(node.v)
          : String(parseFloat(node.v.toFixed(6)));
        break;
      case "var": body = "x"; break;
      case "add":
        body = toString(node.a, p) + " + " + toString(node.b, p + 1); break;
      case "sub":
        body = toString(node.a, p + 1) + " − " + toString(node.b, p + 1); break;
      case "mul":
        body = toString(node.a, p) + " · " + toString(node.b, p + 1); break;
      case "div":
        body = toString(node.a, p + 1) + " / " + toString(node.b, p + 1); break;
      case "neg": body = "−" + toString(node.a, p); break;
      case "pow":
        body = toString(node.a, p + 1) + "^" + toString(node.b, p); break;
      case "fn": {
        const n = node.name;
        if (n === "sqrt") body = "√(" + toString(node.args[0], 0) + ")";
        else if (n === "ln") body = "ln(" + toString(node.args[0], 0) + ")";
        else if (n === "abs") body = "|" + toString(node.args[0], 0) + "|";
        else body = n + "(" + node.args.map(function (g) {
          return toString(g, 0);
        }).join(", ") + ")";
        break;
      }
      default: body = "?";
    }
    return p < parentPrec ? "(" + body + ")" : body;
  }

  global.Expr = {
    parse: parse,
    evaluate: evaluate,
    differentiate: function (n) { return simplify(differentiate(n)); },
    simplify: simplify,
    toString: toString,
    CONSTS: CONSTS
  };
})(window);
