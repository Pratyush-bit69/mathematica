import sys
from pdfxml import load

pages, fonts = load()
pnum = int(sys.argv[1]) if len(sys.argv) > 1 else 9
lo = int(sys.argv[2]) if len(sys.argv) > 2 else 0
hi = int(sys.argv[3]) if len(sys.argv) > 3 else 10**9

for p in pages:
    if p.num != pnum:
        continue
    rows = {}
    for it in p.items:
        if not (lo <= it.top <= hi):
            continue
        rows.setdefault(it.top, []).append(it)
    for top in sorted(rows):
        its = sorted(rows[top], key=lambda i: i.left)
        desc = "  ".join(
            f"[{i.left},{i.right}|{i.size:.0f}|{i.family[:10]}|{i.text[:26]}]" for i in its
        )
        print(f"t={top}: {desc}")
