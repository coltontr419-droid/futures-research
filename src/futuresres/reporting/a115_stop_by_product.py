"""A115 (decisions.md 829): funded stop factor per product under V2, paired vs the deployed 0.7x for both. No trial.

    python -m futuresres.reporting.a115_stop_by_product
"""

from __future__ import annotations

import warnings

import numpy as np

import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX
from futuresres.reporting.a111_stop_ci import V2, ci


def main() -> int:
    warnings.filterwarnings("ignore")
    for era in ("post", "pre"):
        cp, Pp = data(era); Fp, P = setup("50K", launch_paths(Pp)); Fp.update(LIVE)
        F0 = dict(Fp, fee=116.0, payout=V2)
        base = f.simulate(cp, P, 84, MIX, dict(F0, fscale_by={"NKD": 0.7, "FDXM": 0.7}))["net"]
        for k in ({"NKD": 0.7, "FDXM": 1.0}, {"NKD": 1.0, "FDXM": 0.7}, {"NKD": 0.6, "FDXM": 0.8}, {"NKD": 0.8, "FDXM": 0.6}):
            d = f.simulate(cp, P, 84, MIX, dict(F0, fscale_by=k))["net"] - base; m, lo, hi = ci(d)
            print(f"{'2021-26' if era == 'post' else '2010-20'} NKD x{k['NKD']} FDXM x{k['FDXM']} minus both 0.7: mean {m:+,.0f}, 90% CI {lo:+,.0f} .. {hi:+,.0f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
