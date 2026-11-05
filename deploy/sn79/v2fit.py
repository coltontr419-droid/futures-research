"""Model v2 (decisions.md §1237): train on three old slices (A, B, C of the x1_size6 tape), compare v1 vs v2 on TODAY's unseen x1 tape (D)
across hold (300/600/900 s) × bet spacing per book (1800/3600/7200 s): kept books per 3 sim h, pass/fail, validator kappa, raw forward move."""
import json, sys
import numpy as np
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_of_alpha
L = lambda f: np.load(f)
tr = [L("/opt/mvtrx/v2_A.npz"), L("/opt/mvtrx/v2_B.npz"), L("/opt/mvtrx/v2_C.npz")]; D = L("/opt/mvtrx/v2_D.npz")
X = np.vstack([t["X"] for t in tr]); y = np.clip(np.concatenate([t["y600"] for t in tr]), -50, 50)
mu, sd = X.mean(0), X.std(0) + 1e-9; Z = np.clip((X - mu) / sd, -6, 6); A = np.c_[Z, np.ones(len(Z))]
w = np.linalg.solve(A.T @ A + 1000 * np.eye(A.shape[1]), A.T @ y); p_tr = A @ w; th2 = float(np.quantile(np.abs(p_tr), 0.98))
names = [str(n) for n in tr[0]["names"]]
print("v2 train rows %d (v1 had 252,928) | threshold %.2f bp | weights: " % (len(X), th2) + ", ".join("%s %+.2f" % (n, c) for n, c in sorted(zip(names, w[:-1]), key=lambda z: -abs(z[1]))[:7]))
m1 = json.load(open("/opt/mvtrx/agents/rev_model.json"))
p1 = np.clip((D["X"] - np.array(m1["mu"])) / np.array(m1["sd"]), -6, 6) @ np.array(m1["w"]) + m1["b"]
p2 = np.c_[np.clip((D["X"] - mu) / sd, -6, 6), np.ones(len(D["X"]))] @ w
print("today's tape: rows %d | forecast corr with the 600 s move: v1 %+.3f, v2 %+.3f" % (len(p1), np.corrcoef(p1, D["y600"])[0, 1], np.corrcoef(p2, D["y600"])[0, 1]))
bk, ts = D["book"], D["ts"]; span = (ts.max() - ts.min()) / 3600.0; order = np.argsort(ts, kind="stable")
print("model hold  spacing | bets  books  kept/3h  pass%  fail%  kappa   fwd bp  hit%")
for name, p, th in (("v1", p1, m1["th_top2pct"]), ("v2", p2, th2)):
    for hold in (300, 600, 900):
        y = D["y%d" % hold]
        for cool in (1800, 3600, 7200):
            last = {}; per = {}
            for i in order:
                if abs(p[i]) < th or ts[i] - last.get(bk[i], -10 ** 9) < cool: continue
                last[bk[i]] = ts[i]; per.setdefault(bk[i], []).append(np.sign(p[i]) * y[i])
            pb = np.array([np.mean(v) / 2 for v in per.values()]); g = np.array([r for v in per.values() for r in v])
            kept = [float(x) for x in pb if abs(x) >= 2.3]
            print("%-5s %4d  %6d | %4d  %5d  %6.0f   %4.0f   %4.0f  %+5.2f  %+6.2f  %3.0f" % (name, hold, cool, len(g), len(pb), len(kept) * 3 / span,
                  np.mean(pb > 2.3) * 100, np.mean(pb < -2.3) * 100, kappa_of_alpha(kept) if len(kept) >= 4 else 0, g.mean(), (g > 0).mean() * 100))
json.dump({"names": names, "mu": mu.tolist(), "sd": sd.tolist(), "w": w[:-1].tolist(), "b": float(w[-1]), "th_top2pct": th2,
           "note": "decisions.md 1237 v2: trained on slices A+B+C of live_tape_x1_size6"}, open("/opt/mvtrx/agents/rev_model_v2.json", "w"), indent=1)
print("saved agents/rev_model_v2.json (NOT used by any miner yet)")
