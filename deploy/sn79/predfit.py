"""Fit the reversal predictor on the TRAIN slice, judge it on the unseen TEST slice (decisions.md §1233)."""
import numpy as np
tr, te = np.load("/opt/mvtrx/pred_train.npz"), np.load("/opt/mvtrx/pred_test.npz"); names = list(tr["names"])
Xtr, Xte = tr["X"], te["X"]; mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
clipz = lambda X: np.clip((X - mu) / sd, -6, 6)
Ztr, Zte = clipz(Xtr), clipz(Xte)
def ridge(Z, y, lam):
    A = np.c_[Z, np.ones(len(Z))]; w = np.linalg.solve(A.T @ A + lam * np.eye(A.shape[1]), A.T @ y); return w
pred = lambda w, Z: np.c_[Z, np.ones(len(Z))] @ w
print("train rows %d, test rows %d" % (len(Ztr), len(Zte)))
for tgt in ("y60", "y600"):
    ytr = np.clip(tr[tgt], -50, 50); yte = te[tgt]
    for lam in (10, 1000, 100000):
        w = ridge(Ztr, ytr, lam); p = pred(w, Zte)
        print("%s lam %6d | test corr %+.3f | in-sample corr %+.3f" % (tgt, lam, np.corrcoef(p, yte)[0, 1], np.corrcoef(pred(w, Ztr), ytr)[0, 1]))
    w = ridge(Ztr, ytr, 1000); print("  %s weights (per 1 sd): " % tgt + ", ".join("%s %+.2f" % (n, x) for n, x in sorted(zip(names, w[:-1]), key=lambda z: -abs(z[1]))[:8]))
w = ridge(Ztr, np.clip(tr["y600"], -50, 50), 1000); p = pred(w, Zte); y = te["y600"]; bk, ts = te["book"], te["ts"]
def trade(sel_dir, label, cool=3600):
    """one bet per book per COOL s on the selected rows, 600 s hold; raw forward bp in our direction and per-book pass/fail vs ±2.3 bp."""
    order = np.argsort(ts, kind="stable"); last = {}; per = {}; got = []
    for i in order:
        d = sel_dir[i]
        if d == 0 or ts[i] - last.get(bk[i], -10 ** 9) < cool: continue
        last[bk[i]] = ts[i]; r = d * y[i]; got.append(r); per.setdefault(bk[i], []).append(r)
    if not got: print("%-34s no trades" % label); return
    pb = np.array([np.mean(v) / 2 for v in per.values()])            # bp per unit of round-trip notional
    print("%-34s trades %5d | fwd600 our way %+5.2f bp, hit %3.0f%% | books %3d pass %3.0f%% fail %3.0f%%" % (
        label, len(got), np.mean(got), np.mean(np.array(got) > 0) * 100, len(pb), np.mean(pb > 2.3) * 100, np.mean(pb < -2.3) * 100))
I = names.index
S5 = np.where((np.abs(te["X"][:, I("dmid300")]) >= 4) & (-np.sign(te["X"][:, I("dmid300")]) * te["X"][:, I("imb")] >= 0.17), -np.sign(te["X"][:, I("dmid300")]), 0)
trade(S5, "S5 rule (x2 now)")
for q in (0.98, 0.995):
    th = np.quantile(np.abs(p), q); trade(np.where(np.abs(p) >= th, np.sign(p), 0), "model, top %.1f%% |forecast|" % ((1 - q) * 100))
    th2 = np.quantile(np.abs(p), q); trade(np.where(np.abs(p) >= th2, np.sign(p), 0), "model, top %.1f%%, 1 bet/book/2h" % ((1 - q) * 100), cool=7200)
