"""Walk-forward refit of the reversal model (decisions.md §1254): chunks of x3's tape, oldest first. For each chunk: v1 (frozen) vs a ridge fit on the
PREVIOUS chunk(s), top 5% |forecast| rows (train-set threshold), signed mid move at 300/600/900 s, by all / calm+4dec; plus the raw reversal itself
(−sign(dmid300), top 5% |dmid300|) and the top skill UIDs' entries on that chunk, so model failure and market change can be told apart.
    python refit.py <tape> <mb per chunk> c1.npz c2.npz ...   (c1 oldest; offsets = (n−k) × mb)"""
import json, sys
import numpy as np
tape, MB = sys.argv[1], int(sys.argv[2]); paths = sys.argv[3:]
D = [dict(np.load(p)) for p in paths]; n = len(D)
SKILL = {103, 122, 8, 181, 197, 120, 195, 191, 203}                # §1244 minus UID 48, which the clone could not model
v1 = json.load(open("/opt/mvtrx/agents/rev_model.json"))
Zv = lambda X: np.clip((X - np.array(v1["mu"])) / np.array(v1["sd"]), -6, 6)
fv = lambda X: v1["b"] + Zv(X) @ np.array(v1["w"])
def fit(Ds, target, lam=100.0):
    X = np.concatenate([d["X"] for d in Ds]); y = np.concatenate([d[target] for d in Ds]); y = np.clip(y, -30, 30)
    mu, sd = X.mean(0), X.std(0) + 1e-9; Z = np.clip((X - mu) / sd, -6, 6); A = np.c_[np.ones(len(Z)), Z]
    R = lam * np.eye(A.shape[1]); R[0, 0] = 0; w = np.linalg.solve(A.T @ A + R, A.T @ y)
    return lambda Q: np.c_[np.ones(len(Q)), np.clip((Q - mu) / sd, -6, 6)] @ w
def show(name, f, d, th):
    m = np.abs(f) >= th; s = np.sign(f[m]); nv = d["book"][m] >= 63
    r = [f"{np.mean(s * np.clip(d[k][m], -50, 50)):+6.2f}/{np.mean(s * d[k][m] > 0):3.0%}" for k in ("y300", "y600", "y900")]
    q = [f"{np.mean(s[nv] * np.clip(d[k][m][nv], -50, 50)):+6.2f}/{np.mean(s[nv] * d[k][m][nv] > 0):3.0%}" if nv.any() else "n/a" for k in ("y300", "y600", "y900")]
    print(f"   {name:14} n {m.sum():5d} | all 300/600/900 s {' '.join(r)} | calm+4dec {' '.join(q)}")
def entries(k):
    OFF = (n - 1 - k) * MB; inv = {}; out = []
    with open(tape, "rb") as fh:
        fh.seek(0, 2); end = fh.tell() - OFF * 1_000_000; fh.seek(max(0, end - MB * 1_000_000)); fh.readline()
        while fh.tell() < end:
            l = fh.readline()
            if not l: break
            if b'"p"' not in l: continue
            r = json.loads(l); u = r.get("Ta")
            if u not in SKILL: continue
            d = r["q"] if r["s"] == 0 else -r["q"]; K = (u, r["book"]); a = inv.get(K, 0.0); inv[K] = a + d
            if abs(a + d) > abs(a) + 1e-12: out.append((r["book"], r["ts"] // 1_000_000_000, 1.0 if d > 0 else -1.0))
    return out
for k, d in enumerate(D):
    ts = d["ts"]; print(f"== chunk {k + 1}: sim min {ts.min() / 60:.0f}-{ts.max() / 60:.0f}, rows {len(ts)}")
    f = fv(d["X"]); show("v1 frozen", f, d, np.quantile(np.abs(fv(D[0]["X"])), .95))
    j = list(d["names"]).index("dmid300"); x = d["X"][:, j]; show("raw reversal", -x, d, np.quantile(np.abs(D[0]["X"][:, j]), .95))
    if k:
        for t in ("y600", "y900"):
            g = fit(D[max(0, k - 2):k], t); tr = np.concatenate([g(c["X"]) for c in D[max(0, k - 2):k]])
            show(f"refit {t}", g(d["X"]), d, np.quantile(np.abs(tr), .95))
    E = entries(k); idx = {}
    for b in np.unique(d["book"]):
        m = np.where(d["book"] == b)[0]; idx[int(b)] = (d["ts"][m], m)
    S, R = [], []
    for b, t, s in E:
        if b in idx:
            T, m = idx[b]; i = np.searchsorted(T, t, side="right") - 1
            if i >= 0 and t - T[i] <= 5: S.append(s); R.append(m[i])
    S, R = np.array(S), np.array(R)
    if len(S): print(f"   top skill UIDs n {len(S):5d} | " + " ".join(f"{np.mean(S * np.clip(d[k2][R], -50, 50)):+6.2f}/{np.mean(S * d[k2][R] > 0):3.0%}" for k2 in ("y300", "y600", "y900")))
