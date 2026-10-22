"""Math AST: node types + LaTeX / HTML serializers.

The extractor builds a small tree of math nodes from PDF geometry.  Each node can
render itself either as LaTeX (for KaTeX) or as HTML+Unicode (fallback), so a
span that cannot be expressed in LaTeX still looks good.
"""

# ---------------------------------------------------------------- char tables

LATEX = {
    "−": "-", "–": "--", "—": "---",
    "→": r"\to", "⇒": r"\Rightarrow", "⇐": r"\Leftarrow",
    "⇐⇒": r"\Leftrightarrow", "↔": r"\leftrightarrow",
    "|": r"\vert", "‖": r"\Vert", "∥": r"\parallel",
    "•": r"\bullet", "·": r"\cdot", "∗": r"*",
    "×": r"\times", "÷": r"\div", "±": r"\pm", "∓": r"\mp",
    "≥": r"\geq", "≤": r"\leq", "≠": r"\neq", "≈": r"\approx",
    "≡": r"\equiv", "∼": r"\sim", "≁": r"\nsim", "≻": r"\succ", "⪰": r"\succeq",
    "⪯": r"\preceq", "≪": r"\ll",
    "∈": r"\in", "∉": r"\notin", "∋": r"\ni",
    "⊆": r"\subseteq", "⊂": r"\subset", "⊃": r"\supset", "⊇": r"\supseteq",
    "∪": r"\cup", "∩": r"\cap", "∅": r"\emptyset", "∀": r"\forall", "∃": r"\exists",
    "¬": r"\neg", "∧": r"\wedge", "∨": r"\vee", "⊙": r"\odot", "⊗": r"\otimes",
    "⊤": r"\top", "⊥": r"\perp", "∇": r"\nabla", "∂": r"\partial",
    "⌊": r"\lfloor", "⌋": r"\rfloor", "⌈": r"\lceil", "⌉": r"\rceil",
    "⟨": r"\langle", "⟩": r"\rangle",
    "√": r"\sqrt{}", "∞": r"\infty",
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∬": r"\iint",
    "∆": r"\Delta", "Σ": r"\Sigma", "Π": r"\Pi", "Ω": r"\Omega",
    "Γ": r"\Gamma", "Λ": r"\Lambda", "Φ": r"\Phi", "Θ": r"\Theta",
    "π": r"\pi", "θ": r"\theta", "σ": r"\sigma", "λ": r"\lambda",
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\epsilon", "ϵ": r"\varepsilon", "ω": r"\omega", "τ": r"\tau",
    "ρ": r"\rho", "κ": r"\kappa", "η": r"\eta", "φ": r"\varphi", "ϕ": r"\phi",
    "ξ": r"\xi", "ν": r"\nu", "ψ": r"\psi", "ζ": r"\zeta",
    "ι": r"\iota", "χ": r"\chi", "µ": r"\mu",
    "′": "'", "\\": r"\backslash", "△": r"\triangle", "◦": r"\circ",
    "ℓ": r"\ell", "̸": "", "˙": "", "ˆ": "", "˜": "",
    "¯": "", "¨": "", "°": r"^\circ",
    "≁": r"\nsim", "∤": r"\nmid", "∦": r"\nparallel",
    "∠": r"\angle", "⊛": r"\circledast", "■": r"\blacksquare",
}

# blackboard bold (PazoMathBlackboardBold)
BB = {"E": r"\mathbb{E}", "R": r"\mathbb{R}", "P": r"\mathbb{P}",
      "Q": r"\mathbb{Q}", "N": r"\mathbb{N}", "Z": r"\mathbb{Z}",
      "C": r"\mathbb{C}", "I": r"\mathbb{I}", "W": r"\mathbb{W}"}

# calligraphic (CMSY10 letters)
CAL = {c: "\\mathcal{%s}" % c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}

# operator names rendered upright in math
OPNAMES = ["sin", "cos", "tan", "cot", "sec", "csc", "sinh", "cosh", "tanh",
           "arcsin", "arccos", "arctan", "log", "ln", "exp", "lim", "sup",
           "inf", "max", "min", "det", "dim", "ker", "deg", "gcd", "mod",
           "arg", "tr", "rank", "eig", "var", "cov", "median", "mode",
           "sign", "sgn", "Re", "Im", "E", "Pr", "operatorname"]

# upright multi-letter words that live in math runs but are plain text
MATH_WORDS = {"sin", "cos", "tan", "cot", "sec", "csc", "sinh", "cosh", "tanh",
              "log", "ln", "exp", "lim", "det", "dim", "ker", "deg", "gcd",
              "mod", "arg", "max", "min", "sup", "inf", "rank", "tr", "sgn",
              "arcsin", "arccos", "arctan", "sign", "cov", "var", "eig"}


