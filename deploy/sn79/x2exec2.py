"""x2 live S5 execution (decisions.md §1230): for each of x2's taker fills, the mid path around it — how much of the 300 s move had already
reverted by our fill (signal lag), our fill vs mid (half spread paid), and the forward move over the 600 s hold, raw and per book."""
import json, sys
from collections import defaultdict
import numpy as np
MB = int(sys.argv[1]); mid = defaultdict(dict); fills = []
with open("/opt/mvtrx/live_tape_x2c.jsonl", "rb") as fh:
    fh.seek(0, 2); n = fh.tell(); fh.seek(max(0, n - MB * 1_000_000)); fh.readline()
    for l in fh:
        if b'"bid"' in l:
            r = json.loads(l)
            if r.get("bid") and r.get("ask"): mid[r["book"]][r["ts"] // 1_000_000_000] = (r["bid"] + r["ask"]) / 2
        elif b'"Ta": 169' in l:
            r = json.loads(l); fills.append((r["book"], r["ts"] // 1_000_000_000, r["p"], r["q"]))
def at(d, t):
    for k in range(t, t - 6, -1):
        if k in d: return d[k]
rows = []; inv = defaultdict(float)
for b, t, p, q in sorted(fills, key=lambda x: x[1]):
    d = mid[b]; m0 = at(d, t - 1); m300 = at(d, t - 301); m5 = at(d, t - 6); m600 = at(d, t + 600); m60 = at(d, t + 60)
    if None in (m0, m300, m5, m600, m60):
        s = 1 if p >= (m0 or p) else -1; inv[b] += s * q; continue
    s = 1 if p >= m0 else -1
    entry = abs(inv[b] + s * q) > abs(inv[b]) + 1e-9; inv[b] += s * q
    rows.append(dict(move300=-s * (m0 - m300) / m300 * 1e4, last5=-s * (m0 - m5) / m5 * 1e4, paid=s * (p - m0) / m0 * 1e4,
                     f60=s * (m60 - m0) / m0 * 1e4, f600=s * (m600 - m0) / m0 * 1e4, notional=p * q, entry=entry))
print("x2 fills with full context:", len(rows), "of", len(fills), "| entries", sum(r["entry"] for r in rows))
rows = [r for r in rows if r["entry"]]
print("ENTRIES ONLY:")
for k, lab in (("move300", "prior 300 s move we fade (bp, + = against us as intended)"), ("last5", "move in the 5 s before our fill (+ = still moving away)"),
               ("paid", "fill vs mid (bp paid; the validator ignores it)"), ("f60", "mid move our way after 60 s"), ("f600", "mid move our way after 600 s (the hold)")):
    v = np.array([r[k] for r in rows]); print("%-58s mean %+6.2f  median %+6.2f  hit>0 %3.0f%%" % (lab, v.mean(), np.median(v), (v > 0).mean() * 100))
