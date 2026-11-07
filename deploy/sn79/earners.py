"""§1274: what the top EARNERS do (not the top skill UIDs): per UID, maker vs taker $, books, $ per book per sim h, two-sided making share, and the
time profile since their first fill on this tape. Current sim only (ts < 60000 s).   python earners.py <tape> <uid,...>"""
import json, sys, collections, statistics as st
tape, U = sys.argv[1], [int(u) for u in sys.argv[2].split(",")]; S = set(U)
mk = collections.defaultdict(float); tk = collections.defaultdict(float); bk = collections.defaultdict(set); side = collections.defaultdict(lambda: [0.0, 0.0])
first = {}; last = {}; hr = collections.defaultdict(lambda: collections.defaultdict(float)); seen = set(); cp = collections.defaultdict(collections.Counter); tkbook = collections.defaultdict(lambda: collections.defaultdict(float))
for l in open(tape, "rb"):
    if b'"Ta": ' not in l: continue
    r = json.loads(l); t = r["ts"] / 1e9
    if t >= 60000: continue
    k = (r["book"], r.get("id"))
    if k in seen: continue
    seen.add(k); v = r["q"] * r["p"]
    for role, u in (("M", r.get("Ma")), ("T", r.get("Ta"))):
        if u not in S: continue
        first.setdefault(u, t); last[u] = t; bk[u].add(r["book"]); hr[u][int(t // 3600)] += v
        if role == "M":
            mk[u] += v; side[(u, r["book"])][r["s"]] += v; cp[u][r.get("Ta")] += v
        else:
            tk[u] += v; tkbook[u][r["book"]] += v
print(f"{'uid':>4} {'maker $':>11} {'taker $':>11} {'books':>5} {'2-sided':>7} {'$/book/simh':>11} {'span h':>6} | $ per sim hour since first fill (h0, h1, ...)")
for u in U:
    if u not in first: print(f"{u:4d}  no fills"); continue
    span = max(last[u] - first[u], 1) / 3600; books = [b for (uu, b) in side if uu == u]
    two = [b for b in books if min(side[(u, b)]) > 0.25 * max(side[(u, b)])]
    h0 = int(first[u] // 3600); prof = [hr[u].get(h0 + i, 0) for i in range(min(8, int(span) + 1))]
    print(f"{u:4d} {mk[u]:11,.0f} {tk[u]:11,.0f} {len(bk[u]):5d} {len(two) / max(len(books), 1):7.0%} {(mk[u] + tk[u]) / max(len(bk[u]), 1) / span:11,.0f} {span:6.1f} | " + " ".join(f"{p / 1e3:,.0f}k" for p in prof))
