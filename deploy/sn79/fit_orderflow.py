"""MVTRX: fit the 30 s predictor with order-flow features (decisions.md §1206). From a live QuoteAgent tape that has "of" lines, build exactly
the features QuoteAgent._predict computes live (flow5, ret5, ret30, ret120, imb1, imb5, micro, of_new, of_near, of_cancel; order flow summed
over the last 5 s of updates), fit on the first 75% by time, score the new model and the deployed one on the last 25%, and export the new fit
(refit on all rows) when it is better.

    python fit_orderflow.py <tape.jsonl> <deployed model.json> <out model.json>
"""

import json
import sys
from collections import defaultdict

import numpy as np

NAMES = ["flow5", "ret5", "ret30", "ret120", "imb1", "imb5", "micro", "of_new", "of_near", "of_cancel"]
H = 30


def rows(path: str) -> np.ndarray:
    mids, depth, of, fl = defaultdict(dict), defaultdict(dict), defaultdict(lambda: defaultdict(lambda: [0.0] * 6)), defaultdict(lambda: defaultdict(float))
    for line in open(path):
        r = json.loads(line); s = r["ts"] // 1_000_000_000
        if "of" in r:
            o = of[r["book"]][s]
            for i, k in enumerate(("nb", "na", "nb2", "na2", "cb", "ca")):
                o[i] += r["of"].get(k, 0.0)
        elif "p" in r:
            fl[r["book"]][r["ts"] // 1_000_000_000] += r["q"] * (1 if r["s"] == 0 else -1)
        elif r.get("bids") and r.get("asks"):
            mids[r["book"]][s] = (r["bid"] + r["ask"]) / 2; depth[r["book"]][s] = (r["bids"], r["asks"])
    ratio = lambda x, y: (x - y) / (x + y) if x + y > 0 else 0.0
    out = []
    for b, ms in mids.items():
        for s in sorted(ms):
            if s - 120 not in ms or s + H not in ms:
                continue
            bids, asks = depth[b][s]; mid = ms[s]
            imb = lambda k: ratio(sum(x[1] for x in bids[:k]), sum(x[1] for x in asks[:k]))
            micro = (bids[0][0] * asks[0][1] + asks[0][0] * bids[0][1]) / (bids[0][1] + asks[0][1]) - mid
            o5 = [sum(of[b].get(s - j, [0.0] * 6)[i] for j in range(5)) for i in range(6)]
            x = [sum(fl[b].get(s - j, 0.0) for j in range(5)), mid - ms.get(s - 5, mid), mid - ms.get(s - 30, mid), mid - ms[s - 120],
                 imb(1), imb(5), micro, ratio(o5[0], o5[1]), ratio(o5[2], o5[3]), ratio(o5[5], o5[4])]
            out.append([s] + x + [ms[s + H] - mid])
    A = np.array(out, dtype=float)
    return A[np.argsort(A[:, 0])]


def ic(pred, y):
    return float(np.corrcoef(np.argsort(np.argsort(pred)), np.argsort(np.argsort(y)))[0, 1])


def main(tape: str, deployed: str, out: str) -> None:
    A = rows(tape); n = len(A); cut = int(n * 0.75); tr, te = A[:cut], A[cut:]
    X, y = A[:, 1:11], A[:, 11]
    mu, sd = X[:cut].mean(0), X[:cut].std(0); sd[sd == 0] = 1.0
    w, *_ = np.linalg.lstsq((X[:cut] - mu) / sd, y[:cut], rcond=None)
    new_ic = ic(((X[cut:] - mu) / sd) @ w, y[cut:])
    cur = json.load(open(deployed)); idx = [NAMES.index(k) for k in cur["names"]]
    cur_ic = ic(((X[cut:, idx] - np.array(cur["mu"])) / np.array(cur["sd"])) @ np.array(cur["w"]), y[cut:])
    q = np.quantile(((X[cut:] - mu) / sd) @ w, [0.1, 0.9]); p = ((X[cut:] - mu) / sd) @ w
    dec = (y[cut:][p >= q[1]].mean() - y[cut:][p <= q[0]].mean()) / 0.01
    print(f"rows {n} (test {n - cut}); held-out 30 s IC: new {new_ic:+.3f} vs deployed {cur_ic:+.3f}; new top-bottom decile {dec:+.1f} ticks")
    print("weights (z):", " ".join(f"{k}={v:+.4f}" for k, v in zip(NAMES, w)))
    if new_ic > cur_ic + 0.02:
        mu, sd = X.mean(0), X.std(0); sd[sd == 0] = 1.0
        w, *_ = np.linalg.lstsq((X - mu) / sd, y, rcond=None)
        json.dump({"horizon": H, "names": NAMES, "mu": mu.tolist(), "sd": sd.tolist(), "w0": 0.0, "w": w.tolist(), "rows": n,
                   "source": f"fit_orderflow on {tape}"}, open(out, "w"), indent=1)
        print("exported", out)
    else:
        print("not better: kept the deployed model")


if __name__ == "__main__":
    main(*sys.argv[1:4])
