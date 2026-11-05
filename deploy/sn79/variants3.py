"""Skill-UID variant set for scaling (decisions.md §1228): each reversal variant scored over a 3-sim-hour slice like the validator's skill leg
(per-book alpha bp / notional, hurdle 2.3 bp, kappa_of_alpha on kept books), plus pairwise ENTRY overlap: share of A's entries with a
same-book, same-direction entry of B within ±30 sim s (crowding risk if both run as separate UIDs)."""
import json, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_of_alpha
MB = int(sys.argv[1]); OFF = int(sys.argv[2]) if len(sys.argv) > 2 else 0; mid = defaultdict(dict)
with open("/opt/mvtrx/live_tape_x1_size6.jsonl", "rb") as fh:
    fh.seek(0, 2); n = fh.tell(); end = n - OFF * 1_000_000; fh.seek(max(0, end - MB * 1_000_000)); fh.readline()
    for l in fh:
        if fh.tell() > end: break
        if b'"bid"' not in l: continue
        r = json.loads(l)
        if r.get("bid") and r.get("ask"):
            bd = sum(q for _, q in r.get("bids", [])); ad = sum(q for _, q in r.get("asks", []))
            mid[r["book"]][r["ts"] // 1_000_000_000] = ((r["bid"] + r["ask"]) / 2, (bd - ad) / (bd + ad) if bd + ad else 0.0)
S = {b: (np.array(sorted(d)), np.array([d[t][0] for t in sorted(d)]), np.array([d[t][1] for t in sorted(d)])) for b, d in mid.items()}
def run(thr, look, hold, cool, books=None, imb=None, clip=1000.0):
    alphas, entries = [], []
    for b, (ts, m, im) in S.items():
        if books is not None and b not in books: continue
        if len(ts) < look + hold + 10: continue
        idx = {t: i for i, t in enumerate(ts)}; inv = np.zeros(len(ts)); last = -10 ** 9; notional = 0.0
        for i in range(len(ts)):
            j = idx.get(ts[i] - look)
            if j is None or ts[i] - last < cool: continue
            r = (m[i] - m[j]) / m[j] * 1e4
            if abs(r) < thr: continue
            d = -np.sign(r)
            if imb is not None and d * im[i] < imb: continue          # depth must back the trade (§1230)
            k = np.searchsorted(ts, ts[i] + hold)
            inv[i:k] += d * clip / m[i]; last = ts[i]; notional += 2 * clip; entries.append((b, int(ts[i]), int(d)))
        if notional == 0: continue
        dm = np.diff(m); a = np.sum(inv[:-1] * dm) - np.mean(inv[:-1]) * np.sum(dm); alphas.append(a / notional * 1e4)
    a = np.array(alphas); kept = [float(x) for x in a if abs(x) >= 2.3]
    return dict(books=len(a), pas=float(np.mean(a > 2.3)) if len(a) else 0, fail=float(np.mean(a < -2.3)) if len(a) else 0,
                kept=len(kept), kappa=kappa_of_alpha(kept) if len(kept) >= 4 else 0.0, entries=entries)
ALL = set(S); EVEN = {b for b in ALL if b % 2 == 0}; ODD = ALL - EVEN
V = {"V0 x2 now": (12, 600, 2400, 3600, None, None), "V0 + depth>=0.17": (12, 600, 2400, 3600, None, 0.17),
     "S1 4bp/300/600/1200": (4, 300, 600, 1200, None, None), "S1 + depth>=0.17": (4, 300, 600, 1200, None, 0.17),
     "S2 3bp/120/600/900 + depth": (3, 120, 600, 900, None, 0.17), "S3 6bp/300/600/1800 + depth": (6, 300, 600, 1800, None, 0.17),
     "S4 5bp/300/900/2400 + depth": (5, 300, 900, 2400, None, 0.17), "S5 4bp/300/600/3600 + depth": (4, 300, 600, 3600, None, 0.17),
     "S6 8bp/600/1200/3600 + depth": (8, 600, 1200, 3600, None, 0.17)}
R = {k: run(*v) for k, v in V.items()}
print("slice %d MB (ending %d MB back), %d books, %.0f sim min" % (MB, OFF, len(S), np.median([(ts[-1] - ts[0]) / 60 for ts, _, _ in S.values()])))
print("%-36s books  pass  fail  kept  kappa  entries" % "variant")
for k, r in R.items(): print("%-36s %4d  %3.0f%%  %3.0f%%  %4d  %+5.2f  %6d" % (k, r["books"], r["pas"] * 100, r["fail"] * 100, r["kept"], r["kappa"], len(r["entries"])))
def overlap(A, B):
    by = defaultdict(list)
    for b, t, d in B: by[(b, d)].append(t)
    for v in by.values(): v.sort()
    hit = 0
    for b, t, d in A:
        v = by.get((b, d)); 
        if not v: continue
        i = np.searchsorted(v, t)
        if (i < len(v) and abs(v[i] - t) <= 30) or (i > 0 and abs(v[i - 1] - t) <= 30): hit += 1
    return hit / max(len(A), 1)

