"""D-series family 187 (decisions.md §1156): ZN first notice day (last trading day of Feb/May/Aug/Nov): the 3 sessions before, the day, the day after.

    python -m futuresres.reporting.d187_goldfnd [validate]
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12
from futuresres.reporting.d181_vixexp import DISC, VAL, t

ROOT = Path(__file__).resolve().parents[3]


def fnd(days):
    months = [list(v) for _, v in itertools.groupby(sorted(days), key=lambda d: (d.year, d.month))]
    return [g[-1] for g in months if g[-1].month in (2, 5, 8, 11)]


def cell(S, off, h, side, lo, hi, E=None):
    """Event block = sessions [i+off, i+off+h) around each FND index i; excess vs all other non-overlapping h-blocks."""
    days = sorted(S["ZN"]); r = np.array([S["ZN"][d] for d in days]); idx = {d: i for i, d in enumerate(days)}
    ev, used = [], set()
    for e in (E if E is not None else fnd(days)):
        i = idx.get(e)
        if i is None or i + off < 0 or i + off + h > len(days) or not (lo <= days[i + off] <= hi):
            continue
        ev.append(r[i + off:i + off + h].sum()); used.update(range(i + off, i + off + h))
    rest = [r[j:j + h].sum() for j in range(0, len(days) - h, h) if lo <= days[j] <= hi and not used.intersection(range(j, j + h))]
    y = np.array(ev); k = d12.COST["ZN"] * h
    return side * (y - np.mean(rest)), side * y - k, (side - 1) * y - (k if side < 0 else 0.0)


def main(validate: bool) -> None:
    S = d10.series(); out = {"cells": []}
    for off, h, nm in ((-3, 3, "3_before"), (0, 1, "fnd_day"), (1, 1, "day_after")):
        for side, sn in ((1, "long"), (-1, "short")):
            ex, net, _ = cell(S, off, h, side, *DISC)
            r = {"window": nm, "side": sn, "n": len(ex), "excess_bps": round(float(ex.mean()), 2), "t": round(t(ex), 2), "net_bps": round(float(net.mean()), 2)}
            out["cells"].append(r); print("discovery", r)
            if validate and r["excess_bps"] > 0 and r["t"] > 1.96:
                ex, net, al = cell(S, off, h, side, *VAL); rng = np.random.default_rng(1156); w = sorted(S["ZN"]); m = net.mean()
                sh = [cell(S, off, h, side, *VAL, E=[w[i] for i in sorted(rng.choice(len(w), len(net), replace=False))])[1].mean() for _ in range(2000)]
                pct = float((np.array(sh) < m).mean() * 100)
                v = "CONFIRM" if t(net) > 1.645 and t(al) > 1.645 and pct >= 95 else ("WATCHLIST" if m > 0 else "REJECT")
                r.update(sealed_n=len(net), sealed_net=round(float(m), 2), sealed_t=round(t(net), 2), vs_long_t=round(t(al), 2), placebo=pct, decision=v); print("sealed", r)
    (ROOT / "reports" / f"d187_{'sealed' if validate else 'discovery'}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] == ["validate"])
