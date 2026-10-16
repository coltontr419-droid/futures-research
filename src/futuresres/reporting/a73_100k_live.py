"""A73 - 5 x 100K against 5 x 50K, both with the solved live policy (decisions.md 654). No trial.

    python -m futuresres.reporting.a73_100k_live
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
from futuresres.reporting.a27_standalone import flip
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a64_sizes_live import scaled
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a71_realgame import F0, MIX, solve_live

ROOT = Path(__file__).resolve().parents[3]
SEEDS = range(6)


def setup(size: str, P1: dict):
    """(F, paths) for a size with its solved live policy."""
    if size == "50K":
        s = a23.specs()["50K Daily"]; P = P1; room = 20
        F = dict(F0)
    else:
        s = a23.specs()["100K Daily"]; P = scaled(P1, s); room = 30
        F = dict(F0, fee=s.fee, spec=s, dd=s.dd * 100.0, target=s.target * 100.0, payout=("cap", s.f_dd * 100.0, 0.0, s.cap_usd),
                 live_dd=3_000.0, live_cushion=3_000.0, cons=s.cons, lock=f.START)
    ls = dataclasses.replace(s, f_dd=room, f_daily=None)          # live: stop menu scaled to the live room, no daily limit
    F["live_pol"] = {m: solve_live(ls, float(P[m][3]), 84, room=room, lock=room)[:2] for m in sorted(set(MIX))}
    return F, P


def randomised(P: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed); out = {}
    for m, (h, l, c, cost, has) in P.items():
        out[m] = (*flip(h, l, c, rng.random(len(c)) < 0.5), cost, has)
    return out


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
    for size in ("50K", "100K"):
        F, P = setup(size, P1); Fq, Q = setup(size, Q1)
        r = f.simulate(cp, P, 84, MIX, F); rq = f.simulate(cq, Q, 84, MIX, Fq)
        x = {"2025 starts": summary(r, m25), "2021-26": summary(r, np.ones(len(st), bool)), "2010-20": summary(rq, np.ones(len(rq["net"]), bool))}
        x["zero edge 2021-26"] = float(np.mean([f.simulate(cp, randomised(P, k), 84, MIX, F)["net"].mean() for k in SEEDS]))
        x["zero edge 2010-20"] = float(np.mean([f.simulate(cq, randomised(Q, k), 84, MIX, Fq)["net"].mean() for k in SEEDS]))
        out[size] = x
        print(f"5 x {size}: " + " | ".join(f"{p} mean {x[p]['net_mean']:+,.0f} median {x[p]['net_median']:+,.0f} ({x[p]['p_pos']:.0%}, p10 {x[p]['p10']:+,.0f}, "
              f"worst {x[p]['worst']:+,.0f}; fees {x[p]['fees']:,.0f}, live {x[p]['paid_live']:,.0f})" for p in ("2025 starts", "2021-26", "2010-20"))
              + f" | zero edge {x['zero edge 2021-26']:+,.0f} / {x['zero edge 2010-20']:+,.0f}", flush=True)
    (ROOT / "reports" / "a73_100k_live.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
