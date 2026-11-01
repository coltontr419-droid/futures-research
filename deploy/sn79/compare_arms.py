"""Per-book A/B readout (decisions.md §1207): our maker fills grouped by arm (book_id mod N_ARMS; arm 0 = base), all in the same window, so
market-regime shifts cancel. Per arm: fills, 30 s markout, difference vs arm 0 with a book-clustered standard error, share of fills swept
within 1 s, bot-taken share; the field's markout on the same books as a check that the arms' books are comparable.

    python compare_arms.py <tape.jsonl> <our uid> <n arms incl. base> [labels comma-separated]
"""
import bisect
import json
import sys
from collections import defaultdict

import numpy as np

tape, me, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
labels = sys.argv[4].split(",") if len(sys.argv) > 4 else [f"arm {k}" for k in range(n)]
best, fills = defaultdict(list), []
for line in open(tape):
    r = json.loads(line)
    if "p" in r and r.get("Ma") is not None and r["Ma"] >= 0:
        fills.append(r)
    elif r.get("bid") and r.get("ask"):
        best[r["book"]].append((r["ts"] / 1e9, r["bid"], r["ask"]))
ours, field = defaultdict(list), defaultdict(list)
for t in fills:
    bl = best[t["book"]]; k = bisect.bisect_left(bl, (t["ts"] / 1e9 + 30,)); i = bisect.bisect_left(bl, (t["ts"] / 1e9 + 1,))
    if k >= len(bl):
        continue
    maker = 1 if t["s"] == 1 else -1
    mo = maker * ((bl[k][1] + bl[k][2]) / 2 - t["p"]) / 0.01
    after = bl[i][1] if maker == 1 else bl[i][2]
    swept = after < t["p"] - 1e-9 if maker == 1 else after > t["p"] + 1e-9
    (ours if t["Ma"] == me else field)[t["book"] % n].append((t["book"], mo, swept, t["Ta"] is not None and t["Ta"] >= 0))


def stats(rows):
    mo = np.array([r[1] for r in rows]); by = defaultdict(list)
    for r in rows:
        by[r[0]].append(r[1])
    sums = np.array([sum(v) for v in by.values()]); ns = np.array([len(v) for v in by.values()])
    se = np.sqrt(np.sum((sums - ns * mo.mean()) ** 2)) / ns.sum()
    return mo.mean(), se


span = [t["ts"] for t in fills if t["Ma"] == me]
print(f"{tape}: our fills {sum(len(v) for v in ours.values())}, sim span {(max(span) - min(span)) / 6e10:.0f} min" if span else "no fills")
m0, s0 = stats(ours[0]) if ours[0] else (float("nan"), float("nan"))
for k in range(n):
    R = ours[k]
    if not R:
        print(f"  {labels[k]:28}: no fills"); continue
    m, s = stats(R); fm, _ = stats(field[k]) if field[k] else (float("nan"), 0)
    d = "" if k == 0 else f" | vs base {m - m0:+.2f} ± {np.hypot(s, s0):.2f}"
    print(f"  {labels[k]:28}: fills {len(R):5d}  markout {m:+.2f} ± {s:.2f}{d} | swept {np.mean([r[2] for r in R]):.0%} | "
          f"bot-taken {np.mean([r[3] for r in R]):.0%} | field on these books {fm:+.2f}")
