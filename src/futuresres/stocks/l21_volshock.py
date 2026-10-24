"""L-family 21 (decisions.md 997): high-volume return premium — top 20 by 5-day dollar-volume shock (flat price), held a month.

    python -m futuresres.stocks.l21_volshock [validate]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL, K = 0.002, 0.02, "2023-01", 20


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); A = z["A"].astype(np.float64); V = z["V"].astype(np.float64)
    me = [i for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7]]; res = []
    for i0, i1 in zip(me[:-1], me[1:]):
        if (cal[i1][:7] >= SEAL) != validate or i0 < 260:
            continue
        a0, a1 = A[:, i0], A[:, i1]; W = A[:, i0 - 252:i0 + 1]
        ok = np.isfinite(a0) & np.isfinite(a1) & (a0 >= 5) & (np.isnan(W).mean(axis=1) <= 0.05)
        with np.errstate(all="ignore"):
            recent = np.nansum(V[:, i0 - 4:i0 + 1], axis=1)
            base = np.nanmean(V[:, i0 - 54:i0 - 4].reshape(V.shape[0], 10, 5).sum(axis=2), axis=1)
            sc = recent / base; r5 = a0 / A[:, i0 - 5] - 1
        ok &= np.isfinite(sc) & (base > 0) & np.isfinite(r5) & (np.abs(r5) <= 0.05)
        if ok.sum() < 200:
            continue
        fwd = a1 / a0 - 1; v = np.where(ok, sc, -np.inf); top = np.argsort(v)[::-1][:K]
        all_ok = np.isfinite(a0) & np.isfinite(a1) & (a0 >= 5) & (np.isnan(W).mean(axis=1) <= 0.05)
        res.append(float(np.nanmean(fwd[top])) - COST - float(np.nanmean(fwd[all_ok])))
    x = np.array(res); m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    line = f"L21 {'sealed' if validate else 'discovery'}: months {len(x)}, excess {m*100:+.2f}%/month, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(997); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
