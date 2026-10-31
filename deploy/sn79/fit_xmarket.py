"""Cross-market predictor check (decisions.md §1194): fit the 60 s linear predictor on TRAIN tapes, score it and the live model on
held-out TEST markets; export the new fit (all train rows) for QuoteAgent."""
import json, sys
import numpy as np
src = open("/opt/mvtrx/signal_fit.py").read().split("NAMES = [")[0]      # feature construction, one tape list per call
def features(paths):
    g = {"sys": sys, "rows": None}; sys.argv = ["x", ",".join(paths)]; exec(src, g)
    return np.array(g["rows"], dtype=float)
TRAIN, TEST = sys.argv[1].split(","), sys.argv[2].split(",")
train = features(TRAIN); test = features(TEST)
mu, sd = train[:, 1:8].mean(0), train[:, 1:8].std(0)
def ic_dec(w, mu_, sd_, A, k=10):
    y = A[:, k]; ok = np.isfinite(y); pred = ((A[:, 1:8] - mu_) / sd_) @ w
    ic = np.corrcoef(np.argsort(np.argsort(pred[ok])), np.argsort(np.argsort(y[ok])))[0, 1]
    q = np.quantile(pred[ok], [0.1, 0.9]); dec = (y[ok][pred[ok] >= q[1]].mean() - y[ok][pred[ok] <= q[0]].mean()) / 0.01
    return ic, dec
out = {}
for k, h in ((8, 5), (9, 30), (10, 60)):
    y = train[:, k]; ok = np.isfinite(y); X = (train[ok, 1:8] - mu) / sd
    w, *_ = np.linalg.lstsq(X, y[ok], rcond=None); out[h] = w
    ic, dec = ic_dec(w, mu, sd, test, k)
    print(f"new fit h={h:>2}s on held-out markets: IC {ic:+.3f}, top-bottom decile {dec:+.1f} ticks")
live = json.load(open("/opt/mvtrx/model60.json"))
ic, dec = ic_dec(np.array(live["w"]), np.array(live["mu"]), np.array(live["sd"]), test, 10)
print(f"LIVE run-4 model h=60s on held-out markets: IC {ic:+.3f}, top-bottom decile {dec:+.1f} ticks")
for h in (5, 30, 60):
    json.dump({"horizon": h, "names": ["flow5", "ret5", "ret30", "ret120", "imb1", "imb5", "micro"], "mu": mu.tolist(), "sd": sd.tolist(),
               "w0": 0.0, "w": out[h].tolist(), "rows": int(len(train))}, open(f"/opt/mvtrx/model{h}_v2.json", "w"), indent=1)
print("exported model30_v2.json, model60_v2.json; train rows", len(train), "test rows", len(test))
