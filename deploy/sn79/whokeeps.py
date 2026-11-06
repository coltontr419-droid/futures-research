"""Which maker fills keep the spread? (decisions.md §1257) Print-centred capture per fill, as the validator measures it: centred mid = mean price of the 15 prints either side (excluding the fill),
captured = side × (centred mid − price); realized = same against the mid 20 s later, capped to ±|captured|. Slices by depth (distance from the snapshot mid in spreads), book group, taker type, sweep size.
    python whokeeps.py <tape> <since sim min> <uid,uid,...>"""
import bisect, json, sys, collections
tape, since, uids = sys.argv[1], float(sys.argv[2]) * 6e10, {int(u) for u in sys.argv[3].split(",")}
P = collections.defaultdict(list); snaps = collections.defaultdict(lambda: ([], [], [])); seen = set()
for l in open(tape):
    if l.startswith('{"ts"') and '"bid"' in l[:60]:
        i = l.find('"bids"'); r = json.loads(l[:i].rstrip(', ') + "}")
        if r["ts"] >= since - 6e10 and r.get("bid") and r.get("ask"):
            s = snaps[r["book"]]; s[0].append(r["ts"]); s[1].append(r["bid"]); s[2].append(r["ask"])
    elif '"Ma": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"))
        if r["ts"] >= since - 6e10 and k not in seen:
            seen.add(k); P[r["book"]].append((r["ts"], r["p"], r["q"], r["s"], r.get("Ma"), r.get("Ta")))
G = lambda b: "$300" if b < 63 else ("$30" if b < 102 else "4-dec")
R = []
for b, pr in P.items():
    pr.sort(); S = snaps[b]; px = [x[1] for x in pr]; t0 = [x[0] for x in pr]
    for i, (ts, p, q, s, ma, ta) in enumerate(pr):
        if ma not in uids or ts < since or i < 15 or i + 15 >= len(pr): continue
        cm = (sum(px[i - 15:i]) + sum(px[i + 1:i + 16])) / 30; sg = 1 if s == 1 else -1; c = sg * (cm - p) / p * 1e4
        j = bisect.bisect_right(S[0], ts) - 1; k = bisect.bisect_left(S[0], ts + 20e9)
        if j < 0 or k >= len(S[0]): continue
        mid = (S[1][j] + S[2][j]) / 2; sp = S[2][j] - S[1][j]; mf = (S[1][k] + S[2][k]) / 2
        r_ = max(-abs(c), min(abs(c), sg * (mf - p) / p * 1e4)); d = sg * (mid - p) / sp if sp > 0 else 0
        same = sum(q2 for t2, _, q2, s2, _, _ in pr[max(0, i - 8):i + 9] if abs(t2 - ts) < 2e6 and s2 == s) * p
        R.append(dict(u=ma, b=G(b), d=d, c=c, r=r_, n=p * q, bg=ta is None or ta < 0, sweep=same, sm=p * q))
def row(name, X, tot):
    n = sum(x["n"] for x in X)
    if not X or not n: return
    c = sum(x["c"] * x["n"] for x in X) / n; r = sum(x["r"] * x["n"] for x in X) / n
    print(f"   {name:24} ${n / 1e6:6.2f}M {n / tot:4.0%} fills {len(X):6d} | captured {c:+6.2f} bp | realized {r:+6.2f} | quality {r / c if c > 0 else 0:+.2f} | contribution to bp {c * n / tot:+5.2f}")
for grp, us in (("top template makers", uids - {58}), ("x3 old", {58})):
    X = [x for x in R if x["u"] in us]; tot = sum(x["n"] for x in X)
    if not X: continue
    print(f"== {grp}"); row("all", X, tot)
    for nm, lo, hi in (("inside the touch", -9, .45), ("at the touch", .45, .55), ("just behind (.55-1.2)", .55, 1.2), ("deep (1.2-2.5)", 1.2, 2.5), ("very deep (>2.5)", 2.5, 99)):
        row(nm, [x for x in X if lo <= x["d"] < hi], tot)
    for b in ("$300", "$30", "4-dec"): row("book " + b, [x for x in X if x["b"] == b], tot)
    row("taker: background", [x for x in X if x["bg"]], tot); row("taker: miner", [x for x in X if not x["bg"]], tot)
    for nm, lo, hi in (("sweep < $2k", 0, 2e3), ("sweep $2-5k", 2e3, 5e3), ("sweep $5-15k", 5e3, 15e3), ("sweep > $15k", 15e3, 1e12)):
        row(nm, [x for x in X if lo <= x["sweep"] < hi], tot)
    for b in ("$30", "4-dec"):
        Y = [x for x in X if x["b"] == b]; t = sum(x["n"] for x in Y)
        for nm, lo, hi in (("inside", -9, .45), ("touch", .45, .55), ("behind", .55, 1.2), ("deep", 1.2, 99)):
            row(f"{b} {nm}", [x for x in Y if lo <= x["d"] < hi], t)
