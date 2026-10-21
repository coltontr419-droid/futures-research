"""A100 (decisions.md 805): the plan under Tradeify's OFFICIAL Select Daily payout rules vs the model used so far. No trial.

Official (help.tradeify.co 12853966, read 2026-10-21): 50K buffer $2,100; cap $1,250 a request (accounts bought after 2026-09-01);
minimum $250; up to 2x the profit earned since the last payout, which must be > 0. The model so far: buffer $2,000, cap $1,250, no
minimum, no 2x rule. Same setup as A85 (5 x 50K, 3 NKD + 2 FDXM, $116, live rules), with the deployed rules and at zero edge.

    python -m futuresres.reporting.a100_official_payouts
"""

from __future__ import annotations

import datetime as dt
import json
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX

ROOT = Path(__file__).resolve().parents[3]
RULES = {"model so far": ("cap", 2_000.0, 0.0, 1_250.0), "official": ("daily", 2_100.0, 250.0, 1_250.0)}


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    Fp, P = setup("50K", P1); Fq, Q = setup("50K", Q1); Fp.update(LIVE); Fq.update(LIVE)
    st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
    for name, pay in RULES.items():
        Fa, Fb = dict(Fp, fee=116.0, payout=pay), dict(Fq, fee=116.0, payout=pay)
        r = f.simulate(cp, P, 84, MIX, Fa); rq = f.simulate(cq, Q, 84, MIX, Fb)
        x = {"2025 starts": summary(r, m25), "2021-26": summary(r, np.ones(len(st), bool)), "2010-20": summary(rq, np.ones(len(rq["net"]), bool))}
        x["zero edge 2021-26"] = float(np.mean([f.simulate(cp, randomised(P, s), 84, MIX, Fa)["net"].mean() for s in SEEDS]))
        x["zero edge 2010-20"] = float(np.mean([f.simulate(cq, randomised(Q, s), 84, MIX, Fb)["net"].mean() for s in SEEDS]))
        out[name] = x; a, b, c = x["2025 starts"], x["2021-26"], x["2010-20"]
        print(f"{name:13}: 2025 {a['net_mean']:+8,.0f} (median {a['net_median']:+,.0f}, {a['p_pos']:.0%}, p10 {a['p10']:+,.0f}) | 2021-26 {b['net_mean']:+8,.0f} "
              f"({b['p_pos']:.0%}) | 2010-20 {c['net_mean']:+8,.0f} ({c['p_pos']:.0%}) | zero edge {x['zero edge 2021-26']:+,.0f} / {x['zero edge 2010-20']:+,.0f} | "
              f"2021-26 funded paid ${b['paid_sim']:,.0f}, live paid ${b['paid_live']:,.0f}, fees ${b['fees']:,.0f}", flush=True)
    (ROOT / "reports" / "a100_official_payouts.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
