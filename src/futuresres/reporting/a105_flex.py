"""A105 (decisions.md 810): Tradeify Select FLEX vs Select DAILY (both V2, accounts bought after 2026-09-01), 5 x 50K. No trial.

Flex (help.tradeify.co 12853966): a payout every 5 winning days (>= $150), up to 50% of total profit (balance - start), cap $2,500,
min $250, no 2x rule, no buffer, no consistency, same $2,000 EOD drawdown. Modelled with A63's "growth" payout kind (pay_frac 0.5,
min_bal ~0, consistency off). Same brackets as Daily (conservative: Flex has no daily loss limit).

    python -m futuresres.reporting.a105_flex
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

DAILY = dict(payout=("daily", 2_100.0, 250.0, 1_250.0))
FLEX = dict(payout=("growth", 0.0, 250.0, None), caps=(2_500.0,), win_day=150.0, min_bal=0.01, cons_f=1e9, pay_frac=0.5)


def main() -> int:
    warnings.filterwarnings("ignore")
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    Fp, P = setup("50K", P1); Fq, Q = setup("50K", Q1); Fp.update(LIVE); Fq.update(LIVE)
    st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
    for mixname in ("5: 3NKD+2FDXM", "5: 2NKD+3FDXM"):
        M = f.MIXES[mixname]
        for pol, extra in (("Daily V2", DAILY), ("Flex", FLEX)):
            Fa, Fb = dict(Fp, fee=116.0, **extra), dict(Fq, fee=116.0, **extra)
            r = f.simulate(cp, P, 84, M, Fa); rq = f.simulate(cq, Q, 84, M, Fb)
            a, b, c = summary(r, m25), summary(r, np.ones(len(st), bool)), summary(rq, np.ones(len(rq["net"]), bool))
            z = float(np.mean([f.simulate(cp, randomised(P, s), 84, M, Fa)["net"].mean() for s in SEEDS]))
            print(f"{mixname:16} {pol:8}: 2025 {a['net_mean']:+8,.0f} ({a['p_pos']:.0%}, p10 {a['p10']:+,.0f}) | 2021-26 {b['net_mean']:+8,.0f} ({b['p_pos']:.0%}) | "
                  f"2010-20 {c['net_mean']:+8,.0f} ({c['p_pos']:.0%}) | zero edge {z:+,.0f} | funded paid ${b['paid_sim']:,.0f}, live ${b['paid_live']:,.0f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
