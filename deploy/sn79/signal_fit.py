"""Out-of-sample check: fit a linear predictor of the h-second mid change on the first half of the tape (by time), test on the second."""
import json, sys
from collections import defaultdict
import numpy as np
path = sys.argv[1]
quotes, flow = defaultdict(dict), defaultdict(lambda: defaultdict(float))
for line in open(path):
    r = json.loads(line); sec = r["ts"] // 1_000_000_000
    if "p" in r: flow[r["book"]][sec] += r["q"] * (1 if r["s"] == 0 else -1)
    elif "bids" in r and r["bids"] and r["asks"]: quotes[r["book"]][sec] = r
NAMES = ["flow5", "ret5", "ret30", "ret120", "imb1", "imb5", "micro"]
rows = []
for book, q in quotes.items():
    secs = sorted(q); mid = {s: (q[s]["bid"] + q[s]["ask"]) / 2 for s in secs}
    for s in secs:
        if s - 120 not in mid: continue
        b, a = q[s]["bids"], q[s]["asks"]
        imb = lambda k: (sum(x[1] for x in b[:k]) - sum(x[1] for x in a[:k])) / (sum(x[1] for x in b[:k]) + sum(x[1] for x in a[:k]))
        micro = (b[0][0] * a[0][1] + a[0][0] * b[0][1]) / (b[0][1] + a[0][1]) - mid[s]
        x = [sum(flow[book].get(s - j, 0.0) for j in range(5)), mid[s] - mid.get(s - 5, mid[s]), mid[s] - mid.get(s - 30, mid[s]),
             mid[s] - mid[s - 120], imb(1), imb(5), micro]
        ys = [mid.get(s + h, np.nan) - mid[s] for h in (5, 30, 60)]
        rows.append([s] + x + ys)
A = np.array(rows, dtype=float); A = A[np.argsort(A[:, 0])]
MU, SD = A[:, 1:8].mean(0), A[:, 1:8].std(0)
X = A[:, 1:8]; X = (X - MU) / SD; X = np.c_[np.ones(len(X)), X]
half = len(A) // 2
for k, h in enumerate((5, 30, 60)):
    y = A[:, 8 + k]; ok = np.isfinite(y); tr = ok.copy(); tr[half:] = False; te = ok.copy(); te[:half] = False
    w, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None); pred = X @ w
    r2 = 1 - np.sum((y[te] - pred[te]) ** 2) / np.sum((y[te] - y[te].mean()) ** 2)
    ic = np.corrcoef(np.argsort(np.argsort(pred[te])), np.argsort(np.argsort(y[te])))[0, 1]
    q = np.quantile(pred[te], [0.1, 0.9]); dec = (y[te][pred[te] >= q[1]].mean() - y[te][pred[te] <= q[0]].mean()) / 0.01
    print(f"h={h:>2}s  out-of-sample R² {r2:+.3f}  IC {ic:+.3f}  top-bottom decile {dec:+.1f} ticks  weights(z) " + " ".join(f"{n}={v:+.4f}" for n, v in zip(NAMES, w[1:])))

if len(sys.argv) > 2:                                   # export the 60 s model, refit on ALL rows, for QuoteAgent (model=<path>)
    y = A[:, 10]; ok = np.isfinite(y); w, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
    json.dump({"horizon": 60, "names": NAMES, "mu": MU.tolist(), "sd": SD.tolist(), "w0": float(w[0]), "w": w[1:].tolist(), "rows": int(ok.sum())},
              open(sys.argv[2], "w"), indent=1)
    print("exported", sys.argv[2])
