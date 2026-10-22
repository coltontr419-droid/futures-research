"""A113 (decisions.md 827): Tradeify Select 300K V2 — value per $349 attempt (held on top of the 5-account cap; 3 per lifetime). No trial.

Official (help article 16497699, read 2026-10-21): evaluation $349, target $14,000, EOD drawdown $8,000, daily loss $4,000, 40%
consistency; funded Daily drawdown $6,000, buffer $6,100, up to $4,000 a day, 50% of each payout new profit (= the 2x rule), no live
rules modelled. Evaluation drawdown $8,000 and funded $6,000 (`dd_f`); the run with $6,000 in both is a pessimistic check. One NKD
account, 252 sessions, re-buy after a failure; value per attempt = (paid - fees) / attempts. The full 300K policy solve is too big for
this machine (~5 M states a step, 2.7 GB RAM), so every dollar rule is divided by 4 (a quarter-size virtual account: target $3,500, dd
$2,000 / $1,500, daily loss $1,000 / $750, cap $1,000, buffer $1,525, fee $87.25, 1 NKD contract as the 50K) and results multiplied by 4.

    python -m futuresres.reporting.a113_300k
"""

from __future__ import annotations

import dataclasses
import warnings

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, randomised, setup

Q = 4.0                                                          # quarter-size virtual account (see above)
S300Q = a23.Spec("300K/4 Daily", 75_000, 349.0 / Q, 35, 20, 0.40, 15, 10, 8, e_daily=10, k_contracts=1.0, cap_usd=4_000.0 / Q)


def main() -> int:
    warnings.filterwarnings("ignore")
    for era in ("post", "pre"):
        cp, Pp = data(era); F0, P = setup("50K", launch_paths(Pp))
        st = np.array(cp[: len(cp) - 252])
        for dd in (6_000.0, 8_000.0):
            spec = dataclasses.replace(S300Q, dd=int(dd / Q / 100))
            F = dict(F0, fee=349.0 / Q, spec=spec, dd=dd / Q, dd_f=6_000.0 / Q, target=14_000.0 / Q, payout=("daily", 6_100.0 / Q, 250.0 / Q, 4_000.0 / Q),
                     live=("never", 0), cons=0.40, lock=f.START, max_acc=1)
            r = f.simulate(cp, P, 252, ("NKD",), F); b = summary(r, np.ones(len(st), bool))
            att = b["evals"]; per = Q * (b["paid_sim"] - b["fees"]) / max(att, 1e-9)
            z = [f.simulate(cp, randomised(P, s), 252, ("NKD",), F) for s in SEEDS[:3]]
            zb = [summary(x, np.ones(len(st), bool)) for x in z]
            zper = Q * np.mean([(x["paid_sim"] - x["fees"]) / max(x["evals"], 1e-9) for x in zb])
            print(f"{'2021-26' if era == 'post' else '2010-20'} dd ${dd:,.0f}: 252-session net (x4) {Q * b['net_mean']:+9,.0f} | attempts {att:.1f} | "
                  f"value per $349 attempt {per:+,.0f} | zero edge per attempt {zper:+,.0f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
