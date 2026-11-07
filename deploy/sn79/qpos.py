"""Does queue position explain x3's adverse selection? (decisions.md §1264) UID 58's fills joined to its last logged queue row (same book, side, price, within 30 sim s). queue row: [side, price, size ahead of us, level size, order id]. Outcome: mid move after the fill, net of the fill's distance from the mid.
    python qpos.py <tape> <uid>"""
import bisect, json, sys, collections, statistics as st
tape, U = sys.argv[1], int(sys.argv[2])
Q = collections.defaultdict(list); snaps = collections.defaultdict(lambda: ([], [], [])); F = []; seen = set()
for l in open(tape):
    if l.startswith('{"ts"') and '"queue"' in l[:50]:
        r = json.loads(l)
        for side, px, ahead, lvl, oid in r["queue"]: Q[(r["book"], side, px)].append((r["ts"], ahead, lvl))
    elif l.startswith('{"ts"') and '"bid"' in l[:60]:
        i = l.find('"bids"'); r = json.loads(l[:i].rstrip(', ') + "}")
        if r.get("bid") and r.get("ask"):
            s = snaps[r["book"]]; s[0].append(r["ts"]); s[1].append(r["bid"]); s[2].append(r["ask"])
    elif f'"Ma": {U},' in l:
        r = json.loads(l); k = (r["book"], r.get("id"))
        if k not in seen: seen.add(k); F.append(r)
R = []; miss = 0
for r in F:
    b, s, p, ts = r["book"], r["s"], r["p"], r["ts"]; q = Q.get((b, 0 if s == 1 else 1, p))
    if not q: miss += 1; continue
    i = bisect.bisect_right(q, (ts, 1e18, 1e18)) - 1
    if i < 0 or ts - q[i][0] > 30e9: miss += 1; continue
    S = snaps[b]; j = bisect.bisect_right(S[0], ts) - 1; k = bisect.bisect_left(S[0], ts + 20e9)
    if j < 0 or k >= len(S[0]): continue
    sg = 1 if s == 1 else -1; m0 = (S[1][j] + S[2][j]) / 2; m1 = (S[1][k] + S[2][k]) / 2; v = p * r["q"]
    R.append(dict(share=q[i][1] / q[i][2] if q[i][2] else 0, ahead=q[i][1] * p, net=sg * (m1 - m0) / m0 * 1e4, n=v, g="$30" if 63 <= b < 102 else ("4-dec" if b >= 102 else "$300"), lvl=q[i][2] * p))
print("fills", len(F), "joined", len(R), "unmatched", miss)
w = lambda X, k: sum(x[k] * x["n"] for x in X) / sum(x["n"] for x in X)
print("net mid move after the fill at 20 s ($-weighted, + = good), by share of the level ahead of us when last logged:")
for g in ("all", "$30", "4-dec", "$300"):
    for nm, lo, hi in (("front (0)", -1, 1e-9), ("0-25% ahead", 1e-9, .25), ("25-50%", .25, .5), ("50-75%", .5, .75), ("75-100%", .75, 9)):
        Y = [x for x in R if (g == "all" or x["g"] == g) and lo < x["share"] <= hi]
        if len(Y) >= 15: print(f"  {g:6} {nm:13} fills {len(Y):5d} ${sum(x['n'] for x in Y) / 1e3:7.0f}k | net {w(Y, 'net'):+6.2f} bp | median level ${st.median(x['lvl'] for x in Y):7.0f}")
