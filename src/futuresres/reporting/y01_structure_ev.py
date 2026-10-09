"""Y01 - the account structure on real price paths: what one $80 evaluation is worth at ZERO edge.

A COMPUTATION on the account's rules driven by real intraday noise. NO STRATEGY RETURN and no market
claim: every session's drift is removed before use, so a positive result can only come from the payoff
structure (the firm absorbs losses beyond the fee), never from a predicted direction. No trial is spent;
`--log` writes one record to measurements.jsonl. decisions.md 79.

    python -m futuresres.reporting.y01_structure_ev --validate     # engine against the closed form
    python -m futuresres.reporting.y01_structure_ev                # the grid (one product per process)
    python -m futuresres.reporting.y01_structure_ev --log

WHY REAL PATHS. `w_prop_ev` (decisions.md 73) found positive zero-edge EV under a Student-t daily model
marked 13 times a session. What it could not see: overnight reopen gaps, the intraday excursion that
breaches a trailing floor evaluated on equity, where a soft daily limit actually triggers, and the true
round trip. This module replaces the model with resampled MNQ sessions.

THE PATHS. NQ->MNQ spliced 1-minute bars (data/continuous). A session is the CME trading day; a
position is held inside a WINDOW of it and flat outside (always flat 16:55-18:00, the firm's rule).
Complete sessions only: first print within 5 minutes of 18:00 ET and a print within 5 minutes of 16:55
(the U01 rule, decisions.md 67). Each session's path is taken in RETURNS relative to its entry and
rescaled to one MNQ at today's notional, so 2010 and 2026 sessions describe the same contract.
DRIFT REMOVED: the era's mean window return is subtracted linearly across the window. A PREMIUM variant
re-adds a drift fixed from an EXTERNAL prior (labelled), never from this data's own mean.

THE ACCOUNT (user, 2026-10-03; decisions.md 73, 75). Start $50,000; pass at +$3,000; trailing floor
$2,000 below the INTRADAY equity peak, fixed at $50,000 once the peak reaches $52,000; daily loss limit
$1,000 SOFT (flat for the rest of the day); no resets; fee $80. Funded: restarts at $50,000 under the same
floor rule; everything above $52,000 withdrawn every 21 sessions, 90% to the trader. ASSUMED, not
supplied: an evaluation not passed in 252 sessions fails; the funded account is followed 504 sessions.

INTRABAR ORDER. A bar's high and low arrive in unknown order. The floor is tested against the bar's LOW
using the peak through the PREVIOUS bar, and the peak then updates with this bar's HIGH; the target is
tested against the HIGH. A stop fills at its level (the soft limit at -$1,000 less one tick per contract).

COST. One MNQ round trip per contract per session held, $2.32 (X01: $1.82 commission assumed + one
tick, decisions.md 77), charged at the exit and counted against the floor.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
SERIES: Final[Path] = ROOT / "data" / "continuous" / "NQ_MNQ_spliced.parquet"
OUT_JSON: Final[Path] = ROOT / "reports" / "y01_structure_ev.json"
OUT_MD: Final[Path] = ROOT / "reports" / "y01_structure_ev.md"

START: Final[float] = 50_000.0
TARGET: Final[float] = 3_000.0
TRAIL: Final[float] = 2_000.0
LOCK: Final[float] = 2_000.0
DAILY: Final[float] = 1_000.0
FEE: Final[float] = 80.0
SPLIT: Final[float] = 0.90
EVAL_DAYS: Final[int] = 252
FUNDED_DAYS: Final[int] = 504
MONTH: Final[int] = 21
RT_COST: Final[float] = 2.32
TICK_USD: Final[float] = 0.50
MULT: Final[float] = 2.0                         # MNQ $ per index point
CHUNK: Final[int] = 800
SESSION_MIN: Final[int] = 1375                   # 18:00 ET -> 16:55 ET
WINDOWS: Final[dict[str, tuple[int, int]]] = {
    "full": (0, 1375),                           # 18:00 -> 16:55
    "overnight": (0, 930),                       # 18:00 -> 09:30
    "rth": (930, 1320),                          # 09:30 -> 16:00
}
ERA: Final = np.datetime64("2021-01-01")
#: EXTERNAL prior for the premium variant: a long equity-index position's long-run annual Sharpe.
#: Labelled assumption, ~0.3 (century-scale US equity premium, conservatively); NOT measured here.
PREMIUM_SHARPE: Final[float] = 0.3


# --------------------------------------------------------------------------- paths
def load_sessions() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    """(dates, H, L, C) as float32 [S, 1375] returns-relative-to-the-18:00-open, complete sessions only,
    plus today's MNQ notional. Bars outside the session window are dropped."""
    et = pl.col("ts_event").dt.convert_time_zone("America/New_York")
    mod = ((et.dt.hour().cast(pl.Int32) * 60 + et.dt.minute().cast(pl.Int32) - 1080) % 1440)
    df = (pl.scan_parquet(SERIES).select("ts_event", "session", "open", "high", "low", "close")
            .with_columns(mod.alias("m")).filter(pl.col("m") < SESSION_MIN)
            .sort("ts_event").collect())
    sess = df["session"].to_numpy()
    m = df["m"].to_numpy()
    keys, start_idx = np.unique(sess, return_index=True)
    bounds = np.r_[start_idx, len(sess)]
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    keep_dates, H, L, C = [], [], [], []
    for s in range(len(keys)):
        a, b = bounds[s], bounds[s + 1]
        mm = m[a:b]
        if mm[0] > 5 or mm[-1] < SESSION_MIN - 5:
            continue
        p0 = o[a]
        hh = np.full(SESSION_MIN, np.nan); ll = hh.copy(); cc = hh.copy()
        hh[mm] = h[a:b]; ll[mm] = l[a:b]; cc[mm] = c[a:b]
        cc = _ffill(cc, p0)
        hh = np.where(np.isnan(hh), cc, hh); ll = np.where(np.isnan(ll), cc, ll)
        H.append(hh / p0 - 1); L.append(ll / p0 - 1); C.append(cc / p0 - 1)
        keep_dates.append(keys[s])
    notional = float(c[-1]) * MULT
    return (np.array(keep_dates, dtype="datetime64[D]"), np.array(H, np.float32),
            np.array(L, np.float32), np.array(C, np.float32), notional)


