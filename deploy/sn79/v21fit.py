"""Model v2.1 (decisions.md §1239): v2 with the raw fundamental gap replaced by the gap minus the book's own 30-min average (gapdev).
Train on slices A/B/C, compare with v1 on today's unseen tape D (hold 600/900 s, one bet per book per hour)."""
import json, sys
import numpy as np
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_of_alpha
tr = [np.load("/opt/mvtrx/v3_%s.npz" % k) for k in "ABC"]; D = np.load("/opt/mvtrx/v3_D.npz")
names = [str(n) for n in tr[0]["names"]]; keep = [i for i, n in enumerate(names) if n != "gap"]
X = np.vstack([t["X"][:, keep] for t in tr]); y = np.clip(np.concatenate([t["y600"] for t in tr]), -50, 50)
mu, sd = X.mean(0), X.std(0) + 1e-9; Z = np.clip((X - mu) / sd, -6, 6); A = np.c_[Z, np.ones(len(Z))]
w = np.linalg.solve(A.T @ A + 1000 * np.eye(A.shape[1]), A.T @ y); th = float(np.quantile(np.abs(A @ w), 0.98))
kn = [names[i] for i in keep]
print("v2.1 train rows %d | threshold %.2f bp | weights: " % (len(X), th) + ", ".join("%s %+.2f" % (n, c) for n, c in sorted(zip(kn, w[:-1]), key=lambda z: -abs(z[1]))[:7]))
m1 = json.load(open("/opt/mvtrx/agents/rev_model.json"))
p1 = np.clip((D["X"][:, :15] - np.array(m1["mu"])) / np.array(m1["sd"]), -6, 6) @ np.array(m1["w"]) + m1["b"]
p2 = np.c_[np.clip((D["X"][:, keep] - mu) / sd, -6, 6), np.ones(len(D["X"]))] @ w
print("today: forecast corr with the 600 s move: v1 %+.3f, v2.1 %+.3f" % (np.corrcoef(p1, D["y600"])[0, 1], np.corrcoef(p2, D["y600"])[0, 1]))
bk, ts = D["book"], D["ts"]; span = (ts.max() - ts.min()) / 3600.0; order = np.argsort(ts, kind="stable")
print("model hold | bets books kept/3h pass% fail% kappa  fwd bp hit%")
for name, p, t_h in (("v1", p1, m1["th_top2pct"]), ("v2.1", p2, th)):
    for hold in (600, 900):
        yy = D["y%d" % hold]; last = {}; per = {}
        for i in order:
            if abs(p[i]) < t_h or ts[i] - last.get(bk[i], -10 ** 9) < 3600: continue
            last[bk[i]] = ts[i]; per.setdefault(bk[i], []).append(np.sign(p[i]) * yy[i])
        pb = np.array([np.mean(v) / 2 for v in per.values()]); g = np.array([r for v in per.values() for r in v]); kept = [float(x) for x in pb if abs(x) >= 2.3]
        print("%-5s %4d | %4d %5d %6.0f %5.0f %5.0f %+5.2f %+6.2f %4.0f" % (name, hold, len(g), len(pb), len(kept) * 3 / span, np.mean(pb > 2.3) * 100,
              np.mean(pb < -2.3) * 100, kappa_of_alpha(kept) if len(kept) >= 4 else 0, g.mean(), (g > 0).mean() * 100))
json.dump({"names": kn, "mu": mu.tolist(), "sd": sd.tolist(), "w": w[:-1].tolist(), "b": float(w[-1]), "th_top2pct": th, "note": "decisions.md 1239 v2.1 (gapdev)"},
          open("/opt/mvtrx/agents/rev_model_v21.json", "w"), indent=1)
