"""MVTRX UID 213 decay diagnosis: per sim-hour, our maker fills vs the field's, split by taker class (bot = Ta >= 0, background = Ta < 0).
captured = signed (mid at fill - price), realized20 = signed (mid 20 s later - price), in cents; book mid (approximation of the print mid)."""
import bisect, json, sys
from collections import defaultdict
path, me = sys.argv[1], int(sys.argv[2])
mids = defaultdict(list); fills = []; seen = set()
for line in open(path):
    r = json.loads(line)
    if "p" in r:
        k = (r["book"], r.get("id"), r["ts"])
        if k in seen or r.get("Ma") is None or r["Ma"] < 0: continue
        seen.add(k); fills.append(r)
    elif r.get("bid") and r.get("ask"):
        mids[r["book"]].append((r["ts"] / 1e9, (r["bid"] + r["ask"]) / 2))
for b in mids: mids[b].sort()
secs = {b: [t for t, _ in v] for b, v in mids.items()}
def mid(b, t):
    i = bisect.bisect_right(secs[b], t) - 1
    return mids[b][i][1] if i >= 0 else None
agg = defaultdict(lambda: [0, 0.0, 0.0, 0.0])         # (hour, who, cls) -> n, qty, Σq·cap, Σq·real
t0 = min(f["ts"] for f in fills) / 1e9
for f in fills:
    t = f["ts"] / 1e9; b = f["book"]; m0, m1 = mid(b, t), mid(b, t + 20)
    if m0 is None or m1 is None or t + 20 > secs[b][-1]: continue
    sg = 1 if f["s"] == 1 else -1                       # +1 maker bought
    who = "ours" if f["Ma"] == me else "field"; cls = "bot" if (f.get("Ta") is not None and f["Ta"] >= 0) else "bg"
    h = int((t - t0) // 3600)
    for c in (cls, "all"):
        a = agg[(h, who, c)]; a[0] += 1; a[1] += f["q"]; a[2] += f["q"] * sg * (m0 - f["p"]) * 100; a[3] += f["q"] * sg * (m1 - f["p"]) * 100
print("sim h | ours: fills  qty  bot-share | cap c  real20 c  R/C (all) | bot R/C  bg R/C || field: cap c real20 c R/C")
for h in sorted({k[0] for k in agg}):
    o, ob, og, fl = agg[(h, "ours", "all")], agg[(h, "ours", "bot")], agg[(h, "ours", "bg")], agg[(h, "field", "all")]
    rc = lambda a: a[3] / a[2] if a[2] else float("nan"); pq = lambda a, i: a[i] / a[1] if a[1] else float("nan")
    print(f"{h:4d} | {o[0]:5d} {o[1]:7.0f} {ob[1] / o[1] if o[1] else 0:5.2f} | {pq(o,2):6.2f} {pq(o,3):7.2f} {rc(o):6.2f} | {rc(ob):6.2f} {rc(og):6.2f} || {pq(fl,2):6.2f} {pq(fl,3):6.2f} {rc(fl):6.2f}")