def _ffill(x: np.ndarray, first: float) -> np.ndarray:
    if np.isnan(x[0]):
        x[0] = first
    idx = np.where(np.isnan(x), 0, np.arange(len(x)))
    np.maximum.accumulate(idx, out=idx)
    return x[idx]


def window_paths(H, L, C, window: str, drift_per_session: float | None):
    """Per-session $ P&L paths of ONE contract inside the window, relative to the window's entry,
    drift removed (and optionally a fixed premium drift re-added)."""
    a, b = WINDOWS[window]
    base = np.ones(len(C), np.float32) if a == 0 else (1 + C[:, a - 1])
    h = (1 + H[:, a:b]) / base[:, None] - 1
    l = (1 + L[:, a:b]) / base[:, None] - 1
    c = (1 + C[:, a:b]) / base[:, None] - 1
    w = b - a
    ramp = np.arange(1, w + 1, dtype=np.float32) / w
    mu = float(c[:, -1].mean())
    adj = (-mu + (drift_per_session or 0.0)) * ramp
    return h + adj, l + adj, c + adj, mu


# --------------------------------------------------------------------------- the account
def _day(eq, peak, locked_floor, h, l, c, n, target: float | None):
    """One session for every live account. eq/peak (A,), paths (A, W) in $ for n contracts.
    Returns new eq, peak, and flags (breached, passed)."""
    A, W = c.shape
    E0 = eq[:, None]
    hi = E0 + h * n; lo = E0 + l * n; cl = E0 + c * n
    prev_peak = np.maximum(peak[:, None], np.concatenate([E0, np.maximum.accumulate(hi, axis=1)[:, :-1]], axis=1))
    floor = np.where(prev_peak >= START + LOCK, START, prev_peak - TRAIL)
    breach = lo <= floor
    stop = lo <= E0 - DAILY                                # soft daily limit
    hit = (hi >= START + TARGET) if target is not None else np.zeros_like(breach)
    big = W + 1
    t_b = np.where(breach.any(1), breach.argmax(1), big)
    t_s = np.where(stop.any(1), stop.argmax(1), big)
    t_h = np.where(hit.any(1), hit.argmax(1), big)
    t = np.minimum(np.minimum(t_b, t_s), t_h)
    rows = np.arange(A)
    ended = t < big
    tt = np.where(ended, t, W - 1)
    exit_eq = cl[rows, W - 1].copy()
    # same-bar ties: breach first (conservative), then the daily stop, then the target
    is_b = ended & (t_b == t)
    is_s = ended & ~is_b & (t_s == t)
    is_h = ended & ~is_b & ~is_s & (t_h == t)
    exit_eq[is_b] = np.minimum(floor[rows, tt], lo[rows, tt])[is_b]
    exit_eq[is_s] = (eq - DAILY - TICK_USD * n)[is_s]
    exit_eq[is_h] = (START + TARGET)
    run_peak = np.maximum(prev_peak[rows, tt], np.where(is_b | is_s, prev_peak[rows, tt], hi[rows, tt]))
    full_peak = np.maximum(peak, hi.max(1))
    new_peak = np.where(ended, run_peak, full_peak)
    new_eq = exit_eq - RT_COST * n
    # the cost can itself breach: re-test the end-of-day equity against the floor
    fl_end = np.where(new_peak >= START + LOCK, START, new_peak - TRAIL)
    breached = is_b | (new_eq <= fl_end)
    passed = is_h & ~breached
    return new_eq, new_peak, breached, passed


