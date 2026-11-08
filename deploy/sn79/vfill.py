"""§1308: per-fill making marks the way the VALIDATOR computes them (debeta.accumulate_book_capture, simplified): captured = maker side × (print-centred mid − price) × q,
where the centred mid is the size-weighted mean price of the W=15 prints before and after the fill; realized = maker side × (mark − price) × q, mark = size-weighted
mean of the background-sided prints (Ma or Ta < 0) in the ±15-print window around the first print ≥ 20 sim s after the fill. Quality = Σ realized ÷ Σ captured.
A/B with a 1-sim-minute block bootstrap.   python vfill.py <tape> <t0> <t1> <A=uids> <B=uids>"""
import json, sys, collections, bisect, random, statistics as st
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); A = (sys.argv[4].split("=")[0], {int(x) for x in sys.argv[4].split("=")[1].split(",")})
Bg = (sys.argv[5].split("=")[0], {int(x) for x in sys.argv[5].split("=")[1].split(",")}); W, H = 15, 20.0
P = collections.defaultdict(list); seen = set()
for l in open(tape, "rb"):
    if b'"Ta": ' not in l: continue
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < T0 - 300 or t > T1 + 300: continue
    r = json.loads(l); k = (r["book"], r.get("id"), r["ts"])
    if k in seen or r["book"] >= 102: continue
    seen.add(k); P[r["book"]].append((t, r["p"], r["q"], r.get("Ma", -1), r.get("Ta", -1), r["s"]))
rows = []
for b, pr in P.items():
    pr.sort(); ts = [x[0] for x in pr]; n = len(pr)
    for i, (t, p, q, ma, ta, s) in enumerate(pr):
        g = A[0] if ma in A[1] else Bg[0] if ma in Bg[1] else None
        if g is None or not (T0 <= t < T1) or ma == ta: continue
        lo, hi = max(0, i - W), min(n, i + W + 1); win = pr[lo:hi]
        cm = sum(x[1] * x[2] for x in win) / sum(x[2] for x in win)
        j = bisect.bisect_left(ts, t + H)
        if j >= n: continue
        lo2, hi2 = max(0, j - W), min(n, j + W + 1); w2 = [x for x in pr[lo2:hi2] if (x[3] is None or x[3] < 0) or (x[4] is None or x[4] < 0)] or pr[lo2:hi2]
        mark = sum(x[1] * x[2] for x in w2) / sum(x[2] for x in w2)
        mk = 1 if s == 1 else -1                                   # side 1: maker buys
        rows.append((g, "$300" if b < 63 else "calm", t, mk * (cm - p) * q, mk * (mark - p) * q, p * q))
def qual(v): c = sum(x[3] for x in v); r_ = sum(x[4] for x in v); return (r_ / c if c else float("nan")), c, r_
for grp in ("$300", "calm"):
    va = [x for x in rows if x[0] == A[0] and x[1] == grp]; vb = [x for x in rows if x[0] == Bg[0] and x[1] == grp]
    if not va or not vb: continue
    qa, ca, ra = qual(va); qb, cb, rb = qual(vb)
    ba = collections.defaultdict(list); bb = collections.defaultdict(list)
    for x in va: ba[int(x[2] // 60)].append(x)
    for x in vb: bb[int(x[2] // 60)].append(x)
    la, lb = list(ba.values()), list(bb.values()); rng = random.Random(3); d = []
    for _ in range(600):
        sa = [y for blk in (rng.choice(la) for _ in la) for y in blk]; sb = [y for blk in (rng.choice(lb) for _ in lb) for y in blk]
        qa_, _, _ = qual(sa); qb_, _, _ = qual(sb)
        if qa_ == qa_ and qb_ == qb_: d.append(qa_ - qb_)
    se = st.pstdev(d) if d else float("nan")
    print(f"{grp}: {A[0]} {len(va)} fills, captured {ca:+.1f}, realized {ra:+.1f}, QUALITY {qa:.2f} | {Bg[0]} {len(vb)} fills, captured {cb:+.1f}, realized {rb:+.1f}, QUALITY {qb:.2f} | diff {qa - qb:+.2f} ± {se:.2f} → {abs(qa - qb) / se if se == se and se else float('nan'):.1f} noise widths")
