"""SN79: does size cost quality? (§1211 MVTRX prep). Per maker on a tape: maker fills, volume, median fill size, share taken by another miner,
joined with making_exact's per-maker C / R / quality / credit (/tmp/making_exact_field.json from the same tape). Prints size-bucket medians
and rank correlations, and where our uid sits.

    python maker_profile.py <tape.jsonl> <field.json> <our uid>
"""
import json
import sys
from collections import defaultdict

import numpy as np

tape, fj, me = sys.argv[1], sys.argv[2], int(sys.argv[3])
fills, seen = defaultdict(list), set()
for line in open(tape):
    if '"Ma"' not in line:
        continue
    r = json.loads(line)
    k = (r["book"], r.get("id"), r["ts"])
    if k in seen or r.get("Ma") is None or r["Ma"] < 0:
        continue
    seen.add(k); fills[r["Ma"]].append((r["q"], r.get("Ta") is not None and r["Ta"] >= 0))
field = {int(u): v for u, v in json.load(open(fj)).items()}
rows = []
for u, f in fills.items():
    q = np.array([x[0] for x in f]); bot = np.mean([x[1] for x in f])
    v = field.get(u)
    if v is None and u != me:
        continue
    rows.append((u, len(f), q.sum(), np.median(q), bot, (v or {}).get("q", np.nan), (v or {}).get("C", np.nan), (v or {}).get("credit", np.nan)))
A = np.array([r[1:] for r in rows if r[0] != me], dtype=float)
rk = lambda x: np.argsort(np.argsort(x))
def sp(a, b):
    m = ~(np.isnan(a) | np.isnan(b)); return float(np.corrcoef(rk(a[m]), rk(b[m]))[0, 1])
print(f"makers {len(A)} | spearman vs quality: volume {sp(A[:, 1], A[:, 4]):+.2f}, median fill size {sp(A[:, 2], A[:, 4]):+.2f}, "
      f"bot-taken share {sp(A[:, 3], A[:, 4]):+.2f} | vs credit: volume {sp(A[:, 1], A[:, 6]):+.2f}, fill size {sp(A[:, 2], A[:, 6]):+.2f}")
edges = np.quantile(A[:, 2], [0, .25, .5, .75, .9, 1])
print("median fill size bucket        makers  fills  volume  bot%   quality  captured C  credit")
for lo, hi in zip(edges[:-1], edges[1:]):
    s = A[(A[:, 2] >= lo) & (A[:, 2] <= hi)]
    print(f"  {lo:7.2f} - {hi:7.2f}            {len(s):4d}  {np.median(s[:, 0]):6.0f} {np.median(s[:, 1]):7.0f} {100 * np.median(s[:, 3]):4.0f}%   "
          f"{np.nanmedian(s[:, 4]):.3f}   {np.nanmedian(s[:, 5]):8.1f}  {np.nanmedian(s[:, 6]):7.1f}")
top = sorted([r for r in rows if r[0] != me], key=lambda r: -np.nan_to_num(r[7]))[:8]
print("top credit makers: uid fills volume medsize bot% quality C credit")
for r in top + [r for r in rows if r[0] == me]:
    print(f"  {'OURS ' if r[0] == me else ''}{r[0]:4d} {r[1]:6d} {r[2]:8.0f} {r[3]:6.2f} {100 * r[4]:4.0f}% {r[5]:.3f} {r[6]:8.1f} {r[7]:7.1f}")
