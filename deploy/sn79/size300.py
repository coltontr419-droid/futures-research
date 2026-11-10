"""§1340: $300 fills by the ORDER's size (filled $ per order id, ≈ the order size floor) and by depth behind the touch at the fill, fleet vs ours — does size or depth
explain the remaining $300 gap?  python3 size300.py <tape> <T0> <T1> fleet=.. us=.."""
import json, sys, collections
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[4:]}
who = {u: g for g, us in G.items() for u in us}; SN = collections.defaultdict(dict); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < T0 - 5 or t > T1 + 30: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    if b >= 63: continue
    if b'"Mi"' in l:
        r = json.loads(l)
        if r["Ma"] in who and r["Ma"] != r["Ta"] and T0 <= t < T1: F.append((t, b, r["p"], r["q"], r["s"], r["Ma"], r["Mi"]))
    elif b'"bids"' in l:
        r = json.loads(l)
        if r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"], r["ask"])
per_o = collections.defaultdict(float)
for t, b, p, q, s, u, mi in F: per_o[(u, b, mi)] += p * q
rows = []
for t, b, p, q, s, u, mi in F:
    a = SN[b].get(int(t) - 1); z = SN[b].get(int(t) + 20)
    if not a or not z: continue
    buy = s == 1; sg = 1 if buy else -1; mid = (a[0] + a[1]) / 2; d = round(((a[0] - p) if buy else (p - a[1])) / 0.01)
    o = per_o[(u, b, mi)]
    rows.append(dict(g=who[u], usd=p * q, kept=sg * ((z[0] + z[1]) / 2 - p) / mid * 1e4,
                     size="order < $2.5k" if o < 2500 else "order $2.5-4.5k" if o < 4500 else "order $4.5k+",
                     depth="inside" if d < 0 else "touch" if d == 0 else "1-4 behind" if d < 5 else "5+ behind"))
w = lambda v: sum(x["kept"] * x["usd"] for x in v) / sum(x["usd"] for x in v) if v else float("nan")
for dim in ("size", "depth"):
    print(f"-- by {dim}")
    for k in sorted({x[dim] for x in rows}):
        line = []
        for g in G:
            v = [x for x in rows if x["g"] == g and x[dim] == k]; D = sum(x["usd"] for x in rows if x["g"] == g)
            line.append(f"{g} {sum(x['usd'] for x in v) / D:4.0%} kept {w(v):+5.2f} (n {len(v)})")
        print(f"   {k:16s} " + " | ".join(line))
print("-- depth x size (us):")
for dk in ("touch", "1-4 behind", "5+ behind"):
    for sk in ("order < $2.5k", "order $2.5-4.5k"):
        for g in G:
            v = [x for x in rows if x["g"] == g and x["depth"] == dk and x["size"] == sk]
            if len(v) >= 10: print(f"   {g:6s} {dk:11s} {sk:16s} kept {w(v):+5.2f} (n {len(v)})")