# extensible-delimiter glyph pieces that carry no useful character
SKIP_CHARS = set(
    chr(c) for c in (
        0xF8EB, 0xF8EC, 0xF8ED, 0xF8EE, 0xF8EF, 0xF8F0,
        0xF8F1, 0xF8F2, 0xF8F3, 0xF8F4, 0xF8F6, 0xF8F7,
        0xF8F8, 0xF8F9, 0xF8FA, 0xF8FB,
    )
)


def esc_text(s: str) -> str:
    """Escape plain text for HTML."""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def esc_latex(s: str) -> str:
    out = []
    for ch in s:
        if ch in "\\{}$&#^_%~":
            out.append("\\" + ch)
        elif ch == "%":
            out.append("\\%")
        elif 0x0300 <= ord(ch) <= 0x036F:
            continue          # stray combining marks LaTeX cannot take
        else:
            out.append(ch)
    return "".join(out)


_CTRL = None


def finalize(tex: str) -> str:
    """TeX control words swallow following letters — separate them.

    Scans manually so that a command name is always taken in full
    (``\\mathbb`` must not be split into ``\\math`` + ``b``).
    """
    out = []
    i = 0
    n = len(tex)
    while i < n:
        ch = tex[i]
        if ch == "\\":
            j = i + 1
            while j < n and tex[j].isalpha():
                j += 1
            if j > i + 1:
                out.append(tex[i:j])
                if j < n and tex[j].isalpha():
                    out.append(" ")
                i = j
                continue
        out.append(ch)
        i += 1
    return "".join(out)


# ------------------------------------------------------------------- nodes

class Node:
    def latex(self) -> str:
        raise NotImplementedError

    def html(self) -> str:
        raise NotImplementedError


class Text(Node):
    """Literal upright text inside math. Padding spaces live inside the
    braces, exactly as the original LaTeX would have written them."""
    def __init__(self, s):
        self.s = s

    def _clean(self):
        return (self.s.replace("̸=", "≠")
                    .replace("̸", "")
                    .replace("˜", "~"))

    def latex(self):
        return r"\text{" + esc_latex(self._clean()) + "}"

    def html(self):
        return f'<span class="mt">{esc_text(self._clean())}</span>'

class Sym(Node):
    """A single symbol / variable with a role."""
    def __init__(self, s, role="var"):
        self.s = s
        self.role = role  # var | op | sym | bb | cal

    def _map(self):
        if self.s in SKIP_CHARS:
            return ""
        if self.role == "bb" and self.s in BB:
            return BB[self.s]
        if self.role == "cal" and self.s in CAL:
            return CAL[self.s]
        if self.role == "op" and self.s in MATH_WORDS:
            return "\\" + self.s
        s = self.s.replace("̸=", "≠").replace("̸", "")
        if s in LATEX:
            return LATEX[s]
        if len(s) > 1 and all(c in LATEX for c in s):
            return "".join(LATEX[c] for c in s)
        return esc_latex(s)

    def latex(self):
        return self._map()

    def html(self):
        m = self._map()
        if m.startswith("\\") and m[1:].isalpha():
            m = "\\" + m[1:]
        ch = self.s
        if ch in ("∪", "∩", "∈", "⊆", "⇒", "∂", "∇", "∑", "∏", "∞"):
            return f'<span class="msym">{esc_text(ch)}</span>'
        return f'<span class="mvar">{esc_text(ch)}</span>'


def _ends_with_cmd(s: str) -> bool:
    """True when s ends with a TeX control word such as ``\\vert``."""
    i = len(s) - 1
    while i >= 0 and s[i].isalpha():
        i -= 1
    return i >= 0 and s[i] == "\\" and (len(s) - 1 - i) > 0


def join_latex(strings) -> str:
    """Concatenate LaTeX fragments, separating a trailing command word from a
    following letter (TeX would otherwise swallow it)."""
    out = ""
    for s in strings:
        if out and s and _ends_with_cmd(out) and s[0].isalpha():
            out += " "
        out += s
    return out


class Run(Node):
    def __init__(self, parts):
        self.parts = parts

    def latex(self):
        return finalize(join_latex([p.latex() for p in self.parts]))

    def html(self):
        return "".join(p.html() for p in self.parts)


