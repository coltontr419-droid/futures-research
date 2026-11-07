"""§1259 test: scorer alpha (Σ (inv − mean inv) × Δmid per book) for one set of walk-forward entries under different exits, on the 5-s mid path. Fit on the earlier chunk, score the later one, books ≥ 63 and all books."""
import sys, numpy as np
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_floored, hurdle_filter
D = {k: dict(np.load(f"/tmp/rf{k}.npz")) for k in (2, 3, 4)}
def fit(Ds, lam=100.0):
    X = np.concatenate([d["X"] for d in Ds]); y = np.clip(np.concatenate([d["y600"] for d in Ds]), -30, 30)
    mu, sd = X.mean(0), X.std(0) + 1e-9; Z = np.clip((X - mu) / sd, -6, 6); A = np.c_[np.ones(len(Z)), Z]
    L = lam * np.eye(A.shape[1]); L[0, 0] = 0; w = np.linalg.solve(A.T @ A + L, A.T @ y); return mu, sd, w, float(np.quantile(np.abs(A @ w), .95))
def sim(ts, mid, f, th, step, target, stop, usd=1000.0):
    """target None: clock exit at `stop`. stop None: hold until the target, however long. Returns inventory path ($/mid units) and notional."""
    n = len(ts); inv = np.zeros(n); pos = 0.0; px = 0.0; t0 = -1e12; notl = 0.0; last = -1e12; opens = closes = 0; park = 0
    for i in range(n):
        if pos:
            r = np.sign(pos) * (mid[i] - px) / px * 1e4; done = False
            if target is not None and r >= target: done = True
            if stop is not None and ts[i] - t0 >= stop: done = True
            if done: notl += abs(pos) * mid[i]; pos = 0.0; closes += 1
        if not pos and abs(f[i]) >= th and ts[i] - last >= step:
            pos = np.sign(f[i]) * usd / mid[i]; px = mid[i]; t0 = ts[i]; last = ts[i]; notl += usd; opens += 1
        inv[i] = pos
    return inv, notl, opens, closes
def score(d, f, th, books, step, target, stop):
    A, N = {}, {}; o = c = 0; pnl = 0.0
    for b in books:
        m = np.where(d["book"] == b)[0]; ts = d["ts"][m]; md = d["mid"][m]
        if len(m) < 100: continue
        inv, notl, op, cl = sim(ts, md, f[m], th, step, target, stop); o += op; c += cl
        if notl <= 0: continue
        dm = np.diff(md); a = float(np.sum((inv[:-1] - inv.mean()) * dm)); A[int(b)] = a; N[int(b)] = notl; pnl += float(np.sum(inv[:-1] * dm))
    k = hurdle_filter({0: A}, {0: N}, 2.3)[0]; bp = sorted(1e4 * A[b] / N[b] for b in A); tn = sum(N.values())
    return f"books {len(A):3d} kept {len(k):3d} pos {sum(v > 0 for v in k.values()):3d} | median α {bp[len(bp) // 2] if bp else 0:+6.2f} bp | total α {1e4 * sum(A.values()) / max(tn, 1):+6.2f} bp | raw P&L {1e4 * pnl / max(tn, 1):+6.2f} bp | opened {o} closed {c} still open {o - c} | kappa {kappa_floored(list(k.values()), 0.0, 4):+.2f}"
for tr, te in ((3, 4), (2, 3)):
    mu, sd, w, th = fit([D[tr]]); d = D[te]; f = np.c_[np.ones(len(d["X"])), np.clip((d["X"] - mu) / sd, -6, 6)] @ w
    for nm, bk in (("all books", [b for b in np.unique(d["book"])]), ("books ≥ 63", [b for b in np.unique(d["book"]) if b >= 63])):
        print(f"== fit chunk {tr} → test chunk {te}, {nm}, {len(bk)} books")
        for lab, step, tg, st_ in (("clock 900 s (x1 today)", 900, None, 900), ("target 4 bp, 1 h stop", 900, 4, 3600), ("target 4 bp, NO stop", 900, 4, None), ("target 2 bp, NO stop", 900, 2, None), ("target 8 bp, NO stop", 900, 8, None)):
            print(f"   {lab:24} {score(d, f, th, bk, step, tg, st_)}")
