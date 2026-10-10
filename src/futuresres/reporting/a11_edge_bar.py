"""A11 - the edge bar for the two staking plans: what a directional edge of a given strength adds to 4 MNQ
(09:30-16:00) and 8 MGC (03:00-11:30 ET) over 84 trading days. A COMPUTATION; planted edges; no trial.
decisions.md 109.

    python -m futuresres.reporting.a11_edge_bar --era post && python -m futuresres.reporting.a11_edge_bar --era pre
    python -m futuresres.reporting.a11_edge_bar --log

A signal that picks each day's direction with annual Sharpe S on the window is, for the bracket, a drift of
S / sqrt(252) x sigma_window per session in the traded direction. It is planted on the drift-free paths (A08's
caches) as a linear ramp across the window, stops fill at the stop price (decisions.md 108), and the plans run as
in A10b (replay and 21-session block bootstrap). S = 0 reproduces A10b.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a01_game as g
import futuresres.reporting.a02_real as a2
import futuresres.reporting.a08_gold as a8

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a11_edge_bar.json"
PLANS = {"MNQ": ("rth_0930_1600", 4, 2.32), "MGC": ("london_0300_1130", 8, 3.32)}
SHARPES = (0.0, 0.25, 0.5, 1.0, 2.0)


def run(era: str) -> dict:
    warnings.filterwarnings("ignore")
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    a2.STOP_FILL = "level"
    out = {}
    for prod, (win, n, rt) in PLANS.items():
        h, l, c, _ = a8.era_paths(era, prod, win)
        sd = float(c[:, -1].std())
        ramp = (np.arange(1, c.shape[1] + 1, dtype=np.float32) / c.shape[1])[None, :]
        tot = np.float32(n * rt)
        for S in SHARPES:
            d = np.float32(S / math.sqrt(252) * sd) * ramp
            hh, ll, cc = h + d, l + d, c + d
            a2._PATHS["p"] = ((hh * n - (tot - a8.RT_ENGINE)).astype(np.float32), (ll * n - tot).astype(np.float32),
                              (cc * n - tot).astype(np.float32))
            rp = a2.sequential(1, "replay"); bl = [a2.sequential(1, "block", traders=6000, seed=s) for s in (11, 12)]
            k = f"{prod} S={S}"
            out[k] = {"drift_per_day_usd_1ct": float(S / math.sqrt(252) * sd), 
                      "replay": [rp["p_any_payout"], rp["mean_net"], rp["p_net_positive"]],
                      "block": [float(np.mean([b[x] for b in bl])) for x in ("p_any_payout", "mean_net", "p_net_positive")]}
            print(era, k, json.dumps(out[k]), flush=True)
        a2._PATHS.clear()
    return {era: out}


def _out(era: str) -> Path:
    return ROOT / "reports" / f"a11_edge_bar_{era}.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--era", choices=("post", "pre")); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    if a.era:
        _out(a.era).write_text(json.dumps(run(a.era), indent=1) + "\n"); return 0
    r = {**json.loads(_out("post").read_text()), **json.loads(_out("pre").read_text())}
    OUT.write_text(json.dumps(r, indent=1) + "\n")
    for e in ("post", "pre"):
        _out(e).unlink()
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="A-series", symbol="MNQ+MGC",
                               date_range=("2011-02-01", "2026-08-27"), status="completed", params={"kind": "edge_bar_staking", **r},
                               note="kind=computation; NOT a trial. A11: planted directional edges on the two staking plans. decisions.md 109."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
