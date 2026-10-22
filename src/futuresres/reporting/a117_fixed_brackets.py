"""A117 (decisions.md 839): a "consistent trading plan" — one fixed (take, stop) per product in every state — vs the deployed policy. No trial.

Tradeify's Funded Trader Agreement (Oct 2026) §6.5 asks for "a consistent trading plan in terms of size, stops, and targets"; the deployed
policy uses 72 (take, stop) pairs by account state (mostly take $100 / stop $500). Fixed brackets (same dollars for NKD and FDXM, both
stages; no funded 0.7x so the plan is one bracket), V2, $116, live rules, 3 NKD + 2 FDXM, 84-session runs; paired CI vs deployed.

    python -m futuresres.reporting.a117_fixed_brackets
"""

from __future__ import annotations

import itertools
import warnings

import numpy as np

import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX
from futuresres.reporting.a111_stop_ci import V2, ci

GRID = list(itertools.product((300, 500, 800, 1000, 1500, 2000), (300, 500, 800, 1000)))


def main() -> int:
    warnings.filterwarnings("ignore")
    for era in ("post", "pre"):
        cp, Pp = data(era); Fp, P = setup("50K", launch_paths(Pp)); Fp.update(LIVE); lab = "2021-26" if era == "post" else "2010-20"
        F0 = dict(Fp, fee=116.0, payout=V2); Z = randomised(P, SEEDS[0]); one = lambda r: summary(r, np.ones(len(r["net"]), bool))
        base = f.simulate(cp, P, 84, MIX, dict(F0, fscale=(1.0, 0.7))); b = one(base)
        print(f"{lab} deployed policy: net {b['net_mean']:+,.0f}, evals {b['evals']:.1f}, paid ${b['paid_sim'] + b['paid_live']:,.0f}, "
              f"zero edge {one(f.simulate(cp, Z, 84, MIX, dict(F0, fscale=(1.0, 0.7))))['net_mean']:+,.0f}", flush=True)
        for w, l in GRID:
            F = dict(F0, fixed={"NKD": (w, l), "FDXM": (w, l)}); r = f.simulate(cp, P, 84, MIX, F); x = one(r)
            m, lo, hi = ci(r["net"] - base["net"])
            print(f"{lab} fixed take ${w:>5,} stop ${l:>5,}: net {x['net_mean']:+8,.0f} P>0 {x['p_pos']:.0%} evals {x['evals']:5.1f} "
                  f"paid ${x['paid_sim'] + x['paid_live']:>7,.0f} | vs deployed {m:+,.0f} ({lo:+,.0f} .. {hi:+,.0f})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
