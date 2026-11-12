"""§1397: x3 vs x1 per-book buy/sell $ over the last 3 sim h: notional two-sided share, net position $ (|net| median, share of books one-sided > 80%)."""
import json, sys, collections
S0, S1 = float(sys.argv[1]), float(sys.argv[2])
B = {u: collections.defaultdict(lambda: [0.0, 0.0]) for u in (64, 27)}
for path in sys.argv[3:]:
    for l in open(path):
        if '"Ma": 64,' not in l and '"Ma": 27,' not in l: continue
        r = json.loads(l); t = r["ts"] / 1e9
        if not (S0 <= t < S1): continue
        B[r["Ma"]][r["book"]][0 if r["s"] == 1 else 1] += r["p"] * r["q"]
for u, d in B.items():
    tot = sum(a + b for a, b in d.values()); two = sum(2 * min(a, b) for a, b in d.values())
    nets = sorted(abs(a - b) for a, b in d.values()); one = sum(1 for a, b in d.values() if a + b > 0 and max(a, b) / (a + b) > 0.8)
    print(f"UID {u}: books {len(d)} | ${tot/1e6:.2f}M | notional two-sided {100 * two / tot:.0f}% | |net| per book median ${nets[len(nets)//2]/1e3:.1f}k, p90 ${nets[int(.9*(len(nets)-1))]/1e3:.1f}k | books > 80% one side: {one}")
