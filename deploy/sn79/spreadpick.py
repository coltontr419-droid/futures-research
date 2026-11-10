"""§1278: on the $300 books, does the long-lived fleet quote only when the spread is wide, or rest behind the touch? Spread distribution at their fills vs
the books' spread over time; share of fills at the touch vs deeper (fill price vs best price before the fill).  python spreadpick.py <tape> <uids> [since]"""
import json, sys, collections, bisect
tape, U = sys.argv[1], {int(u) for u in sys.argv[2].split(",")}; LO = float(sys.argv[3]) if len(sys.argv) > 3 else 0
B = collections.defaultdict(lambda: ([], [], [])); ALL = []; F = []; seen = set(); qq = {}
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < LO: continue
    if b'"bid": ' in l[:80]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r["book"] < 63 and r.get("bid") and r.get("ask"):
            a = B[r["book"]]; a[0].append(t); a[1].append(r["bid"]); a[2].append(r["ask"]); ALL.append((r["ask"] - r["bid"]) / ((r["ask"] + r["bid"]) / 2) * 1e4)
    elif b'"Ta": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"))
        if k in seen or r["book"] >= 63: continue
        seen.add(k)
        if r.get("Ma") in U: F.append((r["book"], t, r["s"], r["p"])); qq[(r["book"], t, r["p"])] = r["q"] * r["p"]
sp = []; touch = deeper = better = 0; D = collections.Counter(); DV = {}
for b, t, s, p in F:
    a = B[b]; i = bisect.bisect_left(a[0], t) - 1
    if i < 0: continue
    bid, ask = a[1][i], a[2][i]; m = (bid + ask) / 2; sp.append((ask - bid) / m * 1e4)
    best = ask if s == 0 else bid               # s == 0: resting SELL filled → compare with the ask; else the bid
    d = (p - best) if s == 0 else (best - p)    # > 0: filled beyond the touch (deeper, better for the maker)
    tick = 0.01; k = round(d / tick); D[k] += 1
    kb = "inside" if k < 0 else "touch" if k == 0 else "1-2 behind" if k <= 2 else "3-6 behind" if k <= 6 else "7+ behind"
    j = bisect.bisect_left(a[0], t + 120)
    if j < len(a[0]):
        m1 = (a[1][j] + a[2][j]) / 2; mk = -1 if s == 0 else 1          # s == 0: maker sold
        DV.setdefault(kb, []).append((qq.get((b, t, p), 0), mk * (m - p) / m * 1e4, mk * (m1 - m) / m * 1e4))
    if abs(d) < tick / 2: touch += 1
    elif d > 0: deeper += 1
    else: better += 1
q = lambda a, x: sorted(a)[int(x * (len(a) - 1))]
n = touch + deeper + better
print(f"fills {n}: at the touch {touch / n:.0%}, deeper than the touch {deeper / n:.0%} (fills that swept through), inside {better / n:.0%}")
print("depth vs the touch in ticks (+ = behind the touch, − = inside the spread):", sorted((k, round(v / n, 3)) for k, v in D.items() if v / n >= 0.01))
print(f"spread at their fills: p10 {q(sp, .1):.2f} p25 {q(sp, .25):.2f} median {q(sp, .5):.2f} p75 {q(sp, .75):.2f} bp")
print(f"the books' spread over time: p10 {q(ALL, .1):.2f} p25 {q(ALL, .25):.2f} median {q(ALL, .5):.2f} p75 {q(ALL, .75):.2f} bp")
for th in (1.0, 1.5, 2.0, 2.5):
    print(f"  share of time spread ≥ {th} bp: {sum(v >= th for v in ALL) / len(ALL):.0%} | share of their fills at spread ≥ {th}: {sum(v >= th for v in sp) / len(sp):.0%}")
import statistics as st
print("by depth: share of fills | share of $ | median fill $ | edge at fill | mid after 120 s | net per fill (bp)")
tot = sum(sum(x[0] for x in v) for v in DV.values())
for kb in ("inside", "touch", "1-2 behind", "3-6 behind", "7+ behind"):
    v = DV.get(kb, [])
    if v: print(f"  {kb:10} {len(v) / sum(len(x) for x in DV.values()):5.0%} | {sum(x[0] for x in v) / tot:5.0%} | ${st.median(x[0] for x in v):6,.0f} | {st.mean(x[1] for x in v):+6.2f} | {st.mean(x[2] for x in v):+6.2f} | {st.mean(x[1] + x[2] for x in v):+6.2f}")
