"""L-family 15 (decisions.md 954): large-cap one-day crashes >= 8% — buy the close, hold 5 / 20 sessions vs the top-200 equal weight.

    python -m futuresres.stocks.l15_crash [validate]
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL = 0.001, 0.02, "2023-01-01"


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); A = z["A"].astype(np.float64); V = z["V"].astype(np.float64)
    T = len(cal); last = {}; res = {5: collections.defaultdict(list), 20: collections.defaultdict(list)}
    for i in range(260, T - 21):
        if (cal[i] >= SEAL) != validate:
            continue
        dv = np.nanmedian(V[:, i - 63:i], axis=1); ok = np.isfinite(dv) & np.isfinite(A[:, i]) & np.isfinite(A[:, i - 1]) & (A[:, i] >= 5)
        if ok.sum() < 300:
            continue
        top = np.argsort(np.where(ok, dv, -1))[::-1][:200]
        r1 = A[top, i] / A[top, i - 1] - 1
        for k in np.where(r1 <= -0.08)[0]:
            j = top[k]
            if i - last.get(j, -99) < 20:
                continue
            last[j] = i
            for h in (5, 20):
                if not np.isfinite(A[j, i + h]):
                    continue
                f = A[top, i + h] / A[top, i] - 1; ew = float(np.nanmean(f))
                res[h][cal[i]].append(A[j, i + h] / A[j, i] - 1 - COST - ew)
    for h in (5, 20):
        dm = np.array([np.mean(v) for v in res[h].values()]); x = np.array([y for v in res[h].values() for y in v])
        if len(dm) < 5:
            continue
        m, t = float(x.mean()), float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))))
        line = f"L15 {'sealed' if validate else 'discovery'} hold {h}: n {len(x)} days {len(dm)}, excess {m*100:+.2f}%, median {np.median(x)*100:+.2f}%, t {t:+.2f}"
        if h == 5:
            if validate:
                rng = np.random.default_rng(954); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
                post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
                line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
            else:
                line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
