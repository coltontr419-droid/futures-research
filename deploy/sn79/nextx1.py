"""Next x1 design (decisions.md §1260), walk-forward, scorer's alpha on the 5-s mid path, target 8 bp, no stop unless named. Tests: fit 2 → 3, fit 3 → 4, and the deployed v3 → newest chunk. Sweeps: entry threshold (top q of |f|), scale-in legs, book sets.
Note: open positions charge one leg of notional, and paper runs 2-3× optimistic. Compare rows, do not read levels."""
import json, sys, numpy as np
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_floored, hurdle_filter
D = {k: dict(np.load(f"/tmp/rf{k}.npz")) for k in (2, 3, 4, 5)}
v3 = json.load(open("/opt/mvtrx/agents/rev_model_v3.json"))
def fit(Ds, lam=100.0):
    X = np.concatenate([d["X"] for d in Ds]); y = np.clip(np.concatenate([d["y600"] for d in Ds]), -30, 30)
    mu, sd = X.mean(0), X.std(0) + 1e-9; Z = np.clip((X - mu) / sd, -6, 6); A = np.c_[np.ones(len(Z)), Z]
    L = lam * np.eye(A.shape[1]); L[0, 0] = 0; w = np.linalg.solve(A.T @ A + L, A.T @ y); return mu, sd, w, np.abs(A @ w)
def fc(mu, sd, w, X): return np.c_[np.ones(len(X)), np.clip((X - mu) / sd, -6, 6)] @ w
def sim(ts, mid, f, th, step, target, legs, gap, usd=1000.0):
    n = len(ts); inv = np.zeros(n); pos = 0.0; cost = 0.0; k = 0; notl = 0.0; last = -1e12; lastleg = -1e12
    clip = usd / legs
    for i in range(n):
        if pos:
            px = cost / abs(pos); r = np.sign(pos) * (mid[i] - px) / px * 1e4
            if r >= target: notl += abs(pos) * mid[i]; pos = 0.0; cost = 0.0; k = 0
        if abs(f[i]) >= th:
            s = np.sign(f[i])
            if not pos and ts[i] - last >= step:
                pos = s * clip / mid[i]; cost = clip; k = 1; last = ts[i]; lastleg = ts[i]; notl += clip
            elif pos and k < legs and np.sign(pos) == s and ts[i] - lastleg >= gap:
                pos += s * clip / mid[i]; cost += clip; k += 1; lastleg = ts[i]; notl += clip
        inv[i] = pos
    return inv, notl
def score(d, f, th, books, step=900, target=8, legs=1, gap=60):
    A, N = {}, {}
    for b in books:
        m = np.where(d["book"] == b)[0]
        if len(m) < 100: continue
        md = d["mid"][m]; inv, notl = sim(d["ts"][m], md, f[m], th, step, target, legs, gap)
        if notl <= 0: continue
        A[int(b)] = float(np.sum((inv[:-1] - inv.mean()) * np.diff(md))); N[int(b)] = notl
    k = hurdle_filter({0: A}, {0: N}, 2.3)[0]; bp = sorted(1e4 * A[b] / N[b] for b in A); tn = sum(N.values())
    return f"books {len(A):3d} kept {len(k):3d} pos {sum(v > 0 for v in k.values()):3d} median {bp[len(bp) // 2] if bp else 0:+5.2f} total {1e4 * sum(A.values()) / max(tn, 1):+5.2f} $ {tn / 1000:6.0f}k kappa {kappa_floored(list(k.values()), 0.0, 4):+5.2f}"
T = []
for tr, te in ((2, 3), (3, 4)):
    mu, sd, w, abs_f = fit([D[tr]]); T.append((f"{tr}→{te}", D[te], fc(mu, sd, w, D[te]["X"]), abs_f))
d5 = D[5]; d34 = np.concatenate([D[3]["X"], D[4]["X"]]); m_ = (np.array(v3["mu"]), np.array(v3["sd"]), np.r_[v3["b"], v3["w"]]); T.append(("v3→5", d5, fc(*m_, d5["X"]), np.abs(fc(*m_, d34))))
print("rows per test:", [(n, len(d["ts"]), round(d["ts"].min() / 60), round(d["ts"].max() / 60)) for n, d, _, _ in T])
hi = lambda d: [b for b in np.unique(d["book"]) if b >= 63]
print("== entry threshold, books ≥ 63")
for q in (.05, .10, .20, .30):
    for n, d, f, a in T: print(f"  top {q:.0%} {n:5} {score(d, f, float(np.quantile(a, 1 - q)), hi(d))}")
print("== scale-in, books ≥ 63, top 10%")
for legs, gap in ((1, 60), (3, 60), (6, 60), (6, 20)):
    for n, d, f, a in T: print(f"  legs {legs} gap {gap:3d} {n:5} {score(d, f, float(np.quantile(a, .9)), hi(d), legs=legs, gap=gap)}")
print("== target, books ≥ 63, top 10%")
for tg in (6, 8, 12, 16):
    for n, d, f, a in T: print(f"  target {tg:2d} {n:5} {score(d, f, float(np.quantile(a, .9)), hi(d), target=tg)}")
print("== book sets, target 8, top 10%: add the 20 $300 books strongest in the PRIOR chunk (no look-ahead)")
for (n, d, f, a), prior in zip(T, (D[2], D[3], D[4])):
    th = float(np.quantile(a, .9)); pf = T[0][2] if False else None
    # strength per $300 book on the prior chunk: signed y600 of the top forecasts, using the same fit
    mu, sd, w, _ = fit([prior]); g = fc(mu, sd, w, prior["X"]); h = np.abs(g) >= np.quantile(np.abs(g), .9); s = {}
    for b in np.unique(prior["book"][prior["book"] < 63]):
        m = h & (prior["book"] == b)
        if m.sum() >= 10: s[int(b)] = float(np.mean(np.sign(g[m]) * np.clip(prior["y600"][m], -30, 30)))
    top = sorted(s, key=s.get, reverse=True)[:20]
    print(f"  ≥63 only   {n:5} {score(d, f, th, hi(d))}"); print(f"  + 20 $300  {n:5} {score(d, f, th, hi(d) + top)}"); print(f"  only those {n:5} {score(d, f, th, top)}"); print(f"  all books  {n:5} {score(d, f, th, list(np.unique(d['book'])))}")
