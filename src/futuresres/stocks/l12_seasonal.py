"""L-family 12 (decisions.md 948): same-calendar-month seasonality — top 20 by average return in month m over the prior 5 years.

    python -m futuresres.stocks.l12_seasonal [validate]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL, K = 0.002, 0.02, "2023-01", 20


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); A = z["A"].astype(np.float64)
    me = [i for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7]]
    mret = {}                                                  # 'YYYY-MM' -> vector of that month's return (end of prior month -> end of month)
    for i0, i1 in zip(me[:-1], me[1:]):
        mret[cal[i1][:7]] = A[:, i1] / A[:, i0] - 1
    res = []
    for i0, i1 in zip(me[:-1], me[1:]):
        hold = cal[i1][:7]
        if hold < "2020-01" or (hold >= SEAL) != validate:
            continue
        y, m = int(hold[:4]), hold[5:]
        past = [mret.get(f"{y - k}-{m}") for k in range(1, 6)]
        if any(p is None for p in past):
            continue
        P = np.vstack(past); sc = np.where(np.isfinite(P).all(axis=0), P.mean(axis=0), np.nan)
        fwd = mret[hold]; ok = np.isfinite(fwd) & np.isfinite(sc) & (A[:, i0] >= 5)
        if ok.sum() < 200:
            continue
        top = np.argsort(np.where(ok, sc, -np.inf))[::-1][:K]
        res.append(float(np.mean(fwd[top])) - COST - float(np.mean(fwd[ok])))
    x = np.array(res); mu, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    line = f"L12 {'sealed' if validate else 'discovery'}: months {len(x)}, excess {mu*100:+.2f}%/month, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(948); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < mu).mean() * 100)
        post = mu * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and mu > 0 and post > 0 else ("WATCHLIST" if mu > 0 else "REJECT"))
    else:
        line += "  CARRIED" if mu > 0 and t > 1.96 else "  not carried"
    print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
