"""§1392: how do the long-lived fleet makers (5F1F2JMu, ≥ 7 d, making-only) share the same books? Last ≈ 3 sim h before x1 started (sim 75,250–78,250).
Per UID: books traded, fills, $/book/sim h, median fill $, depth profile (ticks behind the pre-trade touch); concurrency: share of a UID's fills that land
within ±2 sim s of another fleet UID's fill on the same book+side, and whether those were at the SAME price (stacked queue) or different prices."""
import json, sys, collections, bisect
F = [7, 40, 52, 55, 87, 102, 110, 132, 166, 183]; X = 64; U = set(F + [X])
S0, S1 = 75250, 78250
snap, tick = {}, {}
fills = []   # (t, book, side, price, uid, $, depth)
for path in sys.argv[1:]:
    for l in open(path):
        i = l.find('"ts": ')
        if i < 0: continue
        t = int(l[i + 6:l.index(",", i)]) / 1e9
        if t < S0 - 60 or t >= S1: continue
        if '"bids"' in l:
            r = json.loads(l); bb = r.get("bids") or []; aa = r.get("asks") or []
            if bb and aa:
                snap[r["book"]] = (bb[0][0], aa[0][0])
                px = [x[0] for x in bb[:5]] + [x[0] for x in aa[:5]]
                d = [round(abs(a - b), 8) for a, b in zip(px, px[1:]) if abs(a - b) > 1e-9]
                if d: tick[r["book"]] = min(d + ([tick[r["book"]]] if r["book"] in tick else []))
            continue
        if '"Ma"' not in l or t < S0: continue
        r = json.loads(l); u = r["Ma"]
        if u not in U: continue
        b = r["book"]; s = snap.get(b); tk = tick.get(b); dep = None
        if s and tk:
            bid = r["s"] == 1; ref = s[0] if bid else s[1]; dep = round(((ref - r["p"]) if bid else (r["p"] - ref)) / tk)
        fills.append((t, b, r["s"], r["p"], u, r["p"] * r["q"], dep))
hrs = (S1 - S0) / 3600
by = collections.defaultdict(list)
for f in fills: by[(f[1], f[2])].append(f)
for k in by: by[k].sort()
q = lambda a, p: sorted(a)[int(p * (len(a) - 1))] if a else float("nan")
BIN = lambda d: "in" if d < 0 else ("0" if d == 0 else ("1" if d == 1 else ("2-4" if d <= 4 else ("5-9" if d <= 9 else "10+"))))
print(f"window sim {S0}-{S1} ({hrs:.2f} sim h)")
print("UID  | books | fills | $/book/sim h | fill $ med | depth in/0/1/2-4/5-9/10+ | near another fleet fill ±2 s: share, of which same price")
for u in F + [X]:
    mine = [f for f in fills if f[4] == u]
    if not mine: print(u, "no fills"); continue
    books = {f[1] for f in mine}; dol = sum(f[5] for f in mine)
    c = collections.Counter(BIN(f[6]) for f in mine if f[6] is not None); n = sum(c.values()) or 1
    near = same = 0
    for f in mine:
        L = by[(f[1], f[2])]; T = [x[0] for x in L]
        lo, hi = bisect.bisect_left(T, f[0] - 2), bisect.bisect_right(T, f[0] + 2)
        others = [x for x in L[lo:hi] if x[4] != u and x[4] in F]
        if others:
            near += 1; same += any(abs(x[3] - f[3]) < 1e-9 for x in others)
    print(f"{u:4d} | {len(books):5d} | {len(mine):5d} | ${dol / len(books) / hrs / 1e3:9.1f}k | {q([f[5] for f in mine], .5):8,.0f} | "
          + "/".join(f"{100 * c[x] / n:.0f}" for x in ("in", "0", "1", "2-4", "5-9", "10+")) + f" | {100 * near / len(mine):3.0f}%, same price {100 * same / max(near, 1):3.0f}%")
# per book: how many fleet UIDs active per sim minute
act = collections.defaultdict(set)
for f in fills:
    if f[4] in F: act[(f[1], int(f[0] // 60))].add(f[4])
v = [len(s) for s in act.values()]
print(f"fleet UIDs filling the same book in the same sim minute: median {q(v, .5)}, p90 {q(v, .9)}, max {max(v)} (over {len(v)} book-minutes with a fleet fill)")
tot = collections.defaultdict(float)
for f in fills: tot[f[1]] += f[5] if f[4] in F else 0
print(f"fleet (10 UIDs) $ per book per sim h: median ${q(list(tot.values()), .5) / hrs / 1e3:.0f}k (x3 alone ≈ $18k)")
