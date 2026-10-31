"""Tag101 strategy read-out from the hourly earnings log (decisions.md §1190-§1191). Pay is softmax(β=10) of each UID's 24 h mean raw score, so
gap = ln(usd_month / median_usd_month) / 10 is the UID's mean-raw-score gap to the median miner, and its hourly change is
(score of the hour's new answers − score of the answers dropping out 24 h earlier) / 24. Once a UID's window holds only its own answers,
a sustained positive slope means the current strategy scores above the one it replaced.

    python3 tag_readout.py [/opt/tag101/earnings_all.csv] [since, default 2026-10-31T01]
"""

import csv
import math
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/opt/tag101/earnings_all.csv"
since = sys.argv[2] if len(sys.argv) > 2 else "2026-10-31T01"
rows = {}
for r in csv.DictReader(open(path)):
    if r["subnet"] != "Tag101" or r["utc"] < since or float(r["usd_month"]) <= 0:
        continue
    rows.setdefault(r["miner"], []).append((r["utc"], float(r["usd_month"]), math.log(float(r["usd_month"]) / float(r["median_usd_month"])) / 10))
for miner, pts in sorted(rows.items()):
    print(f"== {miner}")
    for i, (t, usd, gap) in enumerate(pts):
        d = "" if i == 0 else f"  Δgap {gap - pts[i - 1][2]:+.4f}"
        print(f"  {t}  ${usd:7.1f}/mo  gap vs median {gap:+.3f}{d}")
    if len(pts) >= 3:
        n = len(pts); xs = range(n); mx = (n - 1) / 2; my = sum(p[2] for p in pts) / n
        slope = sum((x - mx) * (p[2] - my) for x, p in zip(xs, pts)) / sum((x - mx) ** 2 for x in xs)
        print(f"  slope {slope:+.4f} gap/hour → new answers score ≈ {24 * slope:+.2f} vs the ones they replace; pay ×{math.exp(10 * slope):.2f}/hour")
