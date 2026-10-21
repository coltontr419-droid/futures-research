"""A101 (decisions.md 806): does the 3 NKD + 2 FDXM mix still lead under Tradeify's V2 payout rules (§805)? No trial.

    python -m futuresres.reporting.a101_v2_mix
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

ROOT = Path(__file__).resolve().parents[3]
MIXES = ["5: 3NKD+2FDXM", "5: 4NKD+1FDXM", "5: 2NKD+3FDXM", "5: NKD×5"]
V2 = ("daily", 2_100.0, 250.0, 1_250.0)


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    Fp, P = setup("50K", P1); Fq, Q = setup("50K", Q1); Fp.update(LIVE); Fq.update(LIVE)
    Fa, Fb = dict(Fp, fee=116.0, payout=V2), dict(Fq, fee=116.0, payout=V2)
    st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
    for mx in MIXES:
        M = f.MIXES[mx]; r = f.simulate(cp, P, 84, M, Fa); rq = f.simulate(cq, Q, 84, M, Fb)
        a, b, c = summary(r, m25), summary(r, np.ones(len(st), bool)), summary(rq, np.ones(len(rq["net"]), bool))
        z = float(np.mean([f.simulate(cp, randomised(P, s), 84, M, Fa)["net"].mean() for s in SEEDS]))
        out[mx] = {"2025": a, "2021-26": b, "2010-20": c, "zero_edge_2021_26": z}
        print(f"{mx:32}: 2025 {a['net_mean']:+8,.0f} ({a['p_pos']:.0%}, p10 {a['p10']:+,.0f}) | 2021-26 {b['net_mean']:+8,.0f} ({b['p_pos']:.0%}) | "
              f"2010-20 {c['net_mean']:+8,.0f} ({c['p_pos']:.0%}) | zero edge 2021-26 {z:+,.0f}", flush=True)
    (ROOT / "reports" / "a101_v2_mix.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