def simulate(paths, n: int, accounts: int, rng, eval_phase: bool, days: int) -> dict:
    h_all, l_all, c_all = paths
    S = len(c_all)
    eq = np.full(accounts, START); peak = eq.copy()
    alive = np.ones(accounts, bool); passed = np.zeros(accounts, bool)
    paid = np.zeros(accounts); days_used = np.zeros(accounts)
    for d in range(days):
        act = np.flatnonzero(alive & ~passed)
        if not len(act):
            break
        idx = rng.integers(0, S, len(act))
        for k in range(0, len(act), CHUNK):            # bounded memory on the 2.7 GB machine
            a_, i_ = act[k:k + CHUNK], idx[k:k + CHUNK]
            ne, npk, br, ps = _day(eq[a_], peak[a_], None, h_all[i_], l_all[i_], c_all[i_], n,
                                   TARGET if eval_phase else None)
            eq[a_] = ne; peak[a_] = npk; days_used[a_] += 1
            alive[a_[br]] = False
            passed[a_[ps]] = True
        if not eval_phase and (d + 1) % MONTH == 0:
            live = alive
            excess = np.where(live, np.maximum(eq - (START + LOCK), 0.0), 0.0)
            paid += SPLIT * excess
            eq -= excess
    out = {"days_mean": float(days_used.mean())}
    if eval_phase:
        out["p_pass"] = float(passed.mean())
    else:
        out["expected_payout"] = float(paid.mean())
        out["p_alive_at_end"] = float(alive.mean())
    return out


def evaluate(paths, n: int, rng, accounts: int = 4000) -> dict:
    e = simulate(paths, n, accounts, rng, True, EVAL_DAYS)
    f = simulate(paths, n, accounts, rng, False, FUNDED_DAYS)
    return {**e, **f, "ev": e["p_pass"] * f["expected_payout"] - FEE,
            "mc_se_p_pass": math.sqrt(e["p_pass"] * (1 - e["p_pass"]) / accounts)}


# --------------------------------------------------------------------------- validation
def validate(seed: int = 1) -> dict:
    """Gaussian random-walk minute paths, no drift. With the daily limit and cost disabled the
    evaluation must pass ~exp(-1)*2/3 = 0.245 (continuous closed form; minute marking is close to it)."""
    global DAILY, RT_COST
    rng = np.random.default_rng(seed)
    S, W = 3000, 1375
    steps = rng.normal(0, 1, (S, W)).astype(np.float32)
    c = np.cumsum(steps, axis=1)
    # a finite pool carries a residual drift (~$20/day here, an annual Sharpe of ~0.5), which moves
    # P(pass) from 0.22 to 0.29 on its own - so the pool is demeaned exactly, as the real paths are
    c -= c[:, -1].mean() * (np.arange(1, W + 1, dtype=np.float32) / W)
    c *= 600.0 / c[:, -1].std()                            # one contract ~ $600 a day
    paths = (c, c, c)
    saved = (DAILY, RT_COST)
    DAILY, RT_COST = 1e12, 0.0
    try:
        e = simulate(paths, 1, 6000, rng, True, EVAL_DAYS)
    finally:
        DAILY, RT_COST = saved
    target = math.exp(-1) * 2 / 3
    se = math.sqrt(target * (1 - target) / 6000)
    return {"p_pass": e["p_pass"], "closed_form": target, "tolerance": 3 * se + 0.01,
            "ok": abs(e["p_pass"] - target) <= 3 * se + 0.01}


