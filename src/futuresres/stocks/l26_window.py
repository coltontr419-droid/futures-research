"""L-family 26 (decisions.md 1020): quarter-end window dressing — top-20 YTD winners, 5 sessions into the quarter's last close.

    python -m futuresres.stocks.l26_window [validate]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL, K = 0.002, 0.02, "2023-01", 20


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); A = z["A"].astype(np.float64)
    qe = [i for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7] and cal[i][5:7] in ("03", "06", "09", "12")]
    ye = {cal[i][:4]: i for i in range(len(cal) - 1) if cal[i][:4] != cal[i + 1][:4]}
    res = []
    for i1 in qe:
        i0 = i1 - 5
        if i0 < 260 or (cal[i1][:7] >= SEAL) != validate:
            continue
        b = ye.get(str(int(cal[i1][:4]) - 1)) if cal[i1][5:7] != "03" else i0 - 63
        if b is None:
            continue
        a0, a1, W = A[:, i0], A[:, i1], A[:, i0 - 252:i0 + 1]
        ok = np.isfinite(a0) & np.isfinite(a1) & (a0 >= 5) & (np.isnan(W).mean(axis=1) <= 0.05) & np.isfinite(A[:, b])
        if ok.sum() < 200:
            continue
        sc = np.where(ok, a0 / A[:, b] - 1, -np.inf); top = np.argsort(sc)[::-1][:K]; fwd = a1 / a0 - 1
        res.append(float(np.nanmean(fwd[top])) - COST - float(np.nanmean(fwd[ok])))
    x = np.array(res); m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    line = f"L26 {'sealed' if validate else 'discovery'}: quarters {len(x)}, excess {m*100:+.2f}%/quarter-end, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(1020); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
