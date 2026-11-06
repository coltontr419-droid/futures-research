"""Clone the top skill miners' direction, then score forecasts with a paper version of the validator's skill (decisions.md §1249).

1. Entries of the top skill-only UIDs (taker trades that grow |inventory| per book) on a tape slice, joined to our 15 features at that second
   (predfeat4 table, 5-s rows). Label = their direction. Fit a ridge-logistic clone on the TRAIN slice; test on an independent slice.
2. Paper skill on the TEST rows: per forecast (v1 rev_model, the clone, random), per threshold (top q% of |f|) and hold H: one position per book
   at a time, ±USD for H s, then flat. Per book alpha = Σ pos × Δmid over the hold − mean inventory × book drift (the validator's de-beta),
   notional = 2 × USD per entry; then the validator's own hurdle_filter (2.3 bp) and kappa_floored (floor 0, min 4 books).
   No own impact and no spread (the scorer charges neither); the lab showed own impact ≤ ±0.8 bp (§1248).

    python clone.py <train.npz> <train tape> <train MB> <train OFF MB> <test.npz> <test tape> <test MB> <test OFF MB>
"""
import json, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_floored, hurdle_filter  # noqa: E402

SKILL = {103, 122, 8, 181, 197, 120, 195, 191, 48, 203}           # §1244 top skill-only UIDs (skill 3-4.3, 62-86 books)
trn_npz, trn_tape, trn_mb, trn_off, tst_npz, tst_tape, tst_mb, tst_off = sys.argv[1:9]


