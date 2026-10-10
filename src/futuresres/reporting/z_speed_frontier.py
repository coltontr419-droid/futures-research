"""What edge does "pass AND get a first payout within 1-2 months" require in this account?

A COMPUTATION on Tradeify's confirmed rules (decisions.md 81-82) and resampled real MNQ 09:30-16:00
sessions with the drift REMOVED and an edge IMPOSED (annual Sharpe 0 to 5). No market claim, no trial.
decisions.md 91.

    python -m futuresres.reporting.z_speed_frontier [--log]

For each size (1-3 MNQ) and imposed Sharpe: P(pass within 21 / 42 trading days) and P(a first funded
payout within 42 trading days of starting the evaluation - the funded account starts the day after the
pass and must clear the $2,000 buffer).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.y01_structure_ev as y
import futuresres.reporting.y02_tradeify as z

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "z_speed_frontier.json"
SHARPES = (0.0, 1.0, 2.0, 3.0, 5.0)
SIZES = (1, 2, 3)
HORIZON = 42
ACCOUNTS = 6000


def race(paths, n, rng):
    h_all, l_all, c_all = paths
    S = len(c_all)
    A = ACCOUNTS
    eq = np.full(A, y.START); pk = eq.copy(); best = np.zeros(A)
    phase = np.zeros(A, int)            # 0 eval, 1 funded, -1 failed, 2 paid
    pass_day = np.full(A, -1); pay_day = np.full(A, -1)
    for d in range(HORIZON):
        for ph in (0, 1):
            act = np.flatnonzero(phase == ph)
            if not len(act):
                continue
            idx = rng.integers(0, S, len(act))
            ne, pnl, br = z.day_eod(eq[act], pk[act], h_all[idx], l_all[idx], c_all[idx], n, True, ph == 1)
            eq[act] = ne; pk[act] = np.maximum(pk[act], ne)
            if ph == 0:
                best[act] = np.maximum(best[act], pnl)
                prof = ne - y.START
                ok = (~br) & (prof >= y.TARGET) & (best[act] <= z.CONSISTENCY * prof)
                phase[act[br]] = -1
                p_ = act[ok]; phase[p_] = 1; pass_day[p_] = d + 1
                eq[p_] = y.START; pk[p_] = y.START          # the funded account starts fresh next day
            else:
                phase[act[br]] = -1
                paid = act[(~br) & (ne > y.START + y.LOCK)]
                phase[paid] = 2; pay_day[paid] = d + 1
    return {"p_pass_21": float(((pass_day > 0) & (pass_day <= 21)).mean()),
            "p_pass_42": float(((pass_day > 0) & (pass_day <= 42)).mean()),
            "p_payout_42": float((pay_day > 0).mean()),
            "p_failed_by_42": float((phase == -1).mean())}


def run(seed: int = 91) -> dict:
    dates, H, L, C, notional = y.load_sessions()
    post = dates >= y.ERA
    rng = np.random.default_rng(seed)
    sd_session = float(C[post][:, -1].std())
    _, _, c0, _ = y.window_paths(H[post], L[post], C[post], "rth", 0.0)
    share = float(c0[:, -1].std() / sd_session)
    out = []
    for s in SHARPES:
        h, l, c, _ = y.window_paths(H[post], L[post], C[post], "rth", s / math.sqrt(252) * sd_session * share)
        usd = (h * notional, l * notional, c * notional)
        for n in SIZES:
            r = race(usd, n, rng)
            r.update({"sharpe": s, "contracts": n, "daily_sigma": float(c[:, -1].std() * notional * n)})
            out.append(r)
            print(f"Sharpe {s:.0f}  {n} MNQ (sigma ${r['daily_sigma']:.0f}): pass<=21d {r['p_pass_21']:.0%} "
                  f"pass<=42d {r['p_pass_42']:.0%}  PAYOUT<=42d {r['p_payout_42']:.0%}", flush=True)
    return {"cells": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    r = json.loads(OUT.read_text()) if (a.log and OUT.exists()) else run()
    OUT.write_text(json.dumps(r, indent=1) + "\n")
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="Z-series", symbol="MNQ",
                               date_range=("2021-01-01", "2026-08-27"), status="completed",
                               params={"kind": "speed_frontier", **r},
                               note="kind=computation; NOT a trial. Edge required to pass and get a payout within "
                                    "42 trading days under Tradeify's rules. decisions.md 91."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
