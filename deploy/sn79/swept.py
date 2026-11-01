"""Queue-position proxy (decisions.md §1207): share of maker fills followed within 1 s by the best price on the filled side moving through the
fill price (the level was swept), ours vs other miners, with 30 s markouts of swept and unswept fills. python swept.py <tape> <our uid>"""
import bisect, json, sys
from collections import defaultdict
import numpy as np
me = int(sys.argv[2]); best = defaultdict(list); fills = []
for line in open(sys.argv[1]):
    r = json.loads(line)
    if "p" in r and r.get("Ma") is not None and r["Ma"] >= 0: fills.append(r)
    elif r.get("bid") and r.get("ask"): best[r["book"]].append((r["ts"] / 1e9, r["bid"], r["ask"]))
res = {"ours": [], "field": []}
for t in fills:
    bl = best[t["book"]]; i = bisect.bisect_left(bl, (t["ts"] / 1e9 + 1.0,)); k = bisect.bisect_left(bl, (t["ts"] / 1e9 + 30,))
    if k >= len(bl): continue
    maker = 1 if t["s"] == 1 else -1
    after = bl[i][1] if maker == 1 else bl[i][2]
    swept = after < t["p"] - 1e-9 if maker == 1 else after > t["p"] + 1e-9
    res["ours" if t["Ma"] == me else "field"].append((swept, maker * ((bl[k][1] + bl[k][2]) / 2 - t["p"]) / 0.01))
for who, R in res.items():
    if not R: continue
    sw = np.array([r[0] for r in R]); mo = np.array([r[1] for r in R])
    print(f"swept within 1 s, {who:5}: {sw.mean():5.1%} of {len(R)} fills | markout swept {mo[sw].mean():+.2f}  not swept {mo[~sw].mean():+.2f}")