def entries(tape, MB, OFF):
    inv = defaultdict(float); out = []
    with open(tape, "rb") as fh:
        fh.seek(0, 2); end = fh.tell() - int(OFF) * 1_000_000; fh.seek(max(0, end - int(MB) * 1_000_000)); fh.readline()
        while fh.tell() < end:
            l = fh.readline()
            if not l: break
            if b'"p"' not in l: continue
            r = json.loads(l); u = r.get("Ta")
            if u not in SKILL: continue
            d = r["q"] if r["s"] == 0 else -r["q"]               # s == 0: the resting order was the sell → the taker bought
            k = (u, r["book"]); a = inv[k]; inv[k] = a + d
            if abs(a + d) > abs(a) + 1e-12:
                out.append((r["book"], r["ts"] // 1_000_000_000, 1.0 if d > 0 else -1.0, u))
    return out


def join(D, ent):
    idx = {}
    for b in np.unique(D["book"]):
        m = np.where(D["book"] == b)[0]; idx[int(b)] = (D["ts"][m], m)
    X, y, u = [], [], []
    for b, t, s, uid in ent:
        if b not in idx: continue
        ts, m = idx[b]; j = np.searchsorted(ts, t, side="right") - 1
        if j < 0 or t - ts[j] > 5: continue
        X.append(D["X"][m[j]]); y.append(s); u.append(uid)
    return np.array(X), np.array(y), np.array(u)


v1 = json.load(open("/opt/mvtrx/agents/rev_model.json"))
z1 = lambda X: np.clip((X - np.array(v1["mu"])) / np.array(v1["sd"]), -6, 6)
f_v1 = lambda X: v1["b"] + z1(X) @ np.array(v1["w"])

Dtr, Dte = dict(np.load(trn_npz)), dict(np.load(tst_npz))   # load once: indexing an NpzFile re-decompresses the whole array
Etr, Ete = entries(trn_tape, trn_mb, trn_off), entries(tst_tape, tst_mb, tst_off)
Xtr, ytr, utr = join(Dtr, Etr); Xte, yte, ute = join(Dte, Ete)
print(f"top-skill entries: train {len(Etr)} ({len(ytr)} joined, buy share {np.mean(ytr > 0):.2f}) | test {len(Ete)} ({len(yte)} joined)")

mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
Z = lambda X: np.clip((X - mu) / sd, -6, 6)
A = np.c_[np.ones(len(Xtr)), Z(Xtr)]; w = np.zeros(A.shape[1]); t01 = (ytr > 0).astype(float)
for _ in range(60):                                                  # ridge-logistic, Newton steps
    p = 1 / (1 + np.exp(-A @ w)); H = (A * (p * (1 - p))[:, None]).T @ A + 1.0 * np.eye(len(w)); w -= np.linalg.solve(H, A.T @ (p - t01) + 1.0 * w)
f_cl = lambda X: np.c_[np.ones(len(X)), Z(X)] @ w
acc = lambda f, X, y: np.mean(np.sign(f(X)) == y)
print(f"clone accuracy on top-skill entries: train {acc(f_cl, Xtr, ytr):.3f} | TEST {acc(f_cl, Xte, yte):.3f} (base rate {max(np.mean(yte > 0), np.mean(yte < 0)):.3f})")
print(f"v1 model agrees with their direction: train {acc(f_v1, Xtr, ytr):.3f} | test {acc(f_v1, Xte, yte):.3f}")
for u in sorted(set(ute)):
    m = ute == u; print(f"   uid {u:3d}: test entries {m.sum():5d}, clone acc {np.mean(np.sign(f_cl(Xte[m])) == yte[m]):.3f}")
print("clone weights (z):", {n: round(float(c), 3) for n, c in zip(list(Dtr["names"]), w[1:])})

# do their entry directions themselves predict the mid over the hold (are they right)? per test entry, signed move at 300/600/900/1800 s
idx = {int(b): (Dte["ts"][np.where(Dte["book"] == b)[0]], np.where(Dte["book"] == b)[0]) for b in np.unique(Dte["book"])}
rows = []
for b, t, s, uid in Ete:
    if b in idx:
        ts, m = idx[b]; j = np.searchsorted(ts, t, side="right") - 1
        if j >= 0 and t - ts[j] <= 5: rows.append((s, m[j]))
S = np.array([r[0] for r in rows]); R = np.array([r[1] for r in rows])
print("their entries, mean signed mid move (bp, + = right) at 300/600/900/1800 s:",
      " / ".join(f"{np.mean(S * Dte[k][R]):+.2f}" for k in ("y300", "y600", "y900", "y1800")))

# paper skill
B, TS, Xte_all = Dte["book"], Dte["ts"], Dte["X"]
def paper(f, q, H, usd=1000.0):
    th = np.quantile(np.abs(f), 1 - q); yk = {300: "y300", 600: "y600", 900: "y900", 1800: "y1800"}[H]; Y = Dte[yk]
    alpha, notl = {}, {}
    for b in np.unique(B):
        m = np.where(B == b)[0]; ts = TS[m]; span = ts[-1] - ts[0] + H
        mids = Dte["mid"][m]; drift_bp = (mids[-1] - mids[0]) / mids[0] * 1e4
        busy = -1; pnl = 0.0; invt = 0.0; n = 0
        for k, i in enumerate(m):
            if ts[k] < busy or abs(f[i]) < th: continue
            s = np.sign(f[i]); pnl += s * usd * Y[i] / 1e4; invt += s * usd * H; busy = ts[k] + H; n += 1
        if n:
            alpha[int(b)] = pnl - (invt / span) * drift_bp / 1e4; notl[int(b)] = 2 * usd * n
    kept = hurdle_filter({0: alpha}, {0: notl}, 2.3)[0]
    bp = sorted(1e4 * alpha[b] / notl[b] for b in alpha)
    return len(alpha), len(kept), sum(v > 0 for v in kept.values()), bp[len(bp) // 2] if bp else 0.0, kappa_floored(list(kept.values()), 0.0, 4)
rng = np.random.default_rng(1)
F = {"v1 model": f_v1(Xte_all), "clone": f_cl(Xte_all), "random": rng.standard_normal(len(Xte_all))}
print("paper skill on the TEST slice: forecast | top q | hold s → books traded, kept, kept positive, median α bp, kappa")
for name, f in F.items():
    for q in (0.02, 0.05, 0.10, 0.25):
        for H in (300, 600, 900, 1800):
            n, k, kp, med, kap = paper(f, q, H)
            print(f"  {name:8} q {q:.2f} H {H:4d}: books {n:3d} kept {k:3d} pos {kp:3d} | median {med:+6.2f} bp | kappa {kap:+.3f}")
