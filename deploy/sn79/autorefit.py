"""Routine refit of the taker model with a gate (decisions.md §1256). Three consecutive chunks of market tape: fit a candidate on chunks 1-2, score it and the RUNNING model on chunk 3,
which neither saw, on the books x1 trades (ids ≥ 63), top 5% |forecast| rows. The candidate passes only if it beats the running model by ≥ 0.5 bp at 600 s, earns ≥ +1 bp, and is right
≥ 55% of the time. Then the final model is refit on chunks 2-3 (the same recipe as §1254).  python autorefit.py <running model json> <c1> <c2> <c3> <out json>   prints one JSON line."""
import json, sys
import numpy as np
run, c1, c2, c3, out = sys.argv[1:6]
D = [dict(np.load(p)) for p in (c1, c2, c3)]; R = json.load(open(run))
assert all(list(d["names"]) == R["names"] for d in D)
def fit(Ds, lam=100.0):
    X = np.concatenate([d["X"] for d in Ds]); y = np.clip(np.concatenate([d["y600"] for d in Ds]), -30, 30)
    mu, sd = X.mean(0), X.std(0) + 1e-9; Z = np.clip((X - mu) / sd, -6, 6); A = np.c_[np.ones(len(Z)), Z]
    L = lam * np.eye(A.shape[1]); L[0, 0] = 0; w = np.linalg.solve(A.T @ A + L, A.T @ y); f = A @ w
    return {"names": R["names"], "mu": mu.tolist(), "sd": sd.tolist(), "w": w[1:].tolist(), "b": float(w[0]), "th_top2pct": float(np.quantile(np.abs(f), .95))}
def pred(m, X):
    return m["b"] + np.clip((X - np.array(m["mu"])) / np.array(m["sd"]), -6, 6) @ np.array(m["w"])
def score(m, d):
    k = d["book"] >= 63; f = pred(m, d["X"][k]); y = d["y600"][k]; h = np.abs(f) >= m["th_top2pct"]
    if h.sum() < 200: return {"n": int(h.sum()), "bp": 0.0, "hit": 0.0}
    s = np.sign(f[h]); return {"n": int(h.sum()), "bp": round(float(np.mean(s * np.clip(y[h], -50, 50))), 2), "hit": round(float(np.mean(s * y[h] > 0)), 3)}
cand = fit(D[:2]); a, b = score(R, D[2]), score(cand, D[2])
ok = b["bp"] >= a["bp"] + 0.5 and b["bp"] >= 1.0 and b["hit"] >= 0.55 and b["n"] >= 200
final = fit(D[1:]); final["note"] = f"autorefit, decisions.md 1256; gate: running {a}, candidate {b}"
json.dump(final, open(out, "w"))
print(json.dumps({"pass": bool(ok), "running": a, "candidate": b}))
