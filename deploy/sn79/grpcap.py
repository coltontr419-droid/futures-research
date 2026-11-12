"""§1398: where does UID 46 out-capture x3? Last ≈ 3 sim h, per book group: fills, notional, spread at fill (bp), edge vs pre-trade mid (bp, + = good), edge $ (≈ capture),
and 24-h-equivalent notional per book vs our 450k pace (is the group pace-bound?)."""
import json, sys, collections
import os
U = {64: "x3", 46: "46", 27: "x1"}
LAYOUT = os.environ.get("LAYOUT", "256")   # §1403: "256" = sim day from 11-12 (0-127 $300 2-dec, 128-191 $30, 192-255 4-dec); "128" = legacy
grp = (lambda b: "$300" if b < 128 else ("$30" if b < 192 else "4dec")) if LAYOUT == "256" else (lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec"))
S0, S1 = float(sys.argv[1]), float(sys.argv[2]); snap = {}
A = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0, set()])
for path in sys.argv[3:]:
    for l in open(path):
        i = l.find('"ts": ')
        if i < 0: continue
        t = int(l[i + 6:l.index(",", i)]) / 1e9
        if t < S0 - 60 or t >= S1: continue
        if '"bids"' in l:
            r = json.loads(l); b, a = r.get("bid"), r.get("ask")
            if b and a and a > b: snap[r["book"]] = (b, a)
            continue
        if '"Ma"' not in l or t < S0: continue
        r = json.loads(l); u = r["Ma"]
        if u not in U: continue
        s = snap.get(r["book"])
        if not s: continue
        m = (s[0] + s[1]) / 2; buy = r["s"] == 1; edge = ((m - r["p"]) if buy else (r["p"] - m)) / m * 1e4; v = r["p"] * r["q"]
        k = (U[u], grp(r["book"])); a_ = A[k]; a_[0] += 1; a_[1] += v; a_[2] += (s[1] - s[0]) / m * 1e4 * v; a_[3] += edge * v / 1e4; a_[4].add(r["book"])
hrs = (S1 - S0) / 3600
for g in (("$300", "$30", "4dec") if LAYOUT == "256" else ("$300", "calm", "4dec")):
    for w in ("x3", "x1", "46"):
        n, v, sp, ed, bk = A[(w, g)]
        if not n: continue
        print(f"{g:4s} {w:3s}: fills {n:5d} | ${v/1e3:7.0f}k | books {len(bk):3d} | $/book/24h ≈ ${v / max(len(bk),1) / hrs * 24 / 1e3:4.0f}k | spread at fill {sp / v:5.1f} bp | edge vs mid {ed / v * 1e4:+5.2f} bp | edge $ {ed:7.0f}")
