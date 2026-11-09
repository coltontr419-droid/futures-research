"""§1351: what made the fleet's $300 kept spike (+4–7 bp per fill, ≈ 9:30–11:00 AM CT 11-09, sim ≈ 39,164–40,335) vs before (37,038–39,164)? Per book
concentration, depth behind the touch, the size of the move after the fill, and x3 on the same books.  python3 spike300.py <tape> fleet=.. us=.."""
import json, sys, collections
tape = sys.argv[1]; G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[2:4]}; who = {u: g for g, us in G.items() for u in us}
P = {"before": (37038, 39164), "spike": (39164, 40335)}; T0, T1 = 37038, 40335
SN = collections.defaultdict(dict); F = []
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
rows = []
for t, b, p, q, s, g in F:
    a = SN[b].get(int(t) - 1); z = SN[b].get(int(t) + 20)
    if not a or not z: continue
    buy = s == 1; sg = 1 if buy else -1; m0 = (a[0] + a[1]) / 2; m1 = (z[0] + z[1]) / 2
    per = "spike" if t >= 39164 else "before"
    rows.append(dict(g=g, per=per, b=b, usd=p * q, kept=sg * (m1 - p) / m0 * 1e4, edge=sg * (m0 - p) / m0 * 1e4, move=sg * (m1 - m0) / m0 * 1e4,
                     depth=round(((a[0] - p) if buy else (p - a[1])) / 0.01), absmove=abs(m1 - m0) / m0 * 1e4))
w = lambda v, k: sum(x[k] * x["usd"] for x in v) / sum(x["usd"] for x in v) if v else float("nan")
for g in G:
    for per in P:
        v = [x for x in rows if x["g"] == g and x["per"] == per]
        if not v: continue
        D = sum(x["usd"] for x in v)
        deep = [x for x in v if x["depth"] >= 5]
        print(f"{g:6s} {per:6s}: fills {len(v):5d} | kept {w(v, 'kept'):+.2f} = edge {w(v, 'edge'):+.2f} + move {w(v, 'move'):+.2f} | |move 20 s| {w(v, 'absmove'):.2f} bp | "
              f"5+ behind {sum(x['usd'] for x in deep) / D:.0%} of $ (kept {w(deep, 'kept'):+.2f})")
# per-book concentration of the fleet's spike profit
fb = collections.defaultdict(lambda: [0.0, 0.0]); tot = 0.0
for x in rows:
    if x["g"] == "fleet" and x["per"] == "spike":
        fb[x["b"]][0] += x["kept"] * x["usd"] / 1e4; fb[x["b"]][1] += x["usd"]; tot += x["kept"] * x["usd"] / 1e4
top = sorted(fb.items(), key=lambda kv: -kv[1][0])[:8]
print(f"\nfleet spike profit ${tot:,.0f} (kept bp × $) — top books: " + ", ".join(f"{b}: ${v[0]:,.0f} ({v[0] / tot:.0%}, kept {v[0] / v[1] * 1e4:+.1f} bp)" for b, v in top))
for b, _ in top[:4]:
    us = [x for x in rows if x["g"] == "us" and x["per"] == "spike" and x["b"] == b]
    print(f"   book {b}: x3 fills {len(us)}, kept {w(us, 'kept'):+.2f}" if us else f"   book {b}: x3 no fills")
