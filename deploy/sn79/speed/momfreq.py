"""4-dec momentum lean census: signal = (mid − mid 60 s ago) + (mid − mid 300 s ago) in bp; lean in its direction when |signal| ≥ k × the top-30% threshold.
Per k: share of book-seconds active and mid move in the lean direction after 60 / 120 / 300 s (bp)."""
import json, sys, collections, numpy as np
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
M = collections.defaultdict(dict)
for l in open(tape, "rb"):
    if b'"bid": ' not in l[:90]: continue
    i = l.find(b'"ts": '); s = int(l[i + 6:l.index(b",", i)]) // 10**9
    if s < LO - 310 or s > HI + 310: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if bk < 192: continue
    r = json.loads(l)
    if r.get("bid") and r.get("ask"): M[bk][s] = (r["bid"] + r["ask"]) / 2
def at(d, s):
    for x in range(s, s + 3):
        if x in d: return d[x]
rows = []
for bk, m in M.items():
    for s in range(LO, HI, 2):
        mid = m.get(s)
        if not mid: continue
        a60, a300 = at(m, s - 60), at(m, s - 300); f = [at(m, s + h) for h in (60, 120, 300)]
        if None in (a60, a300) or None in f: continue
        sig = ((mid - a60) + (mid - a300)) / mid * 1e4
        rows.append((sig, [(x - mid) / mid * 1e4 for x in f]))
sig = np.array([r[0] for r in rows]); fut = np.array([r[1] for r in rows]); thr = np.percentile(np.abs(sig), 70)
print(f"sim {LO}-{HI}: book-seconds {len(rows)}, top-30% |signal| threshold {thr:.2f} bp")
for k in (0.75, 1.0, 1.5, 2.0, 3.0):
    a = np.abs(sig) >= k * thr; d = np.sign(sig[a])[:, None] * fut[a]
    print(f"  k {k:4.2f}: active {a.mean():5.1%} | move in lean direction +60 s {d[:, 0].mean():+.2f}, +120 s {d[:, 1].mean():+.2f}, +300 s {d[:, 2].mean():+.2f} bp")
