"""D-series family 185 (decisions.md §1152): COMEX gold options expiry (4th-last trading day of the month) in GC; the 15th (coupon day) in ZN.

    python -m futuresres.reporting.d185_ogcoupon [validate]
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
from futuresres.reporting.d181_vixexp import DISC, VAL, cell, t

ROOT = Path(__file__).resolve().parents[3]


def og(days):
    ds = sorted(days)
    months = [list(v) for _, v in itertools.groupby(ds, key=lambda d: (d.year, d.month))]
    return [g[-4] for g in months if len(g) >= 4]


def coupon(days):
    ds = sorted(days); out = []
    for y in range(2010, 2027):
        for m in range(1, 13):
            x = dt.date(y, m, 15); n = next((d for d in ds if d >= x), None)
            if n is not None and (n - x).days <= 4:
                out.append(n)
    return out


def main(validate: bool) -> None:
    S = d10.series(); out = {"cells": []}
    for tgt, which, E, nm in (("GC", 0, og(S["GC"]), "og_expiry"), ("GC", 1, og(S["GC"]), "og_next"), ("ZN", 0, coupon(S["ZN"]), "coupon_15th")):
        for side, sn in ((1, "long"), (-1, "short")):
            ex, net, _ = cell(S, tgt, which, side, *DISC, E=E)
            r = {"target": tgt, "event": nm, "side": sn, "n": len(ex), "excess_bps": round(float(ex.mean()), 2), "t": round(t(ex), 2), "net_bps": round(float(net.mean()), 2)}
            out["cells"].append(r); print("discovery", r)
            if validate and r["excess_bps"] > 0 and r["t"] > 1.96:
                ex, net, al = cell(S, tgt, which, side, *VAL, E=E); rng = np.random.default_rng(1152); w = sorted(S[tgt]); m = net.mean()
                sh = [cell(S, tgt, which, side, *VAL, E=[w[i] for i in sorted(rng.choice(len(w), len(net), replace=False))])[1].mean() for _ in range(2000)]
                pct = float((np.array(sh) < m).mean() * 100)
                v = "CONFIRM" if t(net) > 1.645 and t(al) > 1.645 and pct >= 95 else ("WATCHLIST" if m > 0 else "REJECT")
                r.update(sealed_n=len(net), sealed_net=round(float(m), 2), sealed_t=round(t(net), 2), vs_long_t=round(t(al), 2), placebo=pct, decision=v); print("sealed", r)
    (ROOT / "reports" / f"d185_{'sealed' if validate else 'discovery'}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] == ["validate"])
