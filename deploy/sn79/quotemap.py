"""Where do makers rest? (decisions.md §1252) Every maker fill on a tape since a sim minute, against the last book snapshot at or before it:
distance from the mid (bp, + = behind the mid, in the maker's favour), level vs the touch (at touch / inside it / deeper), and the same by
regime (volatile 0-62, calm 63-101, 4-dec 102-127) and price bucket.
    python quotemap.py <tape> <since sim min> <uid,uid,...>"""
import bisect, json, statistics as st, sys
from collections import defaultdict
tape, since, uids = sys.argv[1], float(sys.argv[2]) * 6e10, {int(u) for u in sys.argv[3].split(",")}
snaps = defaultdict(lambda: ([], [], [])); fills = []; seen = set()
for l in open(tape):
    if l.startswith('{"ts"') and '"bid"' in l:
        i = l.find('"bids"'); r = json.loads(l[:i].rstrip(', ') + "}")
        if r["ts"] >= since - 6e10 and r.get("bid") and r.get("ask"):
            s = snaps[r["book"]]; s[0].append(r["ts"]); s[1].append(r["bid"]); s[2].append(r["ask"])
    elif '"Ma": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"))
        if r.get("Ma") in uids and r["ts"] >= since and k not in seen:
            seen.add(k); fills.append((r["Ma"], r["book"], r["ts"], r["p"], r["q"], r["s"]))
reg = lambda b: "vol" if b < 63 else ("calm" if b < 102 else "4dec")
R = defaultdict(list)
for u, b, ts, p, q, s in fills:
    S = snaps.get(b)
    if not S: continue
    i = bisect.bisect_right(S[0], ts) - 1
    if i < 0: continue
    bid, ask = S[1][i], S[2][i]; mid = (bid + ask) / 2; sgn = 1 if s == 1 else -1      # s == 1: the maker's resting order was the buy
    dist = sgn * (mid - p) / mid * 1e4; touch = bid if s == 1 else ask; off = sgn * (touch - p) / mid * 1e4   # off > 0: behind the touch; < 0: inside
    R[u].append((reg(b), p, dist, off, (ask - bid) / mid * 1e4, p * q))
def line(name, X):
    if not X: return
    d = [x[2] for x in X]; o = [x[3] for x in X]; sp = [x[4] for x in X]; n = len(X); e = 1e-6
    w = sum(x[5] for x in X)
    print(f"  {name:10} fills {n:6d} ${w / 1e6:5.2f}M | dist from mid median {st.median(d):+6.2f} bp (mean {st.mean(d):+6.2f}) | spread {st.median(sp):5.2f} bp | "
          f"inside {sum(x < -e for x in o) / n:4.0%} at touch {sum(abs(x) <= e for x in o) / n:4.0%} deeper {sum(x > e for x in o) / n:4.0%} (deeper median {st.median([x for x in o if x > e] or [0]):5.2f} bp)")
for u in sorted(R, key=lambda u: (u != 58, -len(R[u]))):
    X = R[u]; print(f"uid {u}{' (x3)' if u == 58 else ''}: books {len({0})}"[:-9]); line("all", X)
    for g in ("vol", "calm", "4dec"): line(g, [x for x in X if x[0] == g])
    for lo, hi in ((0, 60), (60, 150), (150, 1e9)): line(f"${lo}-{hi if hi < 1e9 else '+'}", [x for x in X if lo <= x[1] < hi])
print("dist / spread at the fill, percentiles 25/50/75/90 (1.0 = one full spread from the mid; 0.5 = at the touch):")
for u in sorted(R, key=lambda u: (u != 58, -len(R[u]))):
    r = sorted(x[2] / x[4] for x in R[u] if x[4] > 0); n = len(r)
    print(f"  uid {u:4d}: " + " / ".join(f"{r[int(n * q)]:+.2f}" for q in (.25, .5, .75, .9)))
