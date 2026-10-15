"""A43 - bracket scaling for the accounts that trade a rule (decisions.md 530). No trial.

    python -m futuresres.reporting.a43_scale
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.a35_nkddollar as a35
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
F = (0.5, 0.75, 1.0, 1.5, 2.0)


def masks():
    return {"NKD": (lambda P: (lambda v: P.get(d3.prev_weekday(v), 0.0) < 0))(a35.weak_dollar_week("6E=F")),
            "FDXM": (lambda P: (lambda v: P.get(d3.prev_weekday(v), 0.0) < 0))(d111.predictor("DX-Y.NYB"))}


def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; out = {}
    for mkt, rule in masks().items():
        n, rt = a23.MARKETS[mkt]
        (h, l, c), d = a23.market_paths(mkt, "post"); dd = [x.astype(object) for x in d]
        pp = a27.flip(h, l, c, np.array([rule(v) for v in dd]))
        st = np.array(dd[: len(dd) - 84]); m24 = st < dt.date(2025, 1, 1); m25 = ~m24
        grid = {}
        for kw, kl in itertools.product(F, F):
            r = a23.replay(s, pp, n, rt, scale=(kw, kl))
            grid[(kw, kl)] = {"d24": float(r["net"][m24].mean()), "d25": float(r["net"][m25].mean()), "p24": float((r["first"][m24] > 0).mean()), "p25": float((r["first"][m25] > 0).mean())}
        best = max(grid, key=lambda k: grid[k]["d24"])
        (hp, lp, cp), dp = a23.market_paths(mkt, "pre"); ddp = [x.astype(object) for x in dp]
        ppp = a27.flip(hp, lp, cp, np.array([rule(v) for v in ddp]))
        pre = {k: float(a23.replay(s, ppp, n, rt, scale=k)["net"].mean()) for k in ((1.0, 1.0), best)}
        out[mkt] = {"grid": {f"{k[0]}x{k[1]}": v for k, v in grid.items()}, "chosen": list(best), "pre_2021_mean_net": {f"{k[0]}x{k[1]}": v for k, v in pre.items()}}
        for k in sorted(grid, key=lambda k: -grid[k]["d24"])[:5] + [(1.0, 1.0)]:
            g = grid[k]
            print(f"{mkt} take x{k[0]:<4} stop x{k[1]:<4}: 2021-24 starts {g['d24']:+7,.0f} ({g['p24']:.0%}) | 2025 starts {g['d25']:+7,.0f} ({g['p25']:.0%})", flush=True)
        print(f"{mkt} chosen {best}: 2010-20 mean {pre[best]:+7,.0f} vs base {pre[(1.0, 1.0)]:+7,.0f}", flush=True)
    (ROOT / "reports" / "a43_scale.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
