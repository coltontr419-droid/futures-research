"""Y01 sensitivity: how the zero-edge structure EV moves with drift and cost, and what a budget of
evaluations returns. A computation on the Y01 engine; no market claim, no trial. decisions.md 79.

    python -m futuresres.reporting.y01_sensitivity
    python -m futuresres.reporting.y01_sensitivity --log

Post-2021 sessions only (the half that decides, S8). Two policies, both fixed BEFORE this run from Y01's
grid and stated here so they are not chosen from these results: RTH 09:30-16:00 with 2 MNQ (Y01's best
cell in both eras) and the full 18:00-16:55 session with 1 MNQ (the smallest full-session position).

DRIFT is imposed, not estimated: a long position's annual Sharpe of -0.3 to +0.3, applied to the
window's own sessions. -0.3 is a bear-market stand-in; +0.3 the external equity-premium prior Y01 used.
COST: $0, the X01 $2.32 per round trip, and double it.
BUDGET: per-evaluation net outcome = -$80, plus the funded account's 2-year payout if it passes, drawn
from the simulated accounts; K evaluations are summed by resampling those outcomes, independent.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Final

import numpy as np

import futuresres.reporting.y01_structure_ev as y

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
OUT_JSON: Final[Path] = ROOT / "reports" / "y01_sensitivity.json"
OUT_MD: Final[Path] = ROOT / "reports" / "y01_sensitivity.md"
POLICIES: Final[tuple[tuple[str, int], ...]] = (("rth", 2), ("full", 1))
DRIFTS: Final[tuple[float, ...]] = (-0.3, -0.15, 0.0, 0.15, 0.3)
COSTS: Final[tuple[float, ...]] = (0.0, 2.32, 4.64)
BUDGETS: Final[tuple[int, ...]] = (5, 10, 20, 40)
ACCOUNTS: Final[int] = 4000


def _accounts(paths, n, rng, eval_phase, days):
    """simulate(), but returning per-account arrays."""
    h_all, l_all, c_all = paths
    S = len(c_all)
    eq = np.full(ACCOUNTS, y.START); peak = eq.copy()
    alive = np.ones(ACCOUNTS, bool); passed = np.zeros(ACCOUNTS, bool); paid = np.zeros(ACCOUNTS)
    for d in range(days):
        act = np.flatnonzero(alive & ~passed)
        if not len(act):
            break
        idx = rng.integers(0, S, len(act))
        for k in range(0, len(act), y.CHUNK):
            a_, i_ = act[k:k + y.CHUNK], idx[k:k + y.CHUNK]
            ne, npk, br, ps = y._day(eq[a_], peak[a_], None, h_all[i_], l_all[i_], c_all[i_], n,
                                     y.TARGET if eval_phase else None)
            eq[a_] = ne; peak[a_] = npk
            alive[a_[br]] = False; passed[a_[ps]] = True
        if not eval_phase and (d + 1) % y.MONTH == 0:
            excess = np.where(alive, np.maximum(eq - (y.START + y.LOCK), 0.0), 0.0)
            paid += y.SPLIT * excess
            eq -= excess
    return passed if eval_phase else paid


def cell(H, L, C, notional, window, n, sharpe, cost, rng) -> dict:
    sd_session = float(C[:, -1].std())
    a, b = y.WINDOWS[window]
    # drift for the window, scaled by the window's share of the session's variance
    h0, l0, c0, _ = y.window_paths(H, L, C, window, 0.0)
    share = float(c0[:, -1].std() / sd_session)
    drift = sharpe / math.sqrt(252) * sd_session * share
    h, l, c, _ = y.window_paths(H, L, C, window, drift)
    usd = (h * notional, l * notional, c * notional)
    saved = y.RT_COST
    y.RT_COST = cost
    try:
        passed = _accounts(usd, n, rng, True, y.EVAL_DAYS)
        payouts = _accounts(usd, n, rng, False, y.FUNDED_DAYS)
    finally:
        y.RT_COST = saved
    p = float(passed.mean())
    return {"window": window, "contracts": n, "sharpe": sharpe, "cost": cost, "p_pass": p,
            "expected_payout": float(payouts.mean()), "ev": p * float(payouts.mean()) - y.FEE,
            "_payouts": payouts, "_p": p}


def budget(p: float, payouts: np.ndarray, rng, reps: int = 20000) -> dict:
    out = {}
    for k in BUDGETS:
        passes = rng.random((reps, k)) < p
        draws = rng.choice(payouts, size=(reps, k))
        net = (passes * draws).sum(1) - y.FEE * k
        out[k] = {"p_net_positive": float((net > 0).mean()), "median": float(np.median(net)),
                  "p05": float(np.quantile(net, 0.05)), "p95": float(np.quantile(net, 0.95)),
                  "mean": float(net.mean()), "outlay": y.FEE * k}
    return out


def run(seed: int = 20261009) -> dict:
    dates, H, L, C, notional = y.load_sessions()
    post = dates >= y.ERA
    H, L, C = H[post], L[post], C[post]
    rng = np.random.default_rng(seed)
    res = {"sessions_post_2021": int(post.sum()), "mnq_notional": notional, "drift": [], "cost": [],
           "budget": {}}
    for window, n in POLICIES:
        for s in DRIFTS:
            r = cell(H, L, C, notional, window, n, s, 2.32, rng)
            if s == 0.0:
                res["budget"][f"{window}_{n}"] = {"p_pass": r["_p"], "ev": r["ev"],
                                                  "by_k": budget(r["_p"], r["_payouts"], rng)}
            res["drift"].append({k: v for k, v in r.items() if not k.startswith("_")})
            print(f"drift {window} n={n} S={s:+.2f}: pass {r['p_pass']:.3f} EV {r['ev']:+.0f}", flush=True)
        for cst in COSTS:
            r = cell(H, L, C, notional, window, n, 0.0, cst, rng)
            res["cost"].append({k: v for k, v in r.items() if not k.startswith("_")})
            print(f"cost  {window} n={n} ${cst}: pass {r['p_pass']:.3f} EV {r['ev']:+.0f}", flush=True)
    return res


def render(r: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# Y01 sensitivity — drift, cost, and a budget of evaluations")
    a("")
    a("Generated by `python -m futuresres.reporting.y01_sensitivity`. Post-2021 MNQ sessions, the Y01 "
      "engine. A computation; no trial. `decisions.md` §79.")
    a("")
    a("## EV per $80 evaluation against an IMPOSED drift (long position's annual Sharpe), cost $2.32")
    a("")
    a("| policy | " + " | ".join(f"Sharpe {s:+.2f}" for s in DRIFTS) + " |")
    a("|---|" + "---|" * len(DRIFTS))
    for window, n in POLICIES:
        row = [c for c in r["drift"] if c["window"] == window and c["contracts"] == n]
        a(f"| {window}, {n} MNQ | " + " | ".join(f"{c['ev']:+,.0f} ({c['p_pass']:.0%})" for c in row) + " |")
    a("")
    a("## EV against the round-trip cost, zero drift")
    a("")
    a("| policy | " + " | ".join(f"${c:.2f}" for c in COSTS) + " |")
    a("|---|" + "---|" * len(COSTS))
    for window, n in POLICIES:
        row = [c for c in r["cost"] if c["window"] == window and c["contracts"] == n]
        a(f"| {window}, {n} MNQ | " + " | ".join(f"{c['ev']:+,.0f}" for c in row) + " |")
    a("")
    a("## A budget of K evaluations, zero drift, cost $2.32 — net of fees, over the funded accounts' 2 years")
    a("")
    for key, bdg in r["budget"].items():
        a(f"**{key.replace('_', ', ')} MNQ** (P(pass) {bdg['p_pass']:.1%}, EV {bdg['ev']:+.0f} per evaluation)")
        a("")
        a("| K | outlay | P(net > 0) | median | 5th pct | 95th pct | mean |")
        a("|---|---|---|---|---|---|---|")
        for k, v in bdg["by_k"].items():
            a(f"| {k} | ${v['outlay']:,.0f} | {v['p_net_positive']:.0%} | {v['median']:+,.0f} | {v['p05']:+,.0f} | "
              f"{v['p95']:+,.0f} | {v['mean']:+,.0f} |")
        a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.y01_sensitivity")
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args(argv)
    if args.log and OUT_JSON.exists():
        r = json.loads(OUT_JSON.read_text())
    else:
        r = run()
        OUT_JSON.write_text(json.dumps(r, indent=1, default=float) + "\n")
        r = json.loads(OUT_JSON.read_text())
    OUT_MD.write_text(render(r))
    print(OUT_MD.read_text())
    if args.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(
            trial_id=log.next_id("m"), hypothesis_id="Y-series", symbol="MNQ",
            date_range=("2021-01-01", "2026-08-27"), status="completed",
            params={"kind": "structure_ev_sensitivity", "drift": r["drift"], "cost": r["cost"],
                    "budget": r["budget"]},
            note=("kind=computation; NOT a trial and NOT counted in N. Y01 sensitivity to imposed drift "
                  "and cost, and a budget of evaluations. decisions.md 79."),
        ))
        print(f"logged {rec['trial_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
