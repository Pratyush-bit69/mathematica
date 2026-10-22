import sys
from pdfxml import load

pages, fonts = load()
pnum = int(sys.argv[1]) if len(sys.argv) > 1 else 9
lo = int(sys.argv[2]) if len(sys.argv) > 2 else 0
hi = int(sys.argv[3]) if len(sys.argv) > 3 else 10**9

for p in pages:
    if p.num != pnum:
        continue
    for it in sorted(p.items, key=lambda i: (i.top, i.left)):
        if not (lo <= it.top <= hi):
            continue
        print(
            f"t={it.top:>4} l={it.left:>4} r={it.right:>4} w={it.width:>3} "
            f"sz={it.size:>4.1f} {it.family[:18]:<18} | {it.text[:40]}"
        )
