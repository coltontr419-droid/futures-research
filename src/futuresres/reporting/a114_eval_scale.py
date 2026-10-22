"""A114 (decisions.md 828): evaluation-stage bracket scaling under V2 (funded stop 0.7x as deployed), paired vs the policy. No trial.

    python -m futuresres.reporting.a114_eval_scale
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
        base_F = dict(Fp, fee=116.0, payout=V2, fscale=(1.0, 0.7)); base = f.simulate(cp, P, 84, MIX, base_F)["net"]
        for es in ((1.0, 0.85), (1.0, 0.7), (1.15, 1.0), (0.85, 1.0)):
            d = f.simulate(cp, P, 84, MIX, dict(base_F, escale=es))["net"] - base; m, lo, hi = ci(d)
            print(f"{'2021-26' if era == 'post' else '2010-20'} eval take x{es[0]:.2f} stop x{es[1]:.2f} minus policy: mean {m:+,.0f}, 90% CI {lo:+,.0f} .. {hi:+,.0f}; "
                  f"windows better {np.mean(d > 0):.0%}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
