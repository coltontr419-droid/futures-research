"""§1358: $300 fill depth behind the own-side best (ticks, 1 s before the fill), fine buckets, fleet vs us: share of $, kept (capped ±20 bp), order age.
python3 depth300.py <tape> <T0> <T1> fleet=.. us=.."""
import json, sys, collections
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[4:6]}
who = {u: g for g, us in G.items() for u in us}; SN = collections.defaultdict(dict); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < T0 - 5 or t > T1 + 30: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    if b >= 63: continue
    if b'"Mi"' in l:
        r = json.loads(l)
        if r["Ma"] in who and r["Ma"] != r["Ta"] and T0 <= t < T1: F.append((t, b, r["p"], r["q"], r["s"], who[r["Ma"]]))
    elif b'"bids"' in l:
        r = json.loads(l)
        if r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"], r["ask"])
B = [(-10**6, -1, "inside"), (0, 0, "touch"), (1, 1, "1"), (2, 2, "2"), (3, 4, "3-4"), (5, 6, "5-6"), (7, 9, "7-9"), (10, 14, "10-14"), (15, 24, "15-24"), (25, 49, "25-49"), (50, 10**6, "50+")]
agg = {g: collections.defaultdict(lambda: [0.0, 0.0, 0]) for g in G}
for t, b, p, q, s, g in F:
    a = SN[b].get(int(t) - 1); z = SN[b].get(int(t) + 20)
    if not a or not z: continue
    buy = s == 1; d = round(((a[0] - p) if buy else (p - a[1])) / 0.01); m0 = (a[0] + a[1]) / 2
    k = max(-20, min(20, (1 if buy else -1) * ((z[0] + z[1]) / 2 - p) / m0 * 1e4))
    lab = next(l for lo, hi, l in B if lo <= d <= hi); c = agg[g][lab]; c[0] += p * q; c[1] += k * p * q; c[2] += 1
for g in G:
    D = sum(v[0] for v in agg[g].values())
    print(f"== {g}: " + " | ".join(f"{l} {agg[g][l][0] / D:.0%} kept {agg[g][l][1] / agg[g][l][0]:+.1f}" for lo, hi, l in B if agg[g][l][0]))
