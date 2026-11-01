"""Where does the field's +1.2 tick markout come from? Maker fills by maker (us vs every other miner, and the top makers), split by taker class
(another miner vs background), with 30 s markouts and fill size. python field_split.py <our uid> <tape>"""
import bisect, json, sys
from collections import defaultdict
import numpy as np
me = int(sys.argv[1]); mids = defaultdict(list); fills = []
for line in open(sys.argv[2]):
    r = json.loads(line)
    if "p" in r and r.get("Ma") is not None and r["Ma"] >= 0: fills.append(r)
    elif r.get("bid") and r.get("ask"): mids[r["book"]].append((r["ts"] / 1e9, (r["bid"] + r["ask"]) / 2, r["ask"] - r["bid"]))
rows = defaultdict(list)
for t in fills:
    ms = mids[t["book"]]; i = bisect.bisect_left(ms, (t["ts"] / 1e9 + 30,)); j = bisect.bisect_left(ms, (t["ts"] / 1e9,)) - 1
    if i >= len(ms) or j < 0: continue
    maker = 1 if t["s"] == 1 else -1; mo = maker * (ms[i][1] - t["p"]) / 0.01
    edge = maker * (ms[j][1] - t["p"]) / 0.01                 # how far inside the pre-fill mid we got filled (half-spread captured)
    bot = t["Ta"] is not None and t["Ta"] >= 0
    rows["ours" if t["Ma"] == me else "others"].append((bot, mo, edge, t["q"], t["Ma"]))
for who in ("ours", "others"):
    R = rows[who]; bot = np.array([r[0] for r in R]); mo = np.array([r[1] for r in R]); ed = np.array([r[2] for r in R]); q = np.array([r[3] for r in R])
    print(f"== {who}: {len(R)} fills, bot-taken {bot.mean():.0%}")
    for name, m in (("bot taker", bot), ("background", ~bot)):
        print(f"   {name:10}: markout {mo[m].mean():+.2f} (size-wtd {np.average(mo[m], weights=q[m]):+.2f}) | captured at fill {ed[m].mean():+.2f} ticks | "
              f"after-fill move {np.mean(mo[m] - ed[m]):+.2f} | median size {np.median(q[m]):.2f}")
others = rows["others"]; by = defaultdict(list)
for r in others: by[r[4]].append(r)
top = sorted(by, key=lambda u: -len(by[u]))[:8]
print("top makers: uid, fills, bot-taken share, markout, captured at fill")
for u in top:
    R = by[u]; b = np.array([r[0] for r in R]); mo = np.array([r[1] for r in R]); ed = np.array([r[2] for r in R])
    print(f"   {u:4d} {len(R):6d}  bot {b.mean():4.0%}  markout {mo.mean():+.2f}  captured {ed.mean():+.2f}")
