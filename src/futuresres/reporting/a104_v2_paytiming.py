"""A104 (decisions.md 809): under V2 payouts, request every eligible day (>= $250) or wait for a larger request? No trial.

    python -m futuresres.reporting.a104_v2_paytiming
"""

from __future__ import annotations

import datetime as dt
import warnings

import numpy as np

import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX


def main() -> int:
    warnings.filterwarnings("ignore")
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    Fp, P = setup("50K", P1); Fq, Q = setup("50K", Q1); Fp.update(LIVE); Fq.update(LIVE)
    st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
    for pmin in (250.0, 625.0, 1_000.0, 1_250.0):
        pay = ("daily", 2_100.0, pmin, 1_250.0)
        Fa, Fb = dict(Fp, fee=116.0, payout=pay), dict(Fq, fee=116.0, payout=pay)
        r = f.simulate(cp, P, 84, MIX, Fa); rq = f.simulate(cq, Q, 84, MIX, Fb)
        a, b, c = summary(r, m25), summary(r, np.ones(len(st), bool)), summary(rq, np.ones(len(rq["net"]), bool))
        z = float(np.mean([f.simulate(cp, randomised(P, s), 84, MIX, Fa)["net"].mean() for s in SEEDS]))
        print(f"request only when >= ${pmin:,.0f}: 2025 {a['net_mean']:+8,.0f} ({a['p_pos']:.0%}, p10 {a['p10']:+,.0f}) | 2021-26 {b['net_mean']:+8,.0f} "
              f"({b['p_pos']:.0%}) | 2010-20 {c['net_mean']:+8,.0f} ({c['p_pos']:.0%}) | zero edge {z:+,.0f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
