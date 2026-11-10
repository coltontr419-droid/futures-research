"""§1322b: $300 adverse move after our fills — (1) PAIRED: fleet vs us on the same book in the same sim minute (removes book/time selection);
(2) pre-fill trend: mid change over the 10 s / 60 s before the fill, signed toward the order (− = the price was falling into our bid), and the
post-fill move per trend bucket; (3) who moved first: our order age vs the last own-side best change.  python3 why300.py <tape> <T0> <T1> fleet=.. us=.."""
import json, sys, collections, statistics as stt
LO, HI = (63, 102) if "--calm" in sys.argv else (0, 63); sys.argv = [a for a in sys.argv if a != "--calm"]
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[4:6]}; who = {u: g for g, us in G.items() for u in us}
SN = collections.defaultdict(dict); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < T0 - 120 or t > T1 + 30: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    if not (LO <= b < HI): continue
    if b'"Mi"' in l:
        r = json.loads(l)
        if r["Ma"] in who and r["Ma"] != r["Ta"] and T0 <= t < T1: F.append((t, b, r["p"], r["q"], r["s"], who[r["Ma"]]))
    elif b'"bids"' in l:
        r = json.loads(l)
        if r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"] + r["ask"]) / 2
rows = []
for t, b, p, q, s, g in F:
    m0 = SN[b].get(int(t) - 1); m20 = SN[b].get(int(t) + 20); m10b = SN[b].get(int(t) - 11); m60b = SN[b].get(int(t) - 61)
    if None in (m0, m20, m10b, m60b): continue
    sg = 1 if s == 1 else -1
    rows.append(dict(g=g, b=b, mn=int(t // 60), usd=p * q, kept=sg * (m20 - p) / m0 * 1e4, move=sg * (m20 - m0) / m0 * 1e4,
                     tr10=sg * (m0 - m10b) / m0 * 1e4, tr60=sg * (m0 - m60b) / m0 * 1e4))
w = lambda v, k: sum(x[k] * x["usd"] for x in v) / sum(x["usd"] for x in v) if v else float("nan")
cell = collections.defaultdict(lambda: {"fleet": [], "us": []})
for x in rows: cell[(x["b"], x["mn"])][x["g"]].append(x)
both = [(c["fleet"], c["us"]) for c in cell.values() if c["fleet"] and c["us"]]
df = [w(f, "kept") - w(u, "kept") for f, u in both]; dm = [w(f, "move") - w(u, "move") for f, u in both]
print(f"(1) PAIRED same book + same sim minute: {len(both)} cells | fleet − us kept {stt.mean(df):+.2f} bp (median {stt.median(df):+.2f}), of which post-fill move {stt.mean(dm):+.2f} "
      f"| fleet better in {sum(1 for d in df if d > 0) / len(df):.0%} of cells")
for g in G:
    v = [x for x in rows if x["g"] == g]
    print(f"\n(2) {g}: {len(v)} fills, kept {w(v, 'kept'):+.2f}, move after {w(v, 'move'):+.2f}")
    for name, k in (("10 s before", "tr10"), ("60 s before", "tr60")):
        for lo, hi, lab in ((-1e9, -1.0, "price ran INTO the order (> 1 bp)"), (-1.0, 1.0, "flat (±1 bp)"), (1.0, 1e9, "price ran AWAY then back (> 1 bp)")):
            u = [x for x in v if lo <= x[k] < hi]
            if u: print(f"    {name:11s} {lab:36s} {sum(x['usd'] for x in u) / sum(x['usd'] for x in v):4.0%} of $ | kept {w(u, 'kept'):+5.2f} | move after {w(u, 'move'):+5.2f} (n {len(u)})")
