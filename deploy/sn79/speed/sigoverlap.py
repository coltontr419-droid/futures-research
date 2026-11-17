"""$300 books: alternative lean signals for a 3rd/4th miner vs the LIVE signal A (model_lean.json, |pred| ≥ 1.5 thr). For each candidate B: share of book-seconds active, OVERLAP = share of B's
active seconds where A leans the same side on the same book (within ±5 s), and B's edge (mid move in its direction, each book's whole-window drift removed) on ALL its seconds and on its
B-only seconds (A not leaning that way) — the new volume a separate miner could take without splitting our fills."""
import json, sys, collections, numpy as np
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
ml = json.load(open("/opt/mvtrx/agents/model_lean.json")); N = ml["names"]
M = collections.defaultdict(dict); F = collections.defaultdict(dict)
for l in open(tape, "rb"):
    if b'"bid": ' not in l[:90]: continue
    i = l.find(b'"ts": '); s = int(l[i + 6:l.index(b",", i)]) // 10**9
    if s < LO - 310 or s > HI + 125: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if bk >= 128: continue
    r = json.loads(l)
    if r.get("bid") and r.get("ask"):
        M[bk][s] = (r["bid"] + r["ask"]) / 2
        if r.get("fund"): F[bk][s] = r["fund"]
def at(d, s):
    for x in range(s, s + 3):
        if x in d: return d[x]
FUND = {"gap", "dF30", "dF60", "dF300"}
rows = []
for bk in M:
    m, f = M[bk], F[bk]; ks = sorted(m); drift = (m[ks[-1]] - m[ks[0]]) / m[ks[0]] * 1e4 / max(1, ks[-1] - ks[0])
    for s in range(LO, HI):
        mid, fv = m.get(s), f.get(s)
        if not mid or not fv: continue
        g = [at(m, s - 10), at(m, s - 50), at(m, s - 300), at(f, s - 30), at(f, s - 60), at(f, s - 300), at(m, s + 60), at(m, s + 120)]
        if None in g: continue
        m10, m50, m300, f30, f60, f300, a60, a120 = g
        x = {"gap": (fv - mid) / mid * 1e4, "dF30": (fv - f30) / mid * 1e4, "dF60": (fv - f60) / mid * 1e4, "dF300": (fv - f300) / mid * 1e4,
             "r10": (mid - m10) / mid * 1e4, "r50": (mid - m50) / mid * 1e4, "r300": (mid - m300) / mid * 1e4}
        z = {n: w * (x[n] - mu) / sd for n, w, mu, sd in zip(N, ml["w"], ml["mu"], ml["sd"]) if sd > 0}
        full = sum(z.values()); fund = sum(v for n, v in z.items() if n in FUND); rev = full - fund
        rows.append((bk, s, full, fund, rev, (a60 - mid) / mid * 1e4 - drift * 60, (a120 - mid) / mid * 1e4 - drift * 120))
R = np.array([r[2:] for r in rows]); BK = np.array([r[0] for r in rows]); S = np.array([r[1] for r in rows])
full, fund, rev, d60, d120 = R.T; thr = ml["thr"]
sigA = np.where(full >= 1.5 * thr, 1, np.where(full <= -1.5 * thr, -1, 0))
# A within ±5 s on the same book and side
key = collections.defaultdict(set)
for b, s, a in zip(BK, S, sigA):
    if a: key[(b, a)].add(s)
def near(b, s, sd): return any((s + k) in key[(b, sd)] for k in range(-5, 6))
def report(name, sig):
    act = sig != 0; n = act.sum()
    if not n: print(f"  {name}: never active"); return
    ov = np.array([near(b, s, sd) for b, s, sd in zip(BK[act], S[act], sig[act])])
    e60 = sig[act] * d60[act]; e120 = sig[act] * d120[act]
    print(f"  {name:34s}: active {act.mean():5.1%} | overlap with A {ov.mean():5.1%} | edge all +60 {e60.mean():+.2f} / +120 {e120.mean():+.2f} | B-only +60 {e60[~ov].mean():+.2f} / +120 {e120[~ov].mean():+.2f} bp")
print(f"sim {LO}-{HI}: book-seconds {len(rows)}")
report("A live (full ≥ 1.5 thr)", sigA)
band = np.where((full >= thr) & (full < 1.5 * thr), 1, np.where((full <= -thr) & (full > -1.5 * thr), -1, 0)); report("B1 band 1.0–1.5 thr", band)
for name, v in (("B2 fundamental part (top 12%)", fund), ("B3 reversion part (top 12%)", rev)):
    t = np.percentile(np.abs(v), 88); report(name, np.where(v >= t, 1, np.where(v <= -t, -1, 0)))
