"""Export the §1233 predictor (600 s target, ridge λ=1000, train slice) to JSON for the live agent: z-score params, weights, the
|forecast| threshold for the top 2% of TRAIN rows, and the big-trade size threshold per book (95th pct of non-top trade sizes)."""
import json, numpy as np
tr = np.load("/opt/mvtrx/pred_train.npz"); names = [str(n) for n in tr["names"]]; X = tr["X"]
mu, sd = X.mean(0), X.std(0) + 1e-9; Z = np.clip((X - mu) / sd, -6, 6); y = np.clip(tr["y600"], -50, 50)
A = np.c_[Z, np.ones(len(Z))]; w = np.linalg.solve(A.T @ A + 1000 * np.eye(A.shape[1]), A.T @ y)
p = A @ w; th = float(np.quantile(np.abs(p), 0.98))
json.dump({"names": names, "mu": mu.tolist(), "sd": sd.tolist(), "w": w[:-1].tolist(), "b": float(w[-1]), "th_top2pct": th,
           "note": "decisions.md 1233; features in bp of mid; flow10/book10 normalised by the book running mean |per-second value| x 10"},
          open("/opt/mvtrx/agents/rev_model.json", "w"), indent=1)
print("exported", len(names), "features | threshold |forecast| >= %.3f bp" % th)
