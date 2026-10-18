"""A85 (decisions.md 718): Tradeify Select Daily vs Growth vs Lightning, 5 x 50K, 3 NKD + 2 FDXM, at today's sale prices. No trial.

    python -m futuresres.reporting.a85_account_lines
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup
from futuresres.reporting.a75_sim_contracts import LIVE

ROOT = Path(__file__).resolve().parents[3]
MIX = f.MIXES["5: 3NKD+2FDXM"]


def lines(F: dict) -> dict:
    base = a23.specs()["50K Daily"]
    return {
        "Select Daily $116": dict(F, fee=116.0),
        "Growth $102": dict(F, fee=102.0, cons=1.0, spec=dataclasses.replace(base, cons=1.0, fee=102.0),
                            payout=("growth", 2_000.0, 0.0, None), caps=(1_500.0, 2_000.0, 2_500.0, 3_000.0), win_day=150.0, min_bal=3_000.0, cons_f=0.35),
        "Lightning $344": dict(F, fee=344.0, no_eval=True, kind_goal=True, payout=("goal", 0.0, 1_000.0, None), goals=(3_000.0, 2_000.0),
                               cons_goal=(0.20, 0.25, 0.30), caps=(2_000.0, 2_000.0, 2_000.0, 2_500.0)),
    }


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    Fp, P = setup("50K", P1); Fq, Q = setup("50K", Q1); Fp.update(LIVE); Fq.update(LIVE)
    st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
    Lp, Lq = lines(Fp), lines(Fq)
    for name in Lp:
        r = f.simulate(cp, P, 84, MIX, Lp[name]); rq = f.simulate(cq, Q, 84, MIX, Lq[name])
        x = {"2025 starts": summary(r, m25), "2021-26": summary(r, np.ones(len(st), bool)), "2010-20": summary(rq, np.ones(len(rq["net"]), bool))}
        x["zero edge 2021-26"] = float(np.mean([f.simulate(cp, randomised(P, s), 84, MIX, Lp[name])["net"].mean() for s in SEEDS]))
        x["zero edge 2010-20"] = float(np.mean([f.simulate(cq, randomised(Q, s), 84, MIX, Lq[name])["net"].mean() for s in SEEDS]))
        out[name] = x
        a, b, c = x["2025 starts"], x["2021-26"], x["2010-20"]
        print(f"{name:18}: 2025 {a['net_mean']:+8,.0f} (median {a['net_median']:+,.0f}, {a['p_pos']:.0%}, p10 {a['p10']:+,.0f}) | 2021-26 {b['net_mean']:+8,.0f} "
              f"({b['p_pos']:.0%}, p10 {b['p10']:+,.0f}) | 2010-20 {c['net_mean']:+8,.0f} ({c['p_pos']:.0%}) | zero edge {x['zero edge 2021-26']:+,.0f} / "
              f"{x['zero edge 2010-20']:+,.0f} | 2021-26: accounts bought {b['evals']:.0f}, fees ${b['fees']:,.0f}, funded paid ${b['paid_sim']:,.0f}, "
              f"live paid ${b['paid_live']:,.0f}, moves {b['moves']:.2f}", flush=True)
    (ROOT / "reports" / "a85_account_lines.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
