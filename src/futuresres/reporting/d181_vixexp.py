"""D-series family 181 (decisions.md §1140): VIX settlement Wednesdays (and the day after) in ES / NQ, long and short.

    python -m futuresres.reporting.d181_vixexp [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12

ROOT = Path(__file__).resolve().parents[3]
DISC = (dt.date(2010, 3, 1), dt.date(2022, 12, 31)); VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))


def third_friday(y, m):
    d = dt.date(y, m, 1); d += dt.timedelta(days=(4 - d.weekday()) % 7); return d + dt.timedelta(days=14)


def expiries(days):
    out, ds = [], set(days)
    for y in range(2010, 2027):
        for m in range(1, 13):
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            e = third_friday(ny, nm) - dt.timedelta(days=30)
            while e not in ds and e > dt.date(2009, 12, 1):
                e -= dt.timedelta(days=1)
            out.append(e)
    return sorted(set(out))


def cell(S, tgt, which, side, lo, hi, E=None):
    days = sorted(S[tgt]); E = E if E is not None else expiries(days); idx = {d: i for i, d in enumerate(days)}
    ev = [days[idx[e] + which] for e in E if e in idx and idx[e] + which < len(days) and lo <= days[idx[e] + which] <= hi]
    evs = set(ev); rest = np.array([S[tgt][d] for d in days if lo <= d <= hi and d not in evs])
    y = np.array([S[tgt][d] for d in ev]); k = d12.COST[tgt]
    return side * (y - rest.mean()), side * y - k, (side - 1) * y - (k if side < 0 else 0.0)


def t(x):
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def main(validate: bool) -> None:
    S = d10.series(); out = {"cells": []}
    for tgt in ("ES", "NQ"):
        for which, wn in ((0, "expiry_day"), (1, "next_day")):
            for side, sn in ((1, "long"), (-1, "short")):
                ex, net, _ = cell(S, tgt, which, side, *DISC)
                r = {"target": tgt, "day": wn, "side": sn, "n": len(ex), "excess_bps": round(float(ex.mean()), 2), "t": round(t(ex), 2), "net_bps": round(float(net.mean()), 2)}
                out["cells"].append(r); print("discovery", r)
                if validate and r["excess_bps"] > 0 and r["t"] > 1.96:
                    ex, net, al = cell(S, tgt, which, side, *VAL); rng = np.random.default_rng(1140); days = sorted(S[tgt])
                    weds = [d for d in days if d.weekday() == 2]; m = net.mean(); sh = []
                    for _ in range(2000):
                        fake = sorted(rng.choice(len(weds), len(ex), replace=False)); sh.append(cell(S, tgt, which, side, *VAL, E=[weds[i] for i in fake])[1].mean())
                    pct = float((np.array(sh) < m).mean() * 100)
                    v = "CONFIRM" if t(net) > 1.645 and t(al) > 1.645 and pct >= 95 else ("WATCHLIST" if m > 0 else "REJECT")
                    r.update(sealed_n=len(net), sealed_net=round(float(m), 2), sealed_t=round(t(net), 2), vs_long_t=round(t(al), 2), placebo=pct, decision=v); print("sealed", r)
    (ROOT / "reports" / f"d181_{'sealed' if validate else 'discovery'}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] == ["validate"])
