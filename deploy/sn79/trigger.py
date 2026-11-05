"""What precedes the top skill takers' ENTRIES? (decisions.md §1232) Position-opening trades only (per-uid running inventory per book).
For each candidate trigger: share of entries whose direction agrees with its sign, and the forward mid move (bp, our direction) when it
agrees vs disagrees. Agreement far from 50% + a forward-move gap = the trigger they use."""
import json, sys
from collections import defaultdict
import numpy as np
TOP = {114, 238, 120, 163, 42, 214, 191, 89, 113, 124, 243, 70, 8, 103, 159, 161, 170, 126, 150, 100}
MB = int(sys.argv[1]); mid = defaultdict(dict); fund = defaultdict(dict); of = defaultdict(dict); trades = defaultdict(list); tops = []
with open("/opt/mvtrx/live_tape_x1_size6.jsonl", "rb") as fh:
    fh.seek(0, 2); n = fh.tell(); fh.seek(max(0, n - MB * 1_000_000)); fh.readline()
    for l in fh:
        r = json.loads(l); b = r.get("book"); t = r["ts"] // 1_000_000_000
        if "bid" in r and r.get("bid") and r.get("ask"):
            mid[b][t] = (r["bid"] + r["ask"]) / 2
            if r.get("fund"): fund[b][t] = r["fund"]
        elif "of" in r:
            o = r["of"]; of[b][t] = (o.get("nb", 0) - o.get("na", 0)) - (o.get("cb", 0) - o.get("ca", 0))   # net new bids minus net cancels
        elif "p" in r:
            ta = r.get("Ta"); trades[b].append((t, r["p"], r["q"], ta))
            if ta in TOP: tops.append((ta, b, t, r["p"], r["q"]))
def at(d, t, w=6):
    for k in range(t, t - w, -1):
        if k in d: return d[k]
# taker direction of every trade: buy if it printed at/above the prior mid
flow = defaultdict(lambda: defaultdict(float)); big = {}
for b, xs in trades.items():
    qs = [q for _, _, q, _ in xs]; big[b] = np.percentile(qs, 95) if qs else 1e9
    for t, p, q, ta in xs:
        m = at(mid[b], t - 1)
        if m is not None and ta not in TOP: flow[b][t] += (1 if p >= m else -1) * q
ents = []; inv = defaultdict(float)
for u, b, t, p, q in sorted(tops, key=lambda x: x[2]):
    m0 = at(mid[b], t - 1)
    if m0 is None: continue
    d = 1 if p >= m0 else -1; key = (u, b)
    entry = abs(inv[key] + d * q) > abs(inv[key]) + 1e-9; inv[key] += d * q
    if not entry: continue
    m600 = at(mid[b], t + 600); m60 = at(mid[b], t + 60)
    if m600 is None or m60 is None: continue
    f = {}
    for w in (1, 10, 60):
        a, z = at(fund[b], t - 1), at(fund[b], t - 1 - w)
        f["dfund_%ds" % w] = (a - z) if a is not None and z is not None else 0.0
    for w in (1, 5):
        z = at(mid[b], t - 1 - w); f["dmid_%ds" % w] = (m0 - z) if z is not None else 0.0
    fa, fz, mz = at(fund[b], t - 1), at(fund[b], t - 11), at(mid[b], t - 11)
    f["gap_now"] = (fa - m0) if fa is not None else 0.0
    f["gap_change_10s"] = ((fa - m0) - (fz - mz)) if None not in (fa, fz, mz) else 0.0
    f["other_flow_10s"] = sum(flow[b].get(k, 0.0) for k in range(t - 10, t))
    f["book_flow_10s"] = sum(of[b].get(k, 0.0) for k in range(t - 10, t))
    bt = [(k, p2, q2) for k, p2, q2, ta in trades[b] if t - 5 <= k < t and q2 >= big[b] and ta not in TOP]
    f["big_trade_5s"] = sum((1 if p2 >= (at(mid[b], k - 1) or p2) else -1) for k, p2, _ in bt)
    ents.append((d, d * (m60 - m0) / m0 * 1e4, d * (m600 - m0) / m0 * 1e4, f))
print("top-taker ENTRIES:", len(ents), "| forward our way: 60 s %+.2f bp, 600 s %+.2f bp, hit(600) %.0f%%" % (
    np.mean([e[1] for e in ents]), np.mean([e[2] for e in ents]), np.mean([e[2] > 0 for e in ents]) * 100))
print("%-16s %7s %8s | fwd600 when agree / disagree (bp)   n agree/disagree" % ("trigger", "nonzero", "agree%"))
for k in ents[0][3]:
    nz = [(d, f600, f[k]) for d, _, f600, f in ents if abs(f[k]) > 1e-12]
    if not nz: print("%-16s %7d" % (k, 0)); continue
    ag = [x for x in nz if np.sign(x[2]) == x[0]]; dis = [x for x in nz if np.sign(x[2]) != x[0]]
    print("%-16s %7d %7.0f%% | %+6.2f / %+6.2f          %d / %d" % (k, len(nz), len(ag) / len(nz) * 100,
          np.mean([x[1] for x in ag]) if ag else 0, np.mean([x[1] for x in dis]) if dis else 0, len(ag), len(dis)))
