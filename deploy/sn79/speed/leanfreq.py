"""Live model ($300 model_lean.json) on the tape: share of book-seconds with |pred| >= k*thr and the mid move over the next 60/120 s in the predicted direction, per k."""
import json, sys, collections
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
ml = json.load(open("/opt/mvtrx/agents/model_lean.json"))
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
K = (1.0, 1.25, 1.5, 1.75, 2.0)
R = {k: [0, 0.0, 0.0] for k in K}; N = 0
def at(d, s):
    for x in range(s, s + 3):
        if x in d: return d[x]
for bk in M:
    m, f = M[bk], F[bk]
    for s in range(LO, HI, 2):
        mid, fv = m.get(s), f.get(s)
        if not mid or not fv: continue
        m10, m50, m300 = at(m, s - 10), at(m, s - 50), at(m, s - 300)
        f30, f60, f300 = at(f, s - 30), at(f, s - 60), at(f, s - 300)
        a60, a120 = at(m, s + 60), at(m, s + 120)
        if None in (m10, m50, m300, f30, f60, f300, a60, a120): continue
        x = {"gap": (fv - mid) / mid * 1e4, "dF30": (fv - f30) / mid * 1e4, "dF60": (fv - f60) / mid * 1e4, "dF300": (fv - f300) / mid * 1e4,
             "r10": (mid - m10) / mid * 1e4, "r50": (mid - m50) / mid * 1e4, "r300": (mid - m300) / mid * 1e4}
        p = sum(w * (x[nm] - mu) / sd for nm, w, mu, sd in zip(ml["names"], ml["w"], ml["mu"], ml["sd"]) if sd > 0)
        N += 1; sg = 1 if p > 0 else -1
        for k in K:
            if abs(p) >= k * ml["thr"]:
                R[k][0] += 1; R[k][1] += sg * (a60 - mid) / mid * 1e4; R[k][2] += sg * (a120 - mid) / mid * 1e4
print(f"book-seconds {N} (sim {LO}-{HI})")
for k in K:
    n, a, b = R[k]
    print(f"  lean {k:4.2f}: active {n / max(N, 1):5.1%} of book-seconds | mid move in the predicted direction +60 s {a / max(n, 1):+.2f} bp, +120 s {b / max(n, 1):+.2f} bp")
