"""Do the new features improve entries out of sample? (decisions.md §1266) Ridge fit on one chunk, scored on a later one: base 15 features vs base + new, top 5% |forecast| rows, signed mid move at 300/600/900 s
(±50 clip) on books ≥ 63 and on all books, plus each new feature's correlation with the 600-s move on the test chunk. Also: among the top skill UIDs' entries, does each new feature separate winners from losers?"""
import sys, numpy as np
P = sys.argv[1:]
D = [dict(np.load(p)) for p in P]; names = list(D[0]["names"]); NB = 15
def fit(Ds, cols, lam=100.0):
    X = np.concatenate([d["X"][:, cols] for d in Ds]); y = np.clip(np.concatenate([d["y600"] for d in Ds]), -30, 30)
    mu, sd = X.mean(0), X.std(0) + 1e-9; Z = np.clip((X - mu) / sd, -6, 6); A = np.c_[np.ones(len(Z)), Z]
    L = lam * np.eye(A.shape[1]); L[0, 0] = 0; w = np.linalg.solve(A.T @ A + L, A.T @ y); th = np.quantile(np.abs(A @ w), .95)
    return lambda Q: np.c_[np.ones(len(Q)), np.clip((Q[:, cols] - mu) / sd, -6, 6)] @ w, th, w
for tr, te in ((0, 1), (1, 2), (0, 2)):
    d = D[te]; print(f"== fit chunk {tr} → test chunk {te}")
    for nm, cols in (("base 15", list(range(NB))), ("base + new", list(range(len(names))))):
        f, th, w = fit([D[tr]], cols); F = f(d["X"])
        for g, mk in (("books ≥ 63", d["book"] >= 63), ("all books", d["book"] >= 0)):
            h = mk & (np.abs(F) >= th); s = np.sign(F[h]); r = lambda k: f"{np.mean(s * np.clip(d[k][h], -50, 50)):+5.2f}/{np.mean(s * d[k][h] > 0):3.0%}"
            print(f"   {nm:11} {g:10} rows {h.sum():5d} | 300 {r('y300')} 600 {r('y600')} 900 {r('y900')}")
    if tr == 0: print("   new feature weights (z):", {n: round(float(c), 2) for n, c in zip(names[NB:], w[1 + NB:])})
d = D[-1]; y = np.clip(d["y600"], -30, 30)
print("correlation of each new feature with the 600-s move, last chunk:", {n: round(float(np.corrcoef(d["X"][:, i], y)[0, 1]), 3) for i, n in enumerate(names) if i >= NB})
