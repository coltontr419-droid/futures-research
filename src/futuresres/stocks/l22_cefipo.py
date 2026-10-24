"""L-family 22 (decisions.md 1008): short new CEFs from session 2 to session 120, vs the CEF universe, after cost and borrow.

    python -m futuresres.stocks.l22_cefipo [validate]
"""

from __future__ import annotations

import collections
import json
import sys

import numpy as np

from futuresres.stocks.l18_cef import OUT as CEF, series, yahoo

COST, BORROW, PRIOR_SD, SEAL = 0.004, 0.015, 0.02, "2021-01"


def main(validate: bool, ipo_only: bool = False) -> None:
    funds = json.loads((CEF / "funds.json").read_text()); A = {}
    for s in funds:
        r = yahoo(s)
        if r:
            A[s] = series(r, "adj")
    days = sorted({d for s in A for d in A[s]}); ix = {d: i for i, d in enumerate(days)}
    res, n = collections.defaultdict(list), 0
    for s, a in A.items():
        ds = sorted(a)
        if len(ds) < 125 or ds[0] < "2013-03" or ds[0] > "2026-03-31" or (ds[0][:7] >= SEAL) != validate:
            continue
        if ipo_only:                                             # §1009 information cut: first close within 2% of a standard IPO price
            c0 = next((c for c in yahoo(s)["indicators"]["quote"][0]["close"] if c), None)
            if not c0 or not any(abs(c0 / p_ - 1) <= 0.02 for p_ in (10, 15, 20, 25)):
                continue
        d0, d1 = ds[1], ds[119]
        u = [A[t][d1] / A[t][d0] - 1 for t in A if t != s and d0 in A[t] and d1 in A[t] and sorted(A[t])[0] < d0]
        if len(u) < 30:
            continue
        res[ds[0][:7]].append(-(a[d1] / a[d0] - 1 - float(np.mean(u))) - COST - BORROW); n += 1
    x = np.array([np.mean(v) for _, v in sorted(res.items())])
    if len(x) < 6:
        print(f"L22: funds {n}, months {len(x)} — too few"); return
    m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    s_ = f"L22{' IPO-only' if ipo_only else ''} {'sealed' if validate else 'discovery'}: new funds {n}, months {len(x)}, short excess {m*100:+.2f}% per 118 sessions, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(1008); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        s_ += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        s_ += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(s_)


if __name__ == "__main__":
    main("validate" in sys.argv[1:], "ipo" in sys.argv[1:])
