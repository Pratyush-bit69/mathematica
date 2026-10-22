import collections
from pdfxml import load

pages, fonts = load()
chars = collections.defaultdict(collections.Counter)
sizes = collections.defaultdict(collections.Counter)
for p in pages:
    for it in p.items:
        for ch in it.text:
            chars[it.family][ch] += 1
        sizes[it.family][it.size] += 1

for fam in sorted(chars):
    c = chars[fam]
    print(f"### {fam}  ({len(c)} distinct)  sizes={sorted(sizes[fam])}")
    print("   " + " ".join(f"{ch!r}:{n}" for ch, n in c.most_common()))
    print()
