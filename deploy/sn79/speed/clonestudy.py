"""CLONE STUDY (MEASURED + held-out): can visible features predict the DIRECTION of UIDs 60/232's taker trades, and does OUR clone's call make money?
Features at the second before each trade (book-level, bp): dmid300, dmid60, dmid10, fund-mid, dfund60, imb5, micro (ticks), flow10 ($k signed), spread.
Train = first 70% of the window by time, test = last 30%. Then score the clone on ALL $300/4-dec book-seconds of the test part: when |p − 0.5| > thr,
the 20/120-s mid move in the predicted direction (bp; NO fees; a taker pays the spread — half-spread shown). python clonestudy.py tape lo hi uids..."""
import json, sys, collections, math, random
import numpy as np
from sklearn.linear_model import LogisticRegression
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); U = set(int(u) for u in sys.argv[4:])
B = collections.defaultdict(dict); TR = collections.defaultdict(list); Y = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0 or b'"book": ' not in l: continue
    try: ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    except ValueError: continue
    if s < LO - 320 or s > HI + 125: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if 128 <= bk < 192: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask") and r.get("bids") and r.get("asks"):
            bq = sum(x[1] for x in r["bids"][:5]); aq = sum(x[1] for x in r["asks"][:5]); b0, a0 = r["bids"][0], r["asks"][0]
            mp = (b0[0] * a0[1] + a0[0] * b0[1]) / (b0[1] + a0[1])
            B[bk][s] = ((r["bid"] + r["ask"]) / 2, r.get("fund"), (bq - aq) / (bq + aq) if bq + aq else 0.0, mp, r["ask"] - r["bid"])
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k); sg = 1 if r["s"] == 0 else -1; TR[bk].append((s, sg * r["p"] * r["q"]))
        if r.get("Ta") in U and LO <= s < HI: Y.append((s, bk, sg))
tick = lambda bk: 0.01 if bk < 128 else 0.0001
def feats(bk, s):
    d = B[bk]; a = d.get(s - 1)
    if not a or not a[1]: return None
    m = a[0]
    def ret(k):
        x = d.get(s - 1 - k); return (m - x[0]) / m * 1e4 if x else None
    r300, r60, r10 = ret(300), ret(60), ret(10); f60 = d.get(s - 61)
    if r300 is None or r60 is None or r10 is None or not f60 or not f60[1]: return None
    fg = (a[1] - m) / m * 1e4; dfg = fg - (f60[1] - f60[0]) / f60[0] * 1e4
    fl = sum(v for t, v in TR[bk] if s - 10 <= t < s) / 1e3
    return [r300, r60, r10, fg, dfg, a[2], (a[3] - m) / tick(bk), fl, a[4] / m * 1e4]
for bk in TR: TR[bk].sort()
NAMES = ["dmid300", "dmid60", "dmid10", "fund-mid", "dfund60", "imb5", "micro", "flow10", "spread"]
X, y, t = [], [], []
for s, bk, sg in Y:
    f = feats(bk, s)
    if f: X.append(f); y.append(1 if sg > 0 else 0); t.append(s)
X, y, t = np.array(X), np.array(y), np.array(t); o = np.argsort(t); X, y, t = X[o], y[o], t[o]
n = len(y); k = int(0.7 * n); mu, sd = X[:k].mean(0), X[:k].std(0) + 1e-9
clf = LogisticRegression(C=1.0, max_iter=2000).fit((X[:k] - mu) / sd, y[:k])
acc_tr = clf.score((X[:k] - mu) / sd, y[:k]); acc_te = clf.score((X[k:] - mu) / sd, y[k:]); base = max(y[k:].mean(), 1 - y[k:].mean())
print(f"uids {sorted(U)}: {n} taker trades with features | test accuracy {acc_te:.1%} (train {acc_tr:.1%}, base {base:.1%})")
print("  weights (z): " + ", ".join(f"{nm} {w:+.2f}" for nm, w in sorted(zip(NAMES, clf.coef_[0]), key=lambda x: -abs(x[1]))))
# score the clone on all book-seconds of the test period
tcut = t[k]; R = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0])
for bk, d in B.items():
    for s in range(int(tcut), int(HI)):
        if s % 5: continue                       # every 5 s to keep it light
        f = feats(bk, s); a = d.get(s - 1); b20 = d.get(s + 20); b120 = d.get(s + 120)
        if not f or not b20 or not b120: continue
        p = clf.predict_proba((np.array([f]) - mu) / sd)[0, 1]; e = abs(p - 0.5)
        for thr in (0.1, 0.2, 0.3):
            if e > thr:
                sg = 1 if p > 0.5 else -1; m = a[0]; c = "$300" if bk < 128 else "4dec"
                x = R[(c, thr)]; x[0] += 1; x[1] += sg * (b20[0] - m) / m * 1e4; x[2] += sg * (b120[0] - m) / m * 1e4; x[3] += a[4] / 2 / m * 1e4
print("  clone calls on ALL book-seconds of the test part (every 5 s): mid move in the called direction, bp (no fees; a taker also pays ≈ half-spread)")
for (c, thr), x in sorted(R.items()):
    print(f"   {c} |p−0.5| > {thr}: n {x[0]:6d} | 20 s {x[1] / x[0]:+.2f}  120 s {x[2] / x[0]:+.2f} | half-spread {x[3] / x[0]:.2f}")