class Script(Node):
    """base with a superscript and/or subscript."""
    def __init__(self, base, sup=None, sub=None):
        self.base = base
        self.sup = sup
        self.sub = sub

    def latex(self):
        b = self.base.latex()
        sup = self.sup.latex() if self.sup is not None else None
        sub = self.sub.latex() if self.sub is not None else None
        if not b:
            # orphan script — wrap so it stays a legal group
            inner = []
            if sup is not None:
                inner.append("^{" + sup + "}")
            if sub is not None:
                inner.append("_{" + sub + "}")
            return "{" + "".join(inner) + "}" if inner else ""
        out = b
        if sup is not None:
            out += "^{" + sup + "}"
        if sub is not None:
            out += "_{" + sub + "}"
        return out

    def html(self):
        b = self.base.html()
        if self.sup is not None:
            b += f'<sup class="msup">{self.sup.html()}</sup>'
        if self.sub is not None:
            b += f'<sub class="msub">{self.sub.html()}</sub>'
        return b


ACCENTS = {
    "ˆ": ("hat", "̂"), "˜": ("tilde", "̃"),
    "¯": ("bar", "̄"), "˙": ("dot", "̇"),
    "¨": ("ddot", "̈"),
}


class Accent(Node):
    """An accent applied to the preceding symbol."""
    def __init__(self, base, kind):
        self.base = base
        self.kind = kind

    def latex(self):
        return "\\" + self.kind + "{" + self.base.latex() + "}"

    def html(self):
        mark = ACCENTS_MARK.get(self.kind, "&#770;")
        return ('<span class="maccent">' + self.base.html() +
                '<span class="macc">' + mark + "</span></span>")


ACCENTS_MARK = {"hat": "&#770;", "tilde": "&#771;", "bar": "&#773;",
                "dot": "&#775;", "ddot": "&#776;"}


class Frac(Node):
    def __init__(self, num, den):
        self.num = num
        self.den = den

    def latex(self):
        return "\\frac{" + self.num.latex() + "}{" + self.den.latex() + "}"

    def html(self):
        return (f'<span class="mfrac"><span class="mnum">{self.num.html()}'
                f'</span><span class="mden">{self.den.html()}</span></span>')


class Sqrt(Node):
    def __init__(self, radicand):
        self.radicand = radicand

    def latex(self):
        return "\\sqrt{" + self.radicand.latex() + "}"

    def html(self):
        return f'<span class="msqrt"><span class="mrad">√</span><span class="mradicand">{self.radicand.html()}</span></span>'


class BigOp(Node):
    """Large operator with limits above/below."""
    def __init__(self, sym, sup=None, sub=None):
        self.sym = sym
        self.sup = sup
        self.sub = sub

    def latex(self):
        s = LATEX.get(self.sym, self.sym)
        out = s
        if self.sup is not None:
            out += "^{" + self.sup.latex() + "}"
        if self.sub is not None:
            out += "_{" + self.sub.latex() + "}"
        return out

    def html(self):
        lim = ""
        if self.sup is not None:
            lim += f'<span class="mlim msup">{self.sup.html()}</span>'
        if self.sub is not None:
            lim += f'<span class="mlim msub">{self.sub.html()}</span>'
        ch = self.sym
        return (f'<span class="mbigop"><span class="mop">{esc_text(ch)}</span>'
                f'<span class="mlims">{lim}</span></span>')


class Matrix(Node):
    def __init__(self, rows, delim="bmatrix"):
        self.rows = rows
        self.delim = delim

    def latex(self):
        body = " \\\\ ".join(
            " & ".join(c.latex() for c in row) for row in self.rows)
        env = {"bmatrix": "bmatrix", "pmatrix": "pmatrix",
               "vmatrix": "vmatrix", "matrix": "matrix"}[self.delim]
        return f"\\begin{{{env}}}\n{body}\n\\end{{{env}}}"

    def html(self):
        rows = ""
        for row in self.rows:
            cells = "".join(f"<td>{c.html()}</td>" for c in row)
            rows += f"<tr>{cells}</tr>"
        return (f'<span class="mmtx"><table class="mmat">{rows}</table></span>')


class Brace(Node):
    """Explicit big delimiter pair."""
    def __init__(self, left, body, right=None):
        self.left = left
        self.body = body
        self.right = right

    def latex(self):
        l = self.left if self.left else "."
        r = self.right if self.right else ""
        return f"\\left{l} {self.body.latex()} \\right{r}" if r else \
               f"\\left{l} {self.body.latex()} \\right."

    def html(self):
        return (f'<span class="mdelim"><span class="mdl">{esc_text(self.left)}</span>'
                f'<span class="mdb">{self.body.html()}</span>'
                f'<span class="mdr">{esc_text(self.right or "")}</span></span>')


class Spacer(Node):
    def __init__(self, w=1):
        self.w = w

    def latex(self):
        return r"\ " * self.w

    def html(self):
        return '<span class="mspace"></span>'
