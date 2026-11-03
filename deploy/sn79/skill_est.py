"""MVTRX skill estimate for one period (§1211 add. 15): per book, alpha = MTM P&L − mean inventory × drift, from our maker AND taker fills
in the last LAST sim minutes of the tape (the starting inventory cancels out of alpha); the validator's kappa_of_alpha over books.
    python skill_est.py <tape> <uid> <last sim min> [skip_file]"""
import json, sys
from collections import defaultdict
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_of_alpha
tape, me, last = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
skip = set(map(int, open(sys.argv[4]).read().split())) if len(sys.argv) > 4 else set()
rows, seen, tmax = [], set(), 0
for line in open(tape):
    if '"p":' not in line: continue
    r = json.loads(line); k = (r["book"], r.get("id"), r["ts"])
    if k in seen: continue
    seen.add(k); rows.append(r); tmax = max(tmax, r["ts"])
t0 = tmax - last * 6e10
inv, cash, isum, n, pf, pl = tuple(defaultdict(float) for _ in range(4)) + ({}, {})
for r in sorted((r for r in rows if r["ts"] >= t0), key=lambda r: r["ts"]):
    b = r["book"]; pf.setdefault(b, r["p"]); pl[b] = r["p"]
    d = 0.0
    if r.get("Ma") == me: d += r["q"] if r["s"] == 1 else -r["q"]          # maker: s == 1 → we bought
    if r.get("Ta") == me: d += r["q"] if r["s"] == 0 else -r["q"]          # taker: s == 0 → we bought
    inv[b] += d; cash[b] -= d * r["p"]
    isum[b] += inv[b]; n[b] += 1
alpha = {}
for b in n:
    if inv[b] == 0 and cash[b] == 0 and isum[b] == 0: continue
    pnl = cash[b] + inv[b] * pl[b]; mi = isum[b] / n[b]
    alpha[b] = pnl - mi * (pl[b] - pf[b])
calm = {b: a for b, a in alpha.items() if b not in skip}; sk = {b: a for b, a in alpha.items() if b in skip}
f = lambda d: f"books {len(d):3d} | Σα {sum(d.values()):9.1f} | positive {sum(a > 0 for a in d.values()):3d} | kappa {kappa_of_alpha(list(d.values())):+.3f}"
print(f"last {last:.0f} sim min | calm (quoted): {f(calm)}")
print(f"                | skipped (unwind): {f(sk)}")
print(f"                | all: {f(alpha)}")
