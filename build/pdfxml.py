"""Parse pdftohtml -xml output into positioned text items with a global font table."""
import re
import html
from dataclasses import dataclass, field

XML_PATH = "/tmp/opencode/mathpdf/doc.xml"

TEXT_RE = re.compile(
    r'<text top="(?P<top>-?\d+)" left="(?P<left>-?\d+)" width="(?P<width>\d+)" '
    r'height="(?P<height>\d+)" font="(?P<font>\d+)">(?P<text>.*?)</text>',
    re.S,
)
FONTSPEC_RE = re.compile(
    r'<fontspec id="(?P<id>\d+)" size="(?P<size>[\d.]+)" family="(?P<family>[^"]*)"'
)
PAGE_RE = re.compile(r'<page number="(?P<num>\d+)"[^>]*>')


@dataclass
class Item:
    page: int
    top: int
    left: int
    width: int
    height: int
    size: float
    family: str
    text: str
    bold: bool = False
    color: str = "#000000"
    # vertical baseline estimate
    @property
    def baseline(self) -> float:
        return self.top + self.size * 0.78

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def cx(self) -> float:
        return self.left + self.width / 2.0


@dataclass
class Page:
    num: int
    width: int = 918
    height: int = 1188
    items: list = field(default_factory=list)


def load(path: str = XML_PATH):
    with open(path, encoding="utf-8") as fh:
        data = fh.read()

    fonts = {}  # id -> (size, family, color)
    for m in FONTSPEC_RE.finditer(data):
        fid = m.group("id")
        color = "#000000"
        # colour may follow family
        tail = data[m.end(): m.end() + 80]
        cm = re.search(r'color="(#[0-9a-fA-F]{6})"', tail)
        if cm:
            color = cm.group(1)
        fonts[fid] = (float(m.group("size")), m.group("family"), color)

    pages = []
    cur = None
    pos = 0
    for pm in PAGE_RE.finditer(data):
        if cur is not None:
            end = data.find("</page>", pos)
            cur.items = _parse_items(data[pos:end], cur.num, fonts)
            pages.append(cur)
        pos = pm.end()
        cur = Page(num=int(pm.group("num")))
    if cur is not None:
        end = data.find("</page>", pos)
        cur.items = _parse_items(data[pos:end], cur.num, fonts)
        pages.append(cur)
    return pages, fonts


def _parse_items(chunk: str, pnum: int, fonts):
    out = []
    for m in TEXT_RE.finditer(chunk):
        raw = m.group("text")
        bold = "<b>" in raw
        txt = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
        txt = txt.replace(" ", " ")
        fid = m.group("font")
        size, family, color = fonts.get(fid, (13.0, "URWPalladioL", "#000000"))
        if not txt:
            # keep zero-width overlays (combining slash) but mark them
            if raw.strip() in ("<b></b>", ""):
                pass
        fam = family.split("+")[-1]
        out.append(
            Item(
                page=pnum,
                top=int(m.group("top")),
                left=int(m.group("left")),
                width=int(m.group("width")),
                height=int(m.group("height")),
                size=size,
                family=fam,
                text=txt,
                bold=bold,
                color=color,
            )
        )
    return out


if __name__ == "__main__":
    pages, fonts = load()
    print("pages:", len(pages))
    print("fonts:", len(fonts))
    total = sum(len(p.items) for p in pages)
    print("items:", total)
    for p in pages[:3]:
        print(p.num, len(p.items))
