"""§1366: calm-book comparison x3 vs the fleet (per UID): fills and $ per wall hour, edge / move / kept (capped ±20 bp), two-sidedness per book.
python3 calmcmp.py <tape> <T0> <T1> <sim s per wall h> fleet=.. us=.."""
import json, sys, collections
tape, T0, T1, RATE = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[5:7]}; who = {u: g for g, us in G.items() for u in us}
SN = collections.defaultdict(dict); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < T0 - 5 or t > T1 + 30: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    if not (63 <= b < 102): continue
    if b'"Mi"' in l:
        r = json.loads(l)
        if r["Ma"] in who and r["Ma"] != r["Ta"] and T0 <= t < T1: F.append((t, b, r["p"], r["q"], r["s"], r["Ma"]))
    elif b'"bids"' in l:
        r = json.loads(l)
        if r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"] + r["ask"]) / 2
wall_h = (T1 - T0) / RATE
for g in G:
    n = len(G[g]); rows = []; side = collections.defaultdict(lambda: [0.0, 0.0])
    for t, b, p, q, s, u in F:
        if who[u] != g: continue
        m0 = SN[b].get(int(t) - 1); m1 = SN[b].get(int(t) + 20)
        if m0 is None or m1 is None: continue
        sg = 1 if s == 1 else -1
        rows.append((p * q, sg * (m0 - p) / m0 * 1e4, sg * (m1 - m0) / m0 * 1e4, max(-20, min(20, sg * (m1 - p) / m0 * 1e4))))
        side[(u, b)][0 if s == 1 else 1] += p * q
    D = sum(r[0] for r in rows); w = lambda k: sum(r[0] * r[k] for r in rows) / D
    two = sum(2 * min(v) for v in side.values()); tot = sum(sum(v) for v in side.values())
    print(f"{g:6s} ({n} UIDs): per UID per wall h {len(rows) / n / wall_h:5.1f} fills, ${D / n / wall_h:8,.0f} | edge {w(1):+.2f} + move {w(2):+.2f} → kept {w(3):+.2f} bp (capped)"
          f" | two-sided share {two / tot:.0%} | books per UID {len(side) / n:.0f}")
