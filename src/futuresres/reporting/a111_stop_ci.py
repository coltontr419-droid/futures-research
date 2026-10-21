"""A111 (decisions.md 818): paired block-bootstrap CI for the funded stop 0.7x vs 1.0x (V2), per start window. No trial.

    python -m futuresres.reporting.a111_stop_ci
"""

from __future__ import annotations

import warnings

import numpy as np

import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import setup
from futuresres.reporting.a75_sim_contracts import LIVE
from futuresres.reporting.a85_account_lines import MIX

V2 = ("daily", 2_100.0, 250.0, 1_250.0)


def ci(d: np.ndarray, block: int = 84, n: int = 4000, seed: int = 818) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed); L = len(d); nb = int(np.ceil(L / block)); out = []
    for _ in range(n):
        idx = np.concatenate([np.arange(s, min(s + block, L)) for s in rng.integers(0, L - block, nb)])[:L]
        out.append(d[idx].mean())
    return float(d.mean()), float(np.percentile(out, 5)), float(np.percentile(out, 95))


def main() -> int:
    warnings.filterwarnings("ignore")
    for era in ("post", "pre"):
        cp, Pp = data(era); Fp, P = setup("50K", launch_paths(Pp)); Fp.update(LIVE)
        a = f.simulate(cp, P, 84, MIX, dict(Fp, fee=116.0, payout=V2))["net"]
        b = f.simulate(cp, P, 84, MIX, dict(Fp, fee=116.0, payout=V2, fscale=(1.0, 0.7)))["net"]
        m, lo, hi = ci(b - a)
        print(f"{'2021-26' if era == 'post' else '2010-20'}: stop 0.7x minus 1.0x per start window: mean {m:+,.0f}, 90% block-bootstrap CI {lo:+,.0f} .. {hi:+,.0f}; "
              f"share of windows better {np.mean(b > a):.0%}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
