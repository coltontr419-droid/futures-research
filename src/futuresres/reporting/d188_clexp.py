"""D-series family 188 (decisions.md §1158): CL expiry (3 business days before the 25th; 4 if the 25th is not a trading day): the 3 sessions before, the day, the day after.

    python -m futuresres.reporting.d188_clexp [validate]
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
    """CL last trading days (function name kept from the §1154 template)."""
    ds = sorted(days); out = []
    for g in [list(v) for _, v in itertools.groupby(ds, key=lambda d: (d.year, d.month))]:
        before = [d for d in g if d.day < 25]
        k = 3 if any(d.day == 25 for d in g) else 4
        if len(before) >= k:
            out.append(before[-k])
    return out


def cell(S, off, h, side, lo, hi, E=None):
    """Event block = sessions [i+off, i+off+h) around each FND index i; excess vs all other non-overlapping h-blocks."""
    days = sorted(S["CL"]); r = np.array([S["CL"][d] for d in days]); idx = {d: i for i, d in enumerate(days)}
    ev, used = [], set()
    for e in (E if E is not None else fnd(days)):
        i = idx.get(e)
        if i is None or i + off < 0 or i + off + h > len(days) or not (lo <= days[i + off] <= hi):
            continue
        ev.append(r[i + off:i + off + h].sum()); used.update(range(i + off, i + off + h))
    rest = [r[j:j + h].sum() for j in range(0, len(days) - h, h) if lo <= days[j] <= hi and not used.intersection(range(j, j + h))]
    y = np.array(ev); k = d12.COST["CL"] * h
    return side * (y - np.mean(rest)), side * y - k, (side - 1) * y - (k if side < 0 else 0.0)


def main(validate: bool) -> None:
    S = d10.series(); out = {"cells": []}
    for off, h, nm in ((-3, 3, "3_before"), (0, 1, "fnd_day"), (1, 1, "day_after")):
        for side, sn in ((1, "long"), (-1, "short")):
            ex, net, _ = cell(S, off, h, side, *DISC)
            r = {"window": nm, "side": sn, "n": len(ex), "excess_bps": round(float(ex.mean()), 2), "t": round(t(ex), 2), "net_bps": round(float(net.mean()), 2)}
            out["cells"].append(r); print("discovery", r)
            if validate and r["excess_bps"] > 0 and r["t"] > 1.96:
                ex, net, al = cell(S, off, h, side, *VAL); rng = np.random.default_rng(1158); w = sorted(S["CL"]); m = net.mean()
                sh = [cell(S, off, h, side, *VAL, E=[w[i] for i in sorted(rng.choice(len(w), len(net), replace=False))])[1].mean() for _ in range(2000)]
                pct = float((np.array(sh) < m).mean() * 100)
                v = "CONFIRM" if t(net) > 1.645 and t(al) > 1.645 and pct >= 95 else ("WATCHLIST" if m > 0 else "REJECT")
                r.update(sealed_n=len(net), sealed_net=round(float(m), 2), sealed_t=round(t(net), 2), vs_long_t=round(t(al), 2), placebo=pct, decision=v); print("sealed", r)
    (ROOT / "reports" / f"d188_{'sealed' if validate else 'discovery'}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] == ["validate"])
