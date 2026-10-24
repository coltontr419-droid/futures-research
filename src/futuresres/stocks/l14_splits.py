"""L-family 14 (decisions.md 952): post-forward-split drift — buy the close of the effective session, hold 20 / 60 sessions.

    python -m futuresres.stocks.l14_splits [validate]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL = 0.002, 0.02, "2023-01-01"


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); syms = list(z["syms"]); A = z["A"].astype(np.float64)
    ci = {d: i for i, d in enumerate(cal)}; si = {s: j for j, s in enumerate(syms)}; res = {20: [], 60: []}
    for l in open(ROOT / "data" / "stocks" / "long" / "splits.jsonl"):
        x = json.loads(l); j = si.get(x["sym"])
        if j is None:
            continue
        for d, ratio in x["splits"]:
            if ratio <= 1 or d < "2015-06-01" or (d >= SEAL) != validate:
                continue
            i = next((ci[c] for c in cal[ci.get(d, 0):ci.get(d, 0) + 5] if c >= d), None) if d in ci else next((k for k, c in enumerate(cal) if c >= d), None)
            if i is None:
                continue
            for h in (20, 60):
                if i + h >= len(cal) or not np.isfinite(A[j, i]) or not np.isfinite(A[j, i + h]):
                    continue
                ok = np.isfinite(A[:, i]) & np.isfinite(A[:, i + h]) & (A[:, i] >= 5)
                ew = float(np.mean(A[ok, i + h] / A[ok, i] - 1))
                res[h].append(A[j, i + h] / A[j, i] - 1 - COST - ew)
    for h, v in res.items():
        x = np.array(v)
        if len(x) < 5:
            print(f"L14 hold {h}: n {len(x)}"); continue
        m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
        line = f"L14 {'sealed' if validate else 'discovery'} hold {h}: n {len(x)}, excess {m*100:+.2f}%, median {np.median(x)*100:+.2f}%, t {t:+.2f}"
        if h == 20:
            if validate:
                rng = np.random.default_rng(952); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
                post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
                line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
            else:
                line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
