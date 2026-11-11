"""§1379: does a fundamental MOVE predict the next mid move? Per book, sample every update: Δf over the last W s vs Δmid over the next H s (both in spreads).
Reports the mean next-mid move by Δf bucket and the share of the level offset (f − mid) that persists.   python3 fundpred.py <tape> [W=10] [H=20]"""
import json, sys, collections, bisect
W = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0; H = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
grp = lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec")
ser = collections.defaultdict(list)
for l in open(sys.argv[1]):
    if '"fund"' not in l or '"bids"' not in l: continue
    i = l.find('"ts": '); t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t < 58000 or t >= 90000: continue
    r = json.loads(l); f, b, a = r.get("fund"), r.get("bid"), r.get("ask")
    if f and b and a and a > b: ser[r["book"]].append((t, f, (a + b) / 2, a - b))
res = collections.defaultdict(lambda: collections.defaultdict(list)); lvl = collections.defaultdict(list)
for k, s in ser.items():
    T = [x[0] for x in s]
    for j in range(0, len(s), 3):
        t, f, m, sp = s[j]
        i0 = bisect.bisect_left(T, t - W); i1 = bisect.bisect_left(T, t + H)
        if i0 >= j or i1 >= len(s): continue
        df = (f - s[i0][1]) / sp; dm = (s[i1][2] - m) / sp
        bk = "up >0.5" if df > 0.5 else ("down <-0.5" if df < -0.5 else "flat")
        res[grp(k)][bk].append(dm); lvl[grp(k)].append(((f - m) / sp, dm))
for g in res:
    out = []
    for bk in ("up >0.5", "flat", "down <-0.5"):
        v = res[g][bk]; out.append(f"Δf {bk}: n {len(v)}, next mid {sum(v) / len(v):+.3f} spreads" if v else f"Δf {bk}: n 0")
    L = lvl[g]; pos = [dm for x, dm in L if x > 0.5]; neg = [dm for x, dm in L if x < -0.5]
    print(g, "|", " | ".join(out), f"| level f>mid: next mid {sum(pos) / max(len(pos), 1):+.3f} (n {len(pos)}), f<mid: {sum(neg) / max(len(neg), 1):+.3f} (n {len(neg)})")
