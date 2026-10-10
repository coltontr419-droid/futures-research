"""A12 - the two demo accounts run TOGETHER: 4 MNQ (09:30-16:00) and 8 MGC (03:00-11:30 ET), both started on the
same date and replayed through real history in order for 84 trading days, stops filling at the stop price. A
COMPUTATION; zero edge (drift removed); no trial. decisions.md 112.

    python -m futuresres.reporting.a12_joint [--log]

Replaces the independence estimate (decisions.md 106: ~85% for at least one payout) with the measured joint
outcome: each product's back-to-back replay (a02_real.sequential, per_trader) is paired with the other's on
common start dates. Histories: 2021-26 and 2015-11 to 2020 (MNQ's complete sessions start 2015-11-20).
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
OUT = ROOT / "reports" / "a12_joint.json"
PLANS = {"MNQ": ("rth_0930_1600", 4, 2.32), "MGC": ("london_0300_1130", 8, 3.32)}


def per_start(era: str, prod: str) -> dict:
    win, n, rt = PLANS[prod]
    h, l, c, d = a8.era_paths(era, prod, win)
    tot = np.float32(n * rt)
    a2._PATHS["p"] = ((h * n - (tot - a8.RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32))
    r = a2.sequential(1, "replay", per_trader=True)
    a2._PATHS.clear()
    e = r["each"]
    return {"date": np.asarray(d)[e["start"]].astype("datetime64[D]"), "net": e["net"], "first": e["first_payout_day"],
            "fees": e["fees"], "paid": e["paid"]}


def combine(m: dict, g_: dict) -> dict:
    common, im, ig = np.intersect1d(m["date"], g_["date"], return_indices=True)
    pm, pg = m["first"][im] > 0, g_["first"][ig] > 0
    net = m["net"][im] + g_["net"][ig]
    first = np.where(pm & pg, np.minimum(m["first"][im], g_["first"][ig]), np.where(pm, m["first"][im], np.where(pg, g_["first"][ig], -1)))
    ind = 1 - (1 - pm.mean()) * (1 - pg.mean())
    return {"common_starts": int(len(common)), "first": str(common[0]), "last": str(common[-1]),
            "p_payout_mnq": float(pm.mean()), "p_payout_mgc": float(pg.mean()),
            "p_any_payout": float((pm | pg).mean()), "p_any_payout_if_independent": float(ind),
            "p_both_payout": float((pm & pg).mean()),
            "median_day_first_payout": float(np.median(first[first > 0])) if (first > 0).any() else None,
            "mean_net": float(net.mean()), "p_net_positive": float((net > 0).mean()),
            "net_p10_p50_p90": [float(x) for x in np.quantile(net, [0.1, 0.5, 0.9])],
            "mean_fees": float((m["fees"][im] + g_["fees"][ig]).mean()),
            "corr_net": float(np.corrcoef(m["net"][im], g_["net"][ig])[0, 1]),
            "worst_net": float(net.min())}


def scale(m: dict, g_: dict, ks=(1, 2, 5, 10, 20)) -> dict:
    """k parallel pairs (1 MNQ + 1 MGC stream each), pair i started i trading days after the first: the sum of
    their real-order outcomes, over every first start date (decisions.md 114)."""
    common, im, ig = np.intersect1d(m["date"], g_["date"], return_indices=True)
    net = m["net"][im] + g_["net"][ig]; fees = m["fees"][im] + g_["fees"][ig]; paid = m["paid"][im] + g_["paid"][ig]
    out = {}
    for k in ks:
        S = len(net) - k
        tot = np.array([net[s:s + k].sum() for s in range(S)])
        out[k] = {"fees": float(np.mean([fees[s:s + k].sum() for s in range(S)])),
                  "paid": float(np.mean([paid[s:s + k].sum() for s in range(S)])),
                  "mean_net": float(tot.mean()), "median_net": float(np.median(tot)), "p_net_positive": float((tot > 0).mean()),
                  "net_p10": float(np.quantile(tot, 0.1)), "worst": float(tot.min())}
    return out


def run() -> dict:
    warnings.filterwarnings("ignore")
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    a2.STOP_FILL = "level"
    out = {}
    for era in ("post", "pre"):
        m, gg = per_start(era, "MNQ"), per_start(era, "MGC")
        out[era] = combine(m, gg)
        out[era]["parallel_pairs"] = scale(m, gg)
        print(era, json.dumps(out[era]), flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    r = run()
    OUT.write_text(json.dumps(r, indent=1) + "\n")
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="A-series", symbol="MNQ+MGC",
                               date_range=(r["pre"]["first"], r["post"]["last"]), status="completed",
                               params={"kind": "joint_two_accounts", **r},
                               note="kind=computation; NOT a trial. A12: 4 MNQ + 8 MGC accounts run together, real order. decisions.md 112."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
