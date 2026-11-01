"""Stronger back-off variants of the near-touch flow pull (decisions.md §1207), scored like pull_oos.py on the second half of each tape:
window W (s) for the near-touch imbalance; cooldown C (s) = the side stays pulled C seconds after the imbalance last crossed THR.
Per fill: blocked if max over the last C+1 seconds of the signed W-second imbalance (computed from seconds before the fill) > THR."""
import bisect, json, sys
from collections import defaultdict
import numpy as np
TICK, H = 0.01, 30
def load(path, me):
    mids, of, fills = defaultdict(list), defaultdict(dict), []
    for line in open(path):
        r = json.loads(line); s = r["ts"] // 1_000_000_000
        if "of" in r:
            o = of[r["book"]].setdefault(s, [0.0, 0.0])
            o[0] += r["of"].get("nb2", 0.0); o[1] += r["of"].get("na2", 0.0)
        elif "p" in r:
            if r["Ma"] == me: fills.append(r)
        elif r.get("bid") and r.get("ask"):
            mids[r["book"]].append((r["ts"] / 1e9, (r["bid"] + r["ask"]) / 2))
    out = []
    for t in fills:
        b, s = t["book"], t["ts"] // 1_000_000_000; ms = mids[b]; i = bisect.bisect_left(ms, (t["ts"] / 1e9 + H,))
        if i >= len(ms): continue
        maker = 1 if t["s"] == 1 else -1
        out.append((b, s, -maker, maker * (ms[i][1] - t["p"]) / TICK))
    return of, out
def near(of, b, end, w):
    nb = sum(of[b].get(end - j, [0, 0])[0] for j in range(w)); na = sum(of[b].get(end - j, [0, 0])[1] for j in range(w))
    return (nb - na) / (nb + na) if nb + na > 0 else 0.0
me = int(sys.argv[1]); res = defaultdict(list)
for p in sys.argv[2:]:
    of, fills = load(p, me); h = len(fills) // 2
    for w in (3, 5, 10):
        for c in (0, 3, 10):
            for thr in (0.2, 0.3, 0.4, 0.5):
                sig = np.array([max(exp * near(of, b, s - 1 - k, w) for k in range(c + 1)) for b, s, exp, mo in fills])
                mo = np.array([f[3] for f in fills]); blk = sig > thr
                res[(w, c, thr)].append((mo[:h][~blk[:h]].sum(), mo[h:][~blk[h:]].sum(), (~blk[h:]).sum(), len(fills) - h, mo[h:].sum()))
# pick (w, c, thr) by first-half kept total summed over tapes, report second-half kept mean per fill and kept share
rank = sorted(res, key=lambda k: -sum(x[0] for x in res[k]))
print("second half, all tapes pooled: kept ticks per kept fill (share of fills kept); baseline (no rule) =",
      f"{sum(x[4] for x in res[rank[0]]) / sum(x[3] for x in res[rank[0]]):+.2f}")
for k in rank[:8] + [(5, 0, 0.3)]:
    kept = sum(x[1] for x in res[k]); n = sum(x[2] for x in res[k]); tot = sum(x[3] for x in res[k])
    print(f"  window {k[0]:2d}s cooldown {k[1]:2d}s thr {k[2]}: kept {kept / n:+.2f}/fill ({n / tot:.0%} kept), kept total {kept:+.0f}"
          f"{'   <- deployed' if k == (5, 0, 0.3) else ''}{'   <- best on 1st half' if k == rank[0] else ''}")
