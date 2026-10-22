import collections
from pdfxml import load

pages, fonts = load()
ctx = collections.defaultdict(list)
for p in pages:
    items = sorted(p.items, key=lambda i: (i.top, i.left))
    for idx, it in enumerate(items):
        if it.family == "CMEX10":
            ctx[it.text].append((p.num, it.top, it.left, " ".join(x.text for x in items[max(0, idx - 4):idx + 5])))
for ch, lst in sorted(ctx.items(), key=lambda kv: -len(kv[1])):
    print(f"=== {ch!r}  x{len(lst)}")
    for row in lst[:3]:
        print("   ", row)
