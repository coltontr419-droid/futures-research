"""How do the top skill UIDs build and unwind positions? (decisions.md §1272) Each UID's position per book, flat to flat. For every fill that ADDS to an open
position: was the price against the position (vs the previous add) or in its favour, by how many bp, how long after, how big vs the first clip. For every
fill that REDUCES: partial or full, and the mid vs the position's average. Outcome per position by add pattern.
    python legs.py <tape> <uid,uid,...> [min ts s] [max ts s]"""
import json, sys, collections, statistics as st, bisect
tape, uids = sys.argv[1], {int(u) for u in sys.argv[2].split(",")}
lo = float(sys.argv[3]) if len(sys.argv) > 3 else 0; hi = float(sys.argv[4]) if len(sys.argv) > 4 else 1e12
M = collections.defaultdict(lambda: ([], [])); F = collections.defaultdict(list); seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if not lo <= t <= hi: continue
    if b'"bid"' in l[:60]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r.get("bid") and r.get("ask"): m = M[r["book"]]; m[0].append(t); m[1].append((r["bid"] + r["ask"]) / 2)
    elif b'"Ta": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"))
        if r.get("Ta") in uids and k not in seen:
            seen.add(k); F[(r["Ta"], r["book"])].append((t, (1 if r["s"] == 0 else -1) * r["q"], r["p"]))
mid = lambda b, t: (lambda a: a[1][max(0, bisect.bisect_right(a[0], t) - 1)] if a[0] else None)(M[b])
A = collections.defaultdict(list); X = collections.defaultdict(list); P = collections.defaultdict(list)
for (u, b), fs in F.items():
    fs.sort(); inv = 0.0; pos = None
    for t, d, p in fs:
        m0 = mid(b, t) or p
        if pos is None or abs(inv) * p < 1:
            pos = dict(t0=t, sg=1 if d > 0 else -1, cost=abs(d) * m0, q=abs(d), last=m0, first=abs(d) * p, adds=[], lastt=t); inv = d; continue
        if (d > 0) == (pos["sg"] > 0):
            mv = pos["sg"] * (m0 - pos["last"]) / pos["last"] * 1e4
            A[u].append((mv, t - pos["lastt"], abs(d) * p / pos["first"])); pos["adds"].append(mv)
            pos["cost"] += abs(d) * m0; pos["q"] += abs(d); pos["last"] = m0; pos["lastt"] = t; inv += d
        else:
            avg = pos["cost"] / pos["q"]; pnl = pos["sg"] * (m0 - avg) / avg * 1e4; full = abs(inv + d) * p < 1
            X[u].append((pnl, full, t - pos["t0"])); inv += d
            if full or (inv > 0) != (pos["sg"] > 0):
                P[u].append((pnl, pos["adds"], t - pos["t0"])); pos = None; inv = 0.0 if full else inv
for u in sorted(uids):
    a = A[u]; x = X[u]; p = P[u]
    if not a or not p: print(f"{u}: too few"); continue
    adv = [v for v in a if v[0] < -0.5]; fav = [v for v in a if v[0] > 0.5]; flat = len(a) - len(adv) - len(fav)
    print(f"== uid {u}: positions closed {len(p)}, adds {len(a)} ({len(a) / max(len(p), 1):.1f} per position)")
    print(f"   adds AGAINST the position {len(adv) / len(a):.0%} (median {st.median([v[0] for v in adv] or [0]):+.1f} bp from last add, {st.median([v[1] for v in adv] or [0]):.0f} s later, size × first {st.median([v[2] for v in adv] or [0]):.2f}) | IN FAVOUR {len(fav) / len(a):.0%} (median {st.median([v[0] for v in fav] or [0]):+.1f} bp, {st.median([v[1] for v in fav] or [0]):.0f} s) | ~flat {flat / len(a):.0%}")
    print(f"   reductions: {len(x)}, full exits {sum(v[1] for v in x) / max(len(x), 1):.0%}, mid vs average at reduction median {st.median(v[0] for v in x):+.1f} bp, in profit {sum(v[0] > 0 for v in x) / max(len(x), 1):.0%}")
    for nm, f in (("no adds", lambda ad: not ad), ("mostly added against", lambda ad: ad and sum(v < 0 for v in ad) > len(ad) / 2), ("mostly added in favour", lambda ad: ad and sum(v > 0 for v in ad) > len(ad) / 2)):
        q = [v for v in p if f(v[1])]
        if q: print(f"   positions {nm:22} n {len(q):4d} | result at close (mid vs avg) mean {st.mean(max(-50, min(50, v[0])) for v in q):+.2f} bp, win {sum(v[0] > 0 for v in q) / len(q):.0%}, hold median {st.median(v[2] for v in q):.0f} s")
