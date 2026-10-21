"""A109 (decisions.md 816): with the funded stop at 0.7x (deployed, §815), the funded take factor and the mix, under V2. No trial.

    python -m futuresres.reporting.a109_v2_take
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

V2 = ("daily", 2_100.0, 250.0, 1_250.0)


def main() -> int:
    warnings.filterwarnings("ignore")
    cp, Pp = data("post"); cq, Pq = data("pre"); Fp, P = setup("50K", launch_paths(Pp)); Fq, Q = setup("50K", launch_paths(Pq))
    Fp.update(LIVE); Fq.update(LIVE)
    st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
    for mx, fs in (("5: 3NKD+2FDXM", (0.8, 0.7)), ("5: 3NKD+2FDXM", (0.9, 0.7)), ("5: 3NKD+2FDXM", (1.0, 0.7)), ("5: 3NKD+2FDXM", (1.1, 0.7)),
                   ("5: 3NKD+2FDXM", (1.25, 0.7)), ("5: 2NKD+3FDXM", (1.0, 0.7)), ("5: 4NKD+1FDXM", (1.0, 0.7))):
        M = f.MIXES[mx]; Fa, Fb = dict(Fp, fee=116.0, payout=V2, fscale=fs), dict(Fq, fee=116.0, payout=V2, fscale=fs)
        r = f.simulate(cp, P, 84, M, Fa); rq = f.simulate(cq, Q, 84, M, Fb)
        a, b, c = summary(r, m25), summary(r, np.ones(len(st), bool)), summary(rq, np.ones(len(rq["net"]), bool))
        z = float(np.mean([f.simulate(cp, randomised(P, s), 84, M, Fa)["net"].mean() for s in SEEDS]))
        print(f"{mx:15} take x{fs[0]:.2f} stop x{fs[1]:.2f}: 2025 {a['net_mean']:+8,.0f} ({a['p_pos']:.0%}, p10 {a['p10']:+,.0f}) | 2021-26 {b['net_mean']:+8,.0f} | "
              f"2010-20 {c['net_mean']:+8,.0f} | zero edge {z:+,.0f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