# --------------------------------------------------------------------------- the grid
def run(seed: int = 20261009) -> dict:
    dates, H, L, C, notional = load_sessions()
    post = dates >= ERA
    res = {"sessions": int(len(dates)), "sessions_post_2021": int(post.sum()),
           "first": str(dates[0]), "last": str(dates[-1]), "mnq_notional": notional,
           "validation": validate(), "cells": []}
    if not res["validation"]["ok"]:
        raise SystemExit(f"engine fails validation: {res['validation']}")
    rng = np.random.default_rng(seed)
    full_sd = float((C[post, -1] * notional).std())
    premium = PREMIUM_SHARPE / math.sqrt(252) * float(C[:, -1].std())   # per session, in returns
    plan = [("full", n, "zero") for n in (1, 2)] + [("overnight", n, "zero") for n in (1, 2, 3)] + \
           [("rth", n, "zero") for n in (1, 2)] + [("full", 1, "premium")]
    for era_name, mask in (("pre_2021", ~post), ("post_2021", post)):
        for window, n, drift in plan:
            h, l, c, mu = window_paths(H[mask], L[mask], C[mask], window,
                                       premium if drift == "premium" else None)
            usd = (h * notional, l * notional, c * notional)
            sd_day = float(c[:, -1].std() * notional * n)
            r = evaluate(usd, n, rng)
            r.update({"era": era_name, "window": window, "contracts": n, "drift": drift,
                      "daily_sigma_usd": sd_day, "removed_mean_window_return": mu})
            res["cells"].append(r)
            print(f"{era_name:9} {window:9} n={n} {drift:7} sigma ${sd_day:6.0f}  pass {r['p_pass']:.3f}"
                  f"  payout {r['expected_payout']:7.0f}  EV {r['ev']:+6.0f}", flush=True)
    res["full_session_sigma_post_2021_one_mnq"] = full_sd
    return res


def render(r: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# Y01 — what one $80 evaluation is worth at zero edge, on real MNQ paths")
    a("")
    a("Generated by `python -m futuresres.reporting.y01_structure_ev`. A computation: drift removed from "
      "every session, no market claim, no trial. `decisions.md` §79.")
    a("")
    v = r["validation"]
    a(f"**Engine validated first:** Gaussian minute paths, no drift, no daily limit, no cost: P(pass) "
      f"{v['p_pass']:.3f} against exp(−1)·2/3 = {v['closed_form']:.3f} (tolerance {v['tolerance']:.3f}).")
    a("")
    a(f"Paths: {r['sessions']:,} complete sessions {r['first']} → {r['last']} ({r['sessions_post_2021']:,} "
      f"since 2021), rescaled to one MNQ at ${r['mnq_notional']:,.0f} notional. 4,000 accounts per cell.")
    a("")
    a("| era | window | MNQ | drift | daily $σ | P(pass) | E[payout] funded | EV per $80 |")
    a("|---|---|---|---|---|---|---|---|")
    for c in r["cells"]:
        a(f"| {c['era']} | {c['window']} | {c['contracts']} | {c['drift']} | {c['daily_sigma_usd']:,.0f} | "
          f"{c['p_pass']:.1%} ± {c['mc_se_p_pass']:.1%} | {c['expected_payout']:,.0f} | **{c['ev']:+,.0f}** |")
    a("")
    a("Zero drift: each session's window return is demeaned within its era, so these EVs come only from "
      "the payoff structure. Premium: a drift equal to an EXTERNAL annual Sharpe of "
      f"{PREMIUM_SHARPE} re-added (assumption, not measured here).")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.y01_structure_ev")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args(argv)
    if args.validate:
        print(json.dumps(validate(), indent=1))
        return 0
    if args.log and OUT_JSON.exists():
        r = json.loads(OUT_JSON.read_text())
    else:
        r = run()
        OUT_JSON.write_text(json.dumps(r, indent=1, default=float) + "\n")
    OUT_MD.write_text(render(r))
    print(OUT_MD.read_text())
    if args.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(
            trial_id=log.next_id("m"), hypothesis_id="Y-series", symbol="MNQ",
            date_range=(r["first"], r["last"]), status="completed",
            params={"kind": "structure_ev_real_paths", "validation": r["validation"],
                    "cells": [{k: c[k] for k in ("era", "window", "contracts", "drift", "daily_sigma_usd",
                                                 "p_pass", "expected_payout", "ev")} for c in r["cells"]]},
            note=("kind=computation; NOT a trial and NOT counted in N. Y01: zero-edge EV of one $80 "
                  "evaluation on resampled real MNQ sessions, drift removed. decisions.md 79."),
        ))
        print(f"logged {rec['trial_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
