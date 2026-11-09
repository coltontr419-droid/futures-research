"""§1343: x3's $300 fills by its queue position (size AHEAD of its order at that price, from its own queue records just before the fill) — does being at the
front matter, and how often are we at the back?  python3 queuepos.py <tape> <T0> <T1> <uid>"""
import json, sys, collections, bisect
tape, T0, T1, UID = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
SN = collections.defaultdict(dict); Q = collections.defaultdict(list); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < T0 - 60 or t > T1 + 30: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    if b >= 63: continue
    r = json.loads(l)
    if "queue" in r:
        for q in r["queue"]: Q[q[4]].append((t, q[2], q[3]))          # order id → (time, size ahead, own size)
    elif "Mi" in r:
        if r["Ma"] == UID and r["Ta"] != UID and T0 <= t < T1: F.append((t, b, r["p"], r["q"], r["s"], r["Mi"]))
    elif "bids" in r and r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"] + r["ask"]) / 2
rows = []
for t, b, p, q, s, mi in F:
    h = [x for x in Q.get(mi, []) if x[0] <= t]
    m0 = SN[b].get(int(t) - 1); m1 = SN[b].get(int(t) + 20)
    if not h or m0 is None or m1 is None: continue
    ahead = h[-1][1] * p
    rows.append((ahead, p * q, (1 if s == 1 else -1) * (m1 - p) / m0 * 1e4))
D = sum(x[1] for x in rows)
print(f"{len(rows)} of {len(F)} $300 fills have a queue record (records are sparse)")
for lo, hi, lab in ((-1, 1, "front (nothing ahead)"), (1, 5000, "< $5k ahead"), (5000, 20000, "$5-20k ahead"), (20000, 1e12, "$20k+ ahead")):
    v = [x for x in rows if lo <= x[0] < hi]
    if v: print(f"  {lab:22s} {sum(x[1] for x in v) / D:4.0%} of $ | kept {sum(x[2] * x[1] for x in v) / sum(x[1] for x in v):+5.2f} bp (n {len(v)})")
