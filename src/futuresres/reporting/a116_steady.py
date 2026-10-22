"""A116 (decisions.md 836): "steady" vs the deployed policy — smaller brackets in BOTH stages to keep accounts alive, paired. No trial.

The user's question (2026-10-21): use the edge as a real prop strategy instead of churning evaluations. NKD cannot trade below one contract,
so the lever is bracket size: (take, stop) x 0.5 and x 0.33 in evaluation and funded (funded stop also keeps the deployed 0.7x). Reports
net, evaluations bought, accounts closed, payouts, P(net > 0), the paired difference (84-session blocks, 90% CI), and the zero-edge value.

    python -m futuresres.reporting.a116_steady
"""

from __future__ import annotations

import warnings

import numpy as np

import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX
from futuresres.reporting.a111_stop_ci import V2, ci

VARIANTS = {"deployed": {}, "steady x0.5": {"escale": (0.5, 0.5), "fscale": (0.5, 0.35)}, "steady x0.33": {"escale": (0.33, 0.33), "fscale": (0.33, 0.23)}}


def main() -> int:
    warnings.filterwarnings("ignore")
    for era in ("post", "pre"):
        cp, Pp = data(era); Fp, P = setup("50K", launch_paths(Pp)); Fp.update(LIVE)
        F0 = dict(Fp, fee=116.0, payout=V2, fscale=(1.0, 0.7)); Z = randomised(P, SEEDS[0])
        for window in (84, 252):
            base = None
            for name, v in VARIANTS.items():
                F = dict(F0, **v); r = f.simulate(cp, P, window, MIX, F); b = summary(r, np.ones(len(r["net"]), bool))
                z = summary(f.simulate(cp, Z, window, MIX, F), np.ones(len(r["net"]), bool))["net_mean"] if window == 252 else float("nan")
                d = "" if base is None else "paired vs deployed {:+,.0f} (CI {:+,.0f} .. {:+,.0f})".format(*ci(r["net"] - base))
                base = r["net"] if base is None else base
                print(f"{'2021-26' if era == 'post' else '2010-20'} {window:3d}s {name:13}: net {b['net_mean']:+8,.0f} P>0 {b['p_pos']:.0%} | evals {b['evals']:.1f}, "
                      f"closed {b['closed_accounts']:.1f}, fees ${b['fees']:,.0f}, paid ${b['paid_sim'] + b['paid_live']:,.0f} | zero edge {z:+,.0f} | {d}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
