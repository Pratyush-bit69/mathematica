import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
d = open(os.path.join(ROOT, "assets", "data", "treatise.js"),
         encoding="utf-8").read()
o = json.loads(d[len("window.TREATISE = "):-2])

cn = int(sys.argv[1]) if len(sys.argv) > 1 else 1
lim = int(sys.argv[2]) if len(sys.argv) > 2 else 40
ch = [c for c in o["chapters"] if c["num"] == cn][0]
print("=" * 70)
print("CHAPTER", ch["num"], ch["title"])
for s in ch["sections"]:
    print(f"  §{s['num']} {s['title'][:70]}  ({len(s['blocks'])} blocks)")
print("-" * 70)
n = 0
for s in ch["sections"]:
    print(f"\n### §{s['num']} {s['title'][:70]}")
    for b in s["blocks"]:
        n += 1
        if n > lim:
            print("...")
            break
        kind = b.get("type")
        title = b.get("title", "")
        num = b.get("num", "")
        if kind in ("theorem", "example", "problem", "exam", "tier", "section"):
            print(f"  <{kind} {num}> {title[:70]}")
        else:
            runs = b.get("runs", [])
            txt = ""
            for r in runs:
                if r["k"] == "text":
                    txt += r["v"]
                else:
                    txt += " «" + r.get("latex", "")[:40] + "»"
            print(f"  [{kind}] {txt[:160]}")
    if n > lim:
        break
