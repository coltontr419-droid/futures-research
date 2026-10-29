"""D-series family 182 (decisions.md §1142): the session and the week after monthly SPX options expiration in ES / NQ, long and short.

    python -m futuresres.reporting.d182_postopex [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12
from futuresres.reporting.d181_vixexp import DISC, VAL, t, third_friday

ROOT = Path(__file__).resolve().parents[3]


def opex(days):
    ds = set(days); out = []
    for y in range(2010, 2027):
        for m in range(1, 13):
            e = third_friday(y, m)
            while e not in ds and e > dt.date(2009, 12, 1):
                e -= dt.timedelta(days=1)
            out.append(e)
    return sorted(set(out))


def cell(S, tgt, h, side, lo, hi, E=None):
    days = sorted(S[tgt]); E = E if E is not None else opex(days); idx = {d: i for i, d in enumerate(days)}; r = np.array([S[tgt][d] for d in days])
    ev, used = [], set()
    for e in E:
        i = idx.get(e)
        if i is None or i + h >= len(days) or not (lo <= days[i + 1] <= hi and days[i + h] <= hi):
            continue
        ev.append(r[i + 1:i + 1 + h].sum()); used.update(range(i + 1, i + 1 + h))
    rest = [r[j:j + h].sum() for j in range(0, len(days) - h, h) if lo <= days[j] <= hi and not used.intersection(range(j, j + h))]
    y = np.array(ev); k = d12.COST[tgt] * h
    return side * (y - np.mean(rest)), side * y - k, (side - 1) * y - (k if side < 0 else 0.0)


def main(validate: bool) -> None:
    S = d10.series(); out = {"cells": []}
    for tgt in ("ES", "NQ"):
        for h in (1, 5):
            for side, sn in ((1, "long"), (-1, "short")):
                ex, net, _ = cell(S, tgt, h, side, *DISC)
                r = {"target": tgt, "sessions": h, "side": sn, "n": len(ex), "excess_bps": round(float(ex.mean()), 2), "t": round(t(ex), 2), "net_bps": round(float(net.mean()), 2)}
                out["cells"].append(r); print("discovery", r)
                if validate and r["excess_bps"] > 0 and r["t"] > 1.96:
                    ex, net, al = cell(S, tgt, h, side, *VAL); rng = np.random.default_rng(1142); fr = [d for d in sorted(S[tgt]) if d.weekday() == 4]; m = net.mean()
                    sh = [cell(S, tgt, h, side, *VAL, E=[fr[i] for i in sorted(rng.choice(len(fr), len(net), replace=False))])[1].mean() for _ in range(2000)]
                    pct = float((np.array(sh) < m).mean() * 100)
                    v = "CONFIRM" if t(net) > 1.645 and t(al) > 1.645 and pct >= 95 else ("WATCHLIST" if m > 0 else "REJECT")
                    r.update(sealed_n=len(net), sealed_net=round(float(m), 2), sealed_t=round(t(net), 2), vs_long_t=round(t(al), 2), placebo=pct, decision=v); print("sealed", r)
    (ROOT / "reports" / f"d182_{'sealed' if validate else 'discovery'}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] == ["validate"])
