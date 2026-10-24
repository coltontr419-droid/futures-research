"""L-family 20 (decisions.md 995): CEF ex-distribution day — close before ex-date to ex-date close, vs the CEF universe.

    python -m futuresres.stocks.l20_cefexdiv [validate]
"""

from __future__ import annotations

import collections
import json
import sys

import numpy as np

from futuresres.stocks.l18_cef import OUT as CEF, series, yahoo

COST, PRIOR_SD, SEAL = 0.003, 0.02, "2022-01"


def main(validate: bool) -> None:
    funds = json.loads((CEF / "funds.json").read_text()); A, C = {}, {}
    for s in funds:
        r = yahoo(s)
        if r:
            A[s], C[s] = series(r, "adj"), series(r, "close")
    days = sorted({d for s in A for d in A[s]}); ix = {d: i for i, d in enumerate(days)}
    uni = {}
    for i in range(1, len(days)):
        d0, d1 = days[i - 1], days[i]
        v = [A[s][d1] / A[s][d0] - 1 for s in A if d0 in A[s] and d1 in A[s]]
        if len(v) >= 30:
            uni[d1] = float(np.mean(v))
    res = collections.defaultdict(list)
    for s in A:
        ds = [d for d in sorted(A[s]) if d in C[s] and C[s][d] > 0]
        for a, b in zip(ds[:-1], ds[1:]):
            if ix[b] - ix[a] != 1 or b not in uni or not ("2013-01" <= b[:7] <= "2026-09") or (b[:7] >= SEAL) != validate:
                continue
            ra, rb = A[s][a] / C[s][a], A[s][b] / C[s][b]
            if rb / ra - 1 > 0.002:                              # adjustment factor rises at b relative to a -> b is an ex-date
                res[b[:7]].append(A[s][b] / A[s][a] - 1 - COST - uni[b])
    x = np.array([np.mean(v) for _, v in sorted(res.items())]); n = sum(map(len, res.values()))
    m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    line = f"L20 {'sealed' if validate else 'discovery'}: ex-days {n}, months {len(x)}, excess {m*100:+.3f}%/event, t {t:+.2f}, gross {(m+COST)*100:+.3f}%"
    if validate:
        rng = np.random.default_rng(995); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
