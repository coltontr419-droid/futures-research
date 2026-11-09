"""§1322c: which taker UIDs hit our $300 / calm fills vs the fleet's, and how those fills do (kept 20 s, bp).  python3 whotakes.py <tape> <T0> <T1> fleet=.. us=.."""
import json, sys, collections
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[4:6]}; who = {u: g for g, us in G.items() for u in us}
SN = collections.defaultdict(dict); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < T0 - 5 or t > T1 + 30: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    if b >= 102: continue
    if b'"Mi"' in l:
        r = json.loads(l)
        if r["Ma"] in who and r["Ma"] != r["Ta"] and T0 <= t < T1 and r["Ta"] >= 0: F.append((t, b, r["p"], r["q"], r["s"], who[r["Ma"]], r["Ta"]))
    elif b'"bids"' in l:
        r = json.loads(l)
        if r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"] + r["ask"]) / 2
for grp, lo, hi in (("$300", 0, 63), ("calm", 63, 102)):
    print(f"== {grp}: miner takers hitting each maker group (share of that group's miner-taken $, kept bp)")
    for g in G:
        agg = collections.defaultdict(lambda: [0.0, 0.0, 0]); tot = 0.0
        for t, b, p, q, s, gg, ta in F:
            if gg != g or not (lo <= b < hi): continue
            m0 = SN[b].get(int(t) - 1); m20 = SN[b].get(int(t) + 20)
            if not m0 or not m20: continue
            k = (1 if s == 1 else -1) * (m20 - p) / m0 * 1e4; agg[ta][0] += p * q; agg[ta][1] += k * p * q; agg[ta][2] += 1; tot += p * q
        top = sorted(agg.items(), key=lambda x: -x[1][0])[:6]
        print(f"  {g}: " + " | ".join(f"UID {u} {v[0] / tot:.0%} kept {v[1] / v[0]:+.1f} (n {v[2]})" for u, v in top))
