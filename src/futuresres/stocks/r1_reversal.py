"""R-family 1 (decisions.md 919): weekly reversal in liquid US stocks — buy the week's worst 20 at Monday's open, sell Friday's close.

    python -m futuresres.stocks.r1_reversal [validate]
"""

from __future__ import annotations

import datetime as dt
import sys

import numpy as np

from futuresres.stocks.i1_insider import bars

COST, PRIOR_SD, SEAL = 0.002, 0.02, "2026-01-01"


def main(validate: bool) -> None:
    B = bars(); sd, so, sc, _ = B.pop("__SPY"); si = {d: i for i, d in enumerate(sd)}
    fridays = [d for d in sd if dt.date.fromisoformat(d).weekday() == 4 and d >= "2025-06-06"]
    idx = {s: {d: i for i, d in enumerate(v[0])} for s, v in B.items()}
    out = {20: [], 50: []}
    for f in fridays:
        if (f >= SEAL) != validate:
            continue
        fi = si[f]
        if fi + 5 >= len(sd):
            continue
        mon, nfri = sd[fi + 1], sd[min(fi + 5, len(sd) - 1)]
        if dt.date.fromisoformat(nfri).weekday() != 4:
            nfri = next((sd[j] for j in range(fi + 1, min(fi + 7, len(sd))) if dt.date.fromisoformat(sd[j]).weekday() == 4), None)
            if not nfri:
                continue
        cand = []
        for s, (ds, o, c, v) in B.items():
            ix = idx[s]; i = ix.get(f)
            if i is None or i < 20 or c[i] is None or c[i - 5] is None or c[i] < 5:
                continue
            dv = [c[j] * v[j] for j in range(i - 20, i) if c[j] and v[j]]
            if not dv or float(np.median(dv)) < 5e6:
                continue
            a, b = ix.get(mon), ix.get(nfri)
            if a is None or b is None or not o[a] or not c[b]:
                continue
            cand.append((c[i] / c[i - 5] - 1, c[b] / o[a] - 1))
        cand.sort(reverse="--winners" in sys.argv)            # decisions.md 920: R-family 2 buys the best performers
        spy = sc[si[nfri]] / so[si[mon]] - 1
        for k in (20, 50):
            if len(cand) >= k:
                r = float(np.mean([x[1] for x in cand[:k]])) - COST
                out[k].append((r, r - spy))
    for k, v in out.items():
        a = np.array([x[1] for x in v]); rw = np.array([x[0] for x in v])
        if len(a) < 4:
            continue
        m, t = float(a.mean()), float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a))))
        line = f"{'R2' if '--winners' in sys.argv else 'R1'} {'sealed' if validate else 'discovery'} {'best' if '--winners' in sys.argv else 'worst'} {k}: weeks {len(a)}, raw {rw.mean()*100:+.2f}%/wk, excess {m*100:+.2f}%/wk, t {t:+.2f}"
        if k == 20:
            if validate:
                rng = np.random.default_rng(920 if "--winners" in sys.argv else 919); pct = float((np.array([(a * rng.choice((-1.0, 1.0), len(a))).mean() for _ in range(4000)]) < m).mean() * 100)
                post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + a.var(ddof=1) / len(a))
                line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
            else:
                line += "  CARRIED" if (m > 0 and t > 1.96 and rw.mean() > 0) else "  not carried"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
