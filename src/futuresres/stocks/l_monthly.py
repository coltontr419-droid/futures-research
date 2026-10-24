"""L-families 1-4 (decisions.md 942): monthly cross-sectional rules on liquid US stocks, 2015-2026, vs the equal-weight universe.

    python -m futuresres.stocks.l_monthly [validate]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
LONG = ROOT / "data" / "stocks" / "long" / "daily.jsonl"
COST, PRIOR_SD, SEAL, K = 0.002, 0.02, "2023-01", 20


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); A = z["A"].astype(np.float64)
    month_ends = [i for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7]]
    res = {k: [] for k in ("L1", "L2", "L3", "L4")}
    for i0, i1 in zip(month_ends[:-1], month_ends[1:]):
        if (cal[i1][:7] >= SEAL) != validate or i0 < 260:
            continue
        a0, a1 = A[:, i0], A[:, i1]; W = A[:, i0 - 252:i0 + 1]
        ok = np.isfinite(a0) & np.isfinite(a1) & (a0 >= 5) & (np.isnan(W).mean(axis=1) <= 0.05) & np.isfinite(A[:, i0 - 252]) & np.isfinite(A[:, i0 - 21])
        if ok.sum() < 200:
            continue
        fwd = a1 / a0 - 1; ew = float(np.nanmean(fwd[ok]))
        with np.errstate(all="ignore"):
            R = np.diff(np.log(A[:, i0 - 63:i0 + 1]), axis=1)
            sc = {"L1": a0 / np.nanmax(W, axis=1), "L2": A[:, i0 - 21] / A[:, i0 - 252] - 1, "L3": -(a0 / A[:, i0 - 21] - 1), "L4": -np.nanstd(R, axis=1)}
        for k in res:
            v = np.where(ok & np.isfinite(sc[k]), sc[k], -np.inf); top = np.argsort(v)[::-1][:K]
            res[k].append(float(np.nanmean(fwd[top])) - COST - ew)
    print(f"L monthly {'sealed' if validate else 'discovery'}")
    for k, v in res.items():
        x = np.array(v)
        if len(x) < 6:
            continue
        m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
        line = f"  {k}: months {len(x)}, excess {m*100:+.2f}%/month, t {t:+.2f}"
        if validate:
            rng = np.random.default_rng(942); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
            post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
            line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
        else:
            line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
