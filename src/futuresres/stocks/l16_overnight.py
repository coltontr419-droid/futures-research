"""L-family 16 (decisions.md 981): overnight-return momentum — top 20 by last-21-session overnight log return, held a month.

    python -m futuresres.stocks.l16_overnight [validate]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL, K = 0.002, 0.02, "2023-01", 20


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); A = z["A"].astype(np.float64); O = z["O"].astype(np.float64)
    me = [i for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7]]; res = []
    for i0, i1 in zip(me[:-1], me[1:]):
        if (cal[i1][:7] >= SEAL) != validate or i0 < 260:
            continue
        a0, a1 = A[:, i0], A[:, i1]; W = A[:, i0 - 252:i0 + 1]
        ok = np.isfinite(a0) & np.isfinite(a1) & (a0 >= 5) & (np.isnan(W).mean(axis=1) <= 0.05)
        with np.errstate(all="ignore"):
            sc = np.nansum(np.log(O[:, i0 - 20:i0 + 1] / A[:, i0 - 21:i0]), axis=1)
        ok &= np.isfinite(sc) & (np.isfinite(O[:, i0 - 20:i0 + 1]).sum(axis=1) >= 18)
        if ok.sum() < 200:
            continue
        fwd = a1 / a0 - 1; v = np.where(ok, sc, -np.inf); top = np.argsort(v)[::-1][:K]
        res.append(float(np.nanmean(fwd[top])) - COST - float(np.nanmean(fwd[ok])))
    x = np.array(res); m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    line = f"L16 {'sealed' if validate else 'discovery'}: months {len(x)}, excess {m*100:+.2f}%/month, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(981); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
