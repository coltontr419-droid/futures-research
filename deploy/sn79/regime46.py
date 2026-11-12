"""§1404: how UID 46 (reference) and others trade the NEW books (new sim, ts < 30,000): per group ($300 0–127 / $30 128–191 / 4dec 192–255): fills, $, books, edge vs mid bp,
depth in ticks behind the touch (median / p75), fill $ median. Rows: x3, x1, 46, 216."""
import json, sys, collections
U = {64: "x3", 27: "x1", 46: "46", 216: "216"}; grp = lambda b: "$300" if b < 128 else ("$30" if b < 192 else "4dec")
snap = {}; tick = {}; A = collections.defaultdict(lambda: [0, 0.0, 0.0, [], [], set()])
for l in open(sys.argv[1]):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t > 30000: continue
    if '"bids"' in l:
        r = json.loads(l); bb = r.get("bids") or []; aa = r.get("asks") or []
        if bb and aa:
            snap[r["book"]] = (bb[0][0], aa[0][0])
            px = [x[0] for x in bb[:5]] + [x[0] for x in aa[:5]]
            d = [round(abs(a - c), 8) for a, c in zip(px, px[1:]) if abs(a - c) > 1e-9]
            if d: tick[r["book"]] = min(d + ([tick[r["book"]]] if r["book"] in tick else []))
        continue
    if '"Ma"' not in l: continue
    r = json.loads(l); u = r["Ma"]
    if u not in U: continue
    b = r["book"]; s = snap.get(b); tk = tick.get(b)
    if not s or not tk: continue
    m = (s[0] + s[1]) / 2; buy = r["s"] == 1; v = r["p"] * r["q"]
    ref = s[0] if buy else s[1]; dep = round(((ref - r["p"]) if buy else (r["p"] - ref)) / tk)
    a = A[(grp(b), U[u])]; a[0] += 1; a[1] += v; a[2] += ((m - r["p"]) if buy else (r["p"] - m)) / m * v; a[3].append(dep); a[4].append(v); a[5].add(b)
q = lambda x, p: sorted(x)[int(p * (len(x) - 1))] if x else float("nan")
for g in ("$300", "$30", "4dec"):
    for w in ("x3", "x1", "46", "216"):
        n, v, e, d, f, bk = A[(g, w)]
        if n: print(f"{g:4s} {w:3s}: fills {n:5d} | ${v/1e3:6.0f}k on {len(bk):3d} books | edge {e / v * 1e4:+6.2f} bp | depth ticks med {q(d, .5):.0f} p75 {q(d, .75):.0f} p90 {q(d, .9):.0f} | ahead {100 * sum(x < 0 for x in d) / n:3.0f}% | fill $ med {q(f, .5):,.0f}")
