"""MEASURED, held-out: predict the $300 mid move over the next H s (60 / 120) from the market model's ingredients, sampled every 5 s per book.
Features (bp): gap = fund − mid; dF30 / dF60 / dF300 (fundamental trend, Hurst 0.73); r10 / r50 / r300 / r600 (chartist momentum / reversion); sweep60 = net $ of
taker −1 (ALGO) last 60 s (k$, + = buying); flow60 = other takers' net $ (k$). Train first 70% by time, test last 30%. Compare: model vs fade (−(r60+r300)) vs fund-move (dF10).
Report test corr, and mean move in the predicted direction for the top 30% |signal| (bp) — the lean's usable edge."""
import json, sys, collections, os, numpy as np
L0, L1 = (int(x) for x in os.environ.get("BOOKS", "0-127").split("-")); OUT = os.environ.get("OUT", "/opt/mvtrx/speed/model_lean.json"); TICK = float(os.environ.get("TICK", "0.01"))
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
M = collections.defaultdict(dict); F = collections.defaultdict(dict); SW = collections.defaultdict(lambda: collections.defaultdict(float)); FL = collections.defaultdict(lambda: collections.defaultdict(float)); seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0 or b'"book": ' not in l: continue
    try: ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    except ValueError: continue
    if s < LO - 620 or s > HI + 125: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if not (L0 <= bk <= L1): continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"):
            M[bk][s] = (r["bid"] + r["ask"]) / 2
            if r.get("fund"): F[bk][s] = r["fund"]
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k); v = (1 if r["s"] == 0 else -1) * r["p"] * r["q"] / 1e3
        (SW if r.get("Ta") == -1 else FL)[bk][s] += v
NAMES = ["gap", "dF30", "dF60", "dF300", "r10", "r50", "r300"]
rows = {60: [], 120: []}
for bk in M:
    m, f = M[bk], F[bk]
    for s in range(LO, HI, 5):
        x = m.get(s); 
        if x is None or s not in f: continue
        def ret(k): y = m.get(s - k); return (x - y) / x * 1e4 if y else None
        def fch(k): y = f.get(s - k); return (f[s] - y) / x * 1e4 if y else None
        r10, r50, r300, r600 = ret(10), ret(50), ret(300), ret(600); d30, d60, d300 = fch(30), fch(60), fch(300); d10 = fch(10)
        if None in (r10, r50, r300, r600, d30, d60, d300, d10): continue
        sw = sum(SW[bk].get(s - t, 0.0) for t in range(1, 61)); fl = sum(FL[bk].get(s - t, 0.0) for t in range(1, 61))
        feat = [(f[s] - x) / x * 1e4, d30, d60, d300, r10, r50, r300]
        for H in (60, 120):
            y = m.get(s + H)
            if y is not None: rows[H].append((s, feat, (y - x) / x * 1e4, -(ret(60) + r300) if ret(60) is not None else 0.0, d10))
for H, R in rows.items():
    R.sort(key=lambda r: r[0]); n = len(R); k = int(0.7 * n)
    X = np.array([r[1] for r in R]); Y = np.array([r[2] for r in R]); FD = np.array([r[3] for r in R]); FM = np.array([r[4] for r in R])
    mu, sd = X[:k].mean(0), X[:k].std(0) + 1e-9; Z = (X - mu) / sd
    lam = 10.0; A = Z[:k].T @ Z[:k] + lam * np.eye(Z.shape[1]); w = np.linalg.solve(A, Z[:k].T @ (Y[:k] - Y[:k].mean()))
    P = Z @ w
    if H == 120:
        thr = float(np.quantile(np.abs(P[:k]), 0.7))
        json.dump({"names": NAMES, "w": [float(v) for v in w], "mu": [float(v) for v in mu], "sd": [float(v) for v in sd], "thr": thr, "H": H,
                   "fit": f"sim {R[0][0]}-{R[k - 1][0]} (train), ridge 10, 11-15 §1486"}, open(OUT, "w"), indent=1)
        print(f"   saved model_lean.json, top-30% threshold |pred| ≥ {thr:.3f} bp")
    def score(sig, name):
        st_, yt = sig[k:], Y[k:]; c = np.corrcoef(st_, yt)[0, 1]
        thr = np.quantile(np.abs(st_), 0.7); sel = np.abs(st_) >= thr
        edge = np.mean(np.sign(st_[sel]) * yt[sel])
        print(f"   H {H:3d}s {name:22} test corr {c:+.3f} | top-30% |signal|: move in its direction {edge:+.2f} bp (n {sel.sum()})")
    print(f"== H {H} s: {n} samples (train {k}, test {n - k}); weights (z): " + ", ".join(f"{nm} {wt:+.2f}" for nm, wt in sorted(zip(NAMES, w), key=lambda t: -abs(t[1]))))
    score(P, "MODEL (all features)"); score(FD, "fade −(r60+r300)"); score(FM, "fund-move dF10")
    q = (n - k) // 4
    for part in range(4):
        a, b = k + part * q, k + (part + 1) * q; st_, yt = P[a:b], Y[a:b]; thr = np.quantile(np.abs(st_), 0.7); sel = np.abs(st_) >= thr
        stf = FD[a:b]; thf = np.quantile(np.abs(stf), 0.7); self_ = np.abs(stf) >= thf
        print(f"      test window {part + 1} (sim {R[a][0]}–{R[b - 1][0]}): MODEL corr {np.corrcoef(st_, yt)[0, 1]:+.3f}, top-30% {np.mean(np.sign(st_[sel]) * yt[sel]):+.2f} bp | fade corr {np.corrcoef(stf, yt)[0, 1]:+.3f}, top-30% {np.mean(np.sign(stf[self_]) * yt[self_]):+.2f} bp")
