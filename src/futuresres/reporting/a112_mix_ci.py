"""A112 (decisions.md 819): paired block-bootstrap CIs for other mixes vs 3 NKD + 2 FDXM (V2, funded stop 0.7x). No trial.

    python -m futuresres.reporting.a112_mix_ci
"""

from __future__ import annotations

import warnings

import numpy as np

import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a111_stop_ci import V2, ci


def main() -> int:
    warnings.filterwarnings("ignore")
    for era in ("post", "pre"):
        cp, Pp = data(era); Fp, P = setup("50K", launch_paths(Pp)); Fp.update(LIVE); F = dict(Fp, fee=116.0, payout=V2, fscale=(1.0, 0.7))
        base = f.simulate(cp, P, 84, f.MIXES["5: 3NKD+2FDXM"], F)["net"]
        for mx in ("5: 4NKD+1FDXM", "5: 2NKD+3FDXM"):
            d = f.simulate(cp, P, 84, f.MIXES[mx], F)["net"] - base; m, lo, hi = ci(d)
            print(f"{'2021-26' if era == 'post' else '2010-20'}: {mx} minus 3+2: mean {m:+,.0f}, 90% CI {lo:+,.0f} .. {hi:+,.0f}; windows better {np.mean(d > 0):.0%}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
