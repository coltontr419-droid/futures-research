"""§1337: $300 book spread (ticks, 1 s before the fill) for the fleet's vs x3's fills, by depth at the fill (inside / touch / behind) — picks T for mk_vol_touch_min."""
import json, sys, collections
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[4:]}
who = {u: g for g, us in G.items() for u in us}; SN = collections.defaultdict(dict); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < T0 - 5 or t > T1: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    if b >= 63: continue
    if b'"Mi"' in l:
        r = json.loads(l)
        if r["Ma"] in who and r["Ma"] != r["Ta"]: F.append((t, b, r["p"], r["q"], r["s"], who[r["Ma"]]))
    elif b'"bids"' in l:
        r = json.loads(l)
        if r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"], r["ask"])
tab = collections.defaultdict(float); tot = collections.defaultdict(float)
for t, b, p, q, s, g in F:
    a = SN[b].get(int(t) - 1)
    if not a: continue
    buy = s == 1; d = round(((a[0] - p) if buy else (p - a[1])) / 0.01); sp = min(round((a[1] - a[0]) / 0.01), 9)
    dk = "inside" if d < 0 else "touch" if d == 0 else "behind"; tab[(g, dk, sp)] += p * q; tot[g] += p * q
for g in G:
    print(f"== {g}: share of $300 $ by spread (ticks) — inside / touch / behind")
    for sp in range(1, 10):
        print(f"   spread {sp}{'+' if sp == 9 else ' '}: " + " | ".join(f"{dk} {tab[(g, dk, sp)] / tot[g]:5.1%}" for dk in ("inside", "touch", "behind")))
