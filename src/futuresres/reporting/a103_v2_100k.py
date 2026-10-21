"""A103 (decisions.md 808): 5 x 100K vs 5 x 50K Select Daily under V2 payouts (§805; 100K buffer $2,600, cap $1,750). No trial.

    python -m futuresres.reporting.a103_v2_100k
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

V2 = {"50K": ("daily", 2_100.0, 250.0, 1_250.0), "100K": ("daily", 2_600.0, 250.0, 1_750.0)}


def main() -> int:
    warnings.filterwarnings("ignore")
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
    for size in ("50K", "100K"):
        Fp, P = setup(size, P1); Fq, Q = setup(size, Q1)
        if size == "50K":
            Fp.update(LIVE); Fq.update(LIVE); Fp["fee"] = Fq["fee"] = 116.0
        for old_new, pay in (("old", None), ("V2", V2[size])):
            Fa, Fb = (dict(Fp, payout=pay), dict(Fq, payout=pay)) if pay else (Fp, Fq)
            r = f.simulate(cp, P, 84, MIX, Fa); rq = f.simulate(cq, Q, 84, MIX, Fb)
            a, b, c = summary(r, m25), summary(r, np.ones(len(st), bool)), summary(rq, np.ones(len(rq["net"]), bool))
            z = float(np.mean([f.simulate(cp, randomised(P, s), 84, MIX, Fa)["net"].mean() for s in SEEDS]))
            print(f"{size:4} {old_new:3} (fee ${Fa['fee']:.0f}): 2025 {a['net_mean']:+8,.0f} ({a['p_pos']:.0%}, p10 {a['p10']:+,.0f}) | 2021-26 {b['net_mean']:+8,.0f} "
                  f"({b['p_pos']:.0%}, p10 {b['p10']:+,.0f}) | 2010-20 {c['net_mean']:+8,.0f} ({c['p_pos']:.0%}) | zero edge {z:+,.0f} | fees 2021-26 ${b['fees']:,.0f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
