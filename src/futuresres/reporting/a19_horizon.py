"""A19 - the planning horizon of the solved policy: the evaluation solved for P(pass within He days) and the funded account
for E[payouts within Hf days], He in {21, 42, 84}, Hf in {21, 63, 126, 252}; each pair replayed through real history in order
(4 MNQ 09:30-16:00 and 8 MGC 03:00-11:30, drift removed, stops at the stop price) over 84- and 252-day windows of back-to-back
$80 attempts. A COMPUTATION; zero edge; no trial. decisions.md 135.

    python -m futuresres.reporting.a19_horizon --era post     (one era per process)
    python -m futuresres.reporting.a19_horizon --era pre
    python -m futuresres.reporting.a19_horizon --log          (merge and record)

The plan so far uses He = Hf = 21 (A01): a stationary policy taken 21 days from the end. A funded account at zero edge can be
worth up to its cushion over its life; a policy that plans further ahead may capture more of it.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a01_game as g
import futuresres.reporting.a02_real as a2
import futuresres.reporting.a08_gold as a8

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a19_horizon.json"
PLANS = {"MNQ": ("rth_0930_1600", 4, 2.32), "MGC": ("london_0300_1130", 8, 3.32)}
HE, HF, WINDOWS = (21, 42, 84), (21, 63, 126, 252), (84, 252)


def _row(r):
    return {k: r[k] for k in ("p_any_payout", "mean_net", "p_net_positive", "mean_attempts", "mean_fees", "mean_paid")}


def run(era: str) -> dict:
    warnings.filterwarnings("ignore")
    a2.STOP_FILL = "level"
    paths = {}
    for prod, (win, n, rt) in PLANS.items():
        h, l, c, _ = a8.era_paths(era, prod, win)
        tot = np.float32(n * rt)
        paths[prod] = ((h * n - (tot - a8.RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32))
    pols_e, pols_f = {}, {}
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        for he in HE:
            g.solve_all(he, keep_policy_at=he); pols_e[he] = g.POLICY["eval"].copy()
        for hf in HF:
            g.solve_funded(hf, "dollars", keep_policy_at=hf); pols_f[hf] = g.POLICY["funded"].copy()
    out = {}
    for he in HE:
        for hf in HF:
            g.POLICY["eval"], g.POLICY["funded"] = pols_e[he], pols_f[hf]
            key = f"He{he}_Hf{hf}"
            out[key] = {}
            for prod in PLANS:
                a2._PATHS["p"] = paths[prod]
                out[key][prod] = {}
                for w in WINDOWS:
                    rp = a2.sequential(1, "replay", window=w)
                    bl = [a2.sequential(1, "block", traders=4000, window=w, seed=s) for s in (11, 12)]
                    out[key][prod][w] = {"replay": _row(rp), "block": {k: float(np.mean([b[k] for b in bl])) for k in _row(rp)}}
            m84 = sum(out[key][p][84]["block"]["mean_net"] for p in PLANS); m252 = sum(out[key][p][252]["block"]["mean_net"] for p in PLANS)
            print(f"{era} {key}: MNQ+MGC block mean net 84d {m84:+,.0f} | 252d {m252:+,.0f}", flush=True)
    a2._PATHS.clear()
    return {era: out}


def _out(era: str) -> Path:
    return ROOT / "reports" / f"a19_{era}.json"


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
                               date_range=("2011-02-01", "2026-08-27"), status="completed", params={"kind": "policy_horizon", **r},
                               note="kind=computation; NOT a trial. A19: evaluation / funded planning horizons, replayed. decisions.md 135."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
