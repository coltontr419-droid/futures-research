"""Route 2's bar: how strong must an edge be ON THE DAYS IT IS HELD, and how often, for a payout within
4 months under Tradeify's rules? A COMPUTATION on synthetic held-day returns; no market claim, no trial.
decisions.md 95.

    python -m futuresres.reporting.b_event_frontier [--log]

An event strategy holds on k days a month (spread evenly) and is flat otherwise. A held day's P&L is
Student-t(5), daily $ sigma S, mean = s x S (s = the per-held-day Sharpe; annual Sharpe = s x sqrt(12 k)).
The intraday low on a held day is approximated as min(0, close) - 0.5 S x |t| (an excursion below the
close). Costs $5 per held day. Tradeify Select Daily (user's terms) via z_firms' engine; best S chosen
per cell from {400, 700, 1000, 1400}; P(first payout within 84 trading days), EV per $80 attempt.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.z_firms as zf

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "b_event_frontier.json"
S_PER_DAY = (0.05, 0.10, 0.15, 0.20, 0.30)
K_PER_MONTH = (2, 5, 10, 21)
SIGMAS = (400.0, 700.0, 1000.0, 1400.0)


def paths(s: float, k: int, sigma: float, rng, n: int = 21 * 400):
    held = (np.arange(n) % 21) < k if k < 21 else np.ones(n, bool)
    rng.shuffle(held.reshape(-1, 21).T)                     # spread the held days within each month
    t = rng.standard_t(5, n) / math.sqrt(5 / 3)
    c = np.where(held, sigma * (s + t) - 5.0, 0.0)
    l = np.where(held, np.minimum(c, 0.0) - 0.5 * sigma * np.abs(rng.standard_t(5, n) / math.sqrt(5 / 3)), 0.0)
    l = np.minimum(l, c)
    return c[:, None].astype(np.float32), l[:, None].astype(np.float32), c[:, None].astype(np.float32)


def run(seed: int = 95) -> dict:
    rng = np.random.default_rng(seed)
    spec = zf.SPECS["Tradeify Select Daily (user's terms)"]
    out = {}
    for s in S_PER_DAY:
        for k in K_PER_MONTH:
            best = None
            for sg in SIGMAS:
                h, l, c = paths(s, k, sg, rng)
                # z_firms draws days independently, so a day is 'held' with probability k/21 - frequency, not order
                r = zf.simulate(spec, (h, l, c), rng, accounts=3000)
                r["sigma"] = sg
                if best is None or r["p_payout_84"] > best["p_payout_84"]:
                    best = r
            out[f"{s}_{k}"] = {"s_per_day": s, "days_per_month": k, "annual_sharpe": s * math.sqrt(12 * k), **best}
            print(f"per-day Sharpe {s:.2f}, {k:2d} days/month (annual {s*math.sqrt(12*k):.2f}): best sigma "
                  f"${best['sigma']:.0f}  P(payout<=84d) {best['p_payout_84']:.0%}  EV84 {best['ev_84']:+.0f}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    r = json.loads(OUT.read_text()) if (a.log and OUT.exists()) else run()
    OUT.write_text(json.dumps(r, indent=1) + "\n")
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="B-series", symbol="synthetic",
                               date_range=("n/a", "n/a"), status="completed", params={"kind": "event_frontier", "cells": r},
                               note="kind=computation; NOT a trial. Edge needed per held day for a 4-month payout. decisions.md 95."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
