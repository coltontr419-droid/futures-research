"""Why do top makers earn on $300 books and x3 not? (decisions.md §1262) Same books (odd ids < 63), same window, x3 vs template makers: depth, spread at the fill, capture, the mid move after the fill, taker type, side balance per book.
    python m300.py <tape> <since sim min>"""
import bisect, json, sys, collections, statistics as st
tape, since = sys.argv[1], float(sys.argv[2]) * 6e10
GR = {"x3": {201}, "top": {144, 252, 7, 31}}; all_ = GR["x3"] | GR["top"]
P = collections.defaultdict(list); snaps = collections.defaultdict(lambda: ([], [], [])); seen = set()
for l in open(tape):
    if l.startswith('{"ts"') and '"bid"' in l[:60]:
        i = l.find('"bids"'); r = json.loads(l[:i].rstrip(', ') + "}")
        if r["ts"] >= since - 6e10 and r.get("bid") and r.get("ask") and r["book"] < 63 and r["book"] % 2:
            s = snaps[r["book"]]; s[0].append(r["ts"]); s[1].append(r["bid"]); s[2].append(r["ask"])
    elif '"Ma": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"))
        if r["ts"] >= since - 6e10 and k not in seen and r["book"] < 63 and r["book"] % 2:
            seen.add(k); P[r["book"]].append((r["ts"], r["p"], r["q"], r["s"], r.get("Ma"), r.get("Ta")))
R = collections.defaultdict(list); side = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0]))
for b, pr in P.items():
    pr.sort(); S = snaps[b]; px = [x[1] for x in pr]
    for i, (ts, p, q, s, ma, ta) in enumerate(pr):
        if ma not in all_ or ts < since or i < 15 or i + 15 >= len(pr): continue
        j = bisect.bisect_right(S[0], ts) - 1; k5 = bisect.bisect_left(S[0], ts + 5e9); k20 = bisect.bisect_left(S[0], ts + 20e9); k60 = bisect.bisect_left(S[0], ts + 60e9)
        if j < 0 or k60 >= len(S[0]): continue
        sg = 1 if s == 1 else -1; mid = (S[1][j] + S[2][j]) / 2; sp = S[2][j] - S[1][j]; bp = lambda v: sg * (v - p) / p * 1e4
        mm = lambda k: (S[1][k] + S[2][k]) / 2; cm = (sum(px[i - 15:i]) + sum(px[i + 1:i + 16])) / 30
        g = "x3" if ma == 201 else "top"; n = p * q; side[g][(ma, b)][0 if s == 1 else 1] += n
        R[g].append(dict(d=sg * (mid - p) / sp if sp else 0, off=sg * (mid - p) / mid * 1e4, sp=sp / mid * 1e4, c=bp(cm), m5=bp(mm(k5)), m20=bp(mm(k20)), m60=bp(mm(k60)), n=n, bg=ta is None or ta < 0))
def w(X, k):
    t = sum(x["n"] for x in X); return sum(x[k] * x["n"] for x in X) / t if t else 0
for g, X in R.items():
    t = sum(x["n"] for x in X); print(f"== {g}: fills {len(X)} ${t / 1e6:.2f}M median fill ${st.median(x['n'] for x in X):.0f} | spread at fill median {st.median(x['sp'] for x in X):.2f} bp | fill vs mid {w(X, 'off'):+.2f} bp | captured {w(X, 'c'):+.2f} | mid vs fill after 5 / 20 / 60 s {w(X, 'm5'):+.2f} {w(X, 'm20'):+.2f} {w(X, 'm60'):+.2f}")
    for nm, lo, hi in (("inside", -9, .45), ("touch", .45, .55), ("behind", .55, 1.2), ("deep", 1.2, 2.5), ("very deep", 2.5, 99)):
        Y = [x for x in X if lo <= x["d"] < hi]
        if Y: print(f"   {nm:9} {sum(x['n'] for x in Y) / t:4.0%} ${sum(x['n'] for x in Y) / 1e6:5.2f}M | fill vs mid {w(Y, 'off'):+6.2f} | captured {w(Y, 'c'):+6.2f} | after 20 s {w(Y, 'm20'):+6.2f}, 60 s {w(Y, 'm60'):+6.2f}")
    for nm, f in (("bg taker", True), ("miner taker", False)):
        Y = [x for x in X if x["bg"] == f]
        if Y: print(f"   {nm:11} {sum(x['n'] for x in Y) / t:4.0%} | captured {w(Y, 'c'):+6.2f} | after 20 s {w(Y, 'm20'):+6.2f}")
    v = list(side[g].values()); bal = [2 * min(a, b) / (a + b) for a, b in v if a + b > 0]; print(f"   two-sided balance per book median {st.median(bal):.2f} (1 = even), books with both sides {sum(min(a, b) > 0 for a, b in v)} of {len(v)}")
