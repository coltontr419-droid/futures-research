"""§1387: x3's per-book buy/sell balance by 30-min-ish sim block (≈ 391 sim s) and book group, last ≈ 6 h: notional, 2·min(buy,sell) share, net position $."""
import json, sys, collections
grp = lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec")
B = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0]))
for path in sys.argv[1:]:
    for l in open(path):
        if '"Ma": 64,' not in l and '"Ta": 64,' not in l: continue
        r = json.loads(l); t = r["ts"] / 1e9
        if t < 69300 or t >= 90000: continue
        mk = r["Ma"] == 64
        buy = (r["s"] == 1) if mk else (r["s"] == 0)
        k = int((t - 69300) // 391); B[(k, grp(r["book"]))][r["book"]][0 if buy else 1] += r["p"] * r["q"]
for k in sorted({k for k, g in B}):
    row = []
    for g in ("$300", "calm", "4dec"):
        d = B.get((k, g), {}); tot = sum(a + b for a, b in d.values()); two = sum(2 * min(a, b) for a, b in d.values()); net = sum(a - b for a, b in d.values())
        row.append(f"{g} ${tot/1e3:5.0f}k two-sided {100 * two / tot if tot else 0:3.0f}% net ${net/1e3:+5.0f}k")
    print(f"sim {69300 + k * 391:6d}: " + " | ".join(row))
