"""§1368: are our $300 fills hit right after the book's FUNDAMENTAL moved against the order (before the mid follows)? Per fill: Δfund over the prior N s
(bp, signed so − = the fundamental moved against the maker's side), kept and the mid move after; fleet vs us.  python3 fundmove.py <tape> <T0> <T1> <N> fleet=.. us=.."""
import json, sys, collections
tape, T0, T1, N = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[5:7]}; who = {u: g for g, us in G.items() for u in us}
SN = collections.defaultdict(dict); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < T0 - 60 or t > T1 + 30: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    if b >= 63: continue
    if b'"Mi"' in l:
        r = json.loads(l)
        if r["Ma"] in who and r["Ma"] != r["Ta"] and T0 <= t < T1: F.append((t, b, r["p"], r["q"], r["s"], who[r["Ma"]]))
    elif b'"bids"' in l:
        r = json.loads(l)
        if r["bids"] and r["asks"] and r.get("fund"): SN[b][int(t)] = ((r["bid"] + r["ask"]) / 2, r["fund"])
rows = []
for t, b, p, q, s, g in F:
    a = SN[b].get(int(t) - 1); z = SN[b].get(int(t) + 20); o = SN[b].get(int(t) - 1 - N)
    if not a or not z or not o: continue
    sg = 1 if s == 1 else -1; m0, f0 = a; m1 = z[0]
    dfund = sg * (f0 - o[1]) / m0 * 1e4                 # + = fundamental moved in the maker's favour (up for a bid) before the fill
    gap_f = sg * (f0 - m0) / m0 * 1e4                   # + = fundamental above the mid for a bid (favourable lean)
    rows.append((g, p * q, max(-20, min(20, sg * (m1 - p) / m0 * 1e4)), sg * (m1 - m0) / m0 * 1e4, dfund, gap_f))
w = lambda v, k: sum(x[1] * x[k] for x in v) / sum(x[1] for x in v) if v else float("nan")
for g in G:
    v = [x for x in rows if x[0] == g]; D = sum(x[1] for x in v)
    print(f"== {g}: {len(v)} fills, kept {w(v, 2):+.2f}, move after {w(v, 3):+.2f}")
    for lab, f in (("fund moved AGAINST us ≥ 0.5 bp", lambda x: x[4] <= -0.5), ("fund flat (±0.5)", lambda x: -0.5 < x[4] < 0.5), ("fund moved WITH us ≥ 0.5", lambda x: x[4] >= 0.5)):
        u = [x for x in v if f(x)]
        if u: print(f"   Δfund {N}s {lab:32s} {sum(x[1] for x in u) / D:4.0%} of $ | kept {w(u, 2):+5.2f} | move after {w(u, 3):+5.2f} (n {len(u)})")
    for lab, f in (("fund vs mid against us ≥ 1 bp", lambda x: x[5] <= -1), ("fund ≈ mid (±1)", lambda x: -1 < x[5] < 1), ("fund vs mid with us ≥ 1", lambda x: x[5] >= 1)):
        u = [x for x in v if f(x)]
        if u: print(f"   lean {lab:34s} {sum(x[1] for x in u) / D:4.0%} of $ | kept {w(u, 2):+5.2f} | move after {w(u, 3):+5.2f} (n {len(u)})")
