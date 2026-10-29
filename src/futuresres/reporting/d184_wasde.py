"""D-series family 184 (decisions.md §1149): WASDE release days in ZC, ZS, ZW, long and short.

    python -m futuresres.reporting.d184_wasde [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
from futuresres.reporting.d181_vixexp import DISC, VAL, cell, t

ROOT = Path(__file__).resolve().parents[3]


def main(validate: bool) -> None:
    S = d10.series(); out = {"cells": []}
    W = [dt.date.fromisoformat(x) for x in (ROOT / "data" / "wasde" / "dates.txt").read_text().split()]
    for tgt in ("ZC", "ZS", "ZW"):
        E = [d for d in W if d in S[tgt]]
        for side, sn in ((1, "long"), (-1, "short")):
            ex, net, _ = cell(S, tgt, 0, side, *DISC, E=E)
            r = {"target": tgt, "side": sn, "n": len(ex), "excess_bps": round(float(ex.mean()), 2), "t": round(t(ex), 2), "net_bps": round(float(net.mean()), 2)}
            out["cells"].append(r); print("discovery", r)
            if validate and r["excess_bps"] > 0 and r["t"] > 1.96:
                ex, net, al = cell(S, tgt, 0, side, *VAL, E=E); rng = np.random.default_rng(1149); w = sorted(S[tgt]); m = net.mean()
                sh = [cell(S, tgt, 0, side, *VAL, E=[w[i] for i in sorted(rng.choice(len(w), len(net), replace=False))])[1].mean() for _ in range(2000)]
                pct = float((np.array(sh) < m).mean() * 100)
                v = "CONFIRM" if t(net) > 1.645 and t(al) > 1.645 and pct >= 95 else ("WATCHLIST" if m > 0 else "REJECT")
                r.update(sealed_n=len(net), sealed_net=round(float(m), 2), sealed_t=round(t(net), 2), vs_long_t=round(t(al), 2), placebo=pct, decision=v); print("sealed", r)
    (ROOT / "reports" / f"d184_{'sealed' if validate else 'discovery'}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] == ["validate"])
