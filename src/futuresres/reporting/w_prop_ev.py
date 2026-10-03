"""W-series success condition: expected value of one $80 prop evaluation, by Sharpe and size.

A COMPUTATION, not a hypothesis: it takes a return distribution as input and searches nothing about
the market (R06's reasoning, `r-series-research/reports/r06_eval_sizing.md`). Logs to
`measurements.jsonl` with `--log`.

    python -m futuresres.reporting.w_prop_ev
    python -m futuresres.reporting.w_prop_ev --log

THE ACCOUNT, as supplied by the user 2026-10-03 (decisions.md 73), and where it was ambiguous, the
reading used - each stated, none silently chosen:

  evaluation   start $50,000; pass at +$3,000. Trailing floor $2,000 below the INTRADAY equity peak,
               fixed at $50,000 once the peak reaches $52,000 (CHECKPOINT §1, §62).
  funded       starts again at $50,000 with the same floor rule. READING: "a $2k buffer before payout"
               means profits are withdrawable only above $52,000 - the lock point. Withdrawals are
               taken at each month end, of everything above $52,000; the trader keeps 90%.
  fee          $80 per evaluation; NO RESETS - a breach in either phase ends that account.
  daily loss   $1,000 from the day's starting equity. Modelled BOTH ways, because the brief does not
               say which applies: HARD (breach - the account ends) and SOFT (flat for the rest of the
               day). R06 found a daily limit, not the maximum drawdown, was what bound at one firm.
  horizon      the funded account is followed for at most 2 years; EV counts payouts within it.

THE RETURN MODEL. A daily-horizon strategy marked 13 times a session (the §62 intraday grid, 3,276
marks a year); innovations Student-t with nu = 5 (the §59 sensitivity value), scaled to the requested
daily dollar volatility; drift set by the annual Sharpe. Size enters ONLY as daily $ volatility: the
30-micro cap is not binding at any size the grid reaches (it would allow ~$15,000/day of sigma on MNQ).

VALIDATED BEFORE USE against the closed form: with no drift and no daily limit, P(peak +$2,000 before a
$2,000 trailing drawdown) is exp(-1) = 0.368 (§59), and from the lock, P(+$3,000 before $50,000) is 2/3,
so P(pass) -> 0.245 as marking tightens. The run refuses to report if the simulator misses those by
more than its own Monte Carlo error plus the known discrete-monitoring bias (§62: 0.372 at 52k marks).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Final

import numpy as np

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
OUT_JSON: Final[Path] = ROOT / "reports" / "w_prop_ev.json"
OUT_MD: Final[Path] = ROOT / "reports" / "w_prop_ev.md"

START: Final[float] = 50_000.0
TARGET: Final[float] = 3_000.0
TRAIL: Final[float] = 2_000.0
LOCK: Final[float] = 2_000.0
DAILY_LIMIT: Final[float] = 1_000.0
FEE: Final[float] = 80.0
SPLIT: Final[float] = 0.90
MARKS: Final[int] = 13
NU: Final[float] = 5.0
EVAL_MAX_DAYS: Final[int] = 252            # an evaluation not passed in a year counts as failed
FUNDED_DAYS: Final[int] = 504
MONTH: Final[int] = 21

SHARPES: Final[tuple[float, ...]] = (0.0, 0.4, 0.7, 1.0, 1.25, 1.5, 2.0)
DAILY_SIGMAS: Final[tuple[float, ...]] = (100, 150, 250, 400, 600, 900)


def _steps(rng, n_paths: int, n_days: int, sigma_day: float, sharpe: float) -> np.ndarray:
    """P&L per mark, shape (paths, days, marks). t innovations rescaled to unit variance."""
    t = rng.standard_t(NU, size=(n_paths, n_days, MARKS)) / math.sqrt(NU / (NU - 2))
    sd = sigma_day / math.sqrt(MARKS)
    mu = sharpe / math.sqrt(252) * sigma_day / MARKS
    return mu + sd * t


def simulate_eval(rng, n: int, sigma_day: float, sharpe: float, hard_daily: bool,
                  daily_limit: bool = True) -> dict:
    eq = np.full(n, START); peak = eq.copy(); alive = np.ones(n, bool)
    passed = np.zeros(n, bool); days_to_pass = np.full(n, np.nan)
    chunk = 63
    for d0 in range(0, EVAL_MAX_DAYS, chunk):
        steps = _steps(rng, n, min(chunk, EVAL_MAX_DAYS - d0), sigma_day, sharpe)
        for d in range(steps.shape[1]):
            day_open = eq.copy(); paused = np.zeros(n, bool)
            for m in range(MARKS):
                act = alive & ~passed & ~paused
                eq = np.where(act, eq + steps[:, d, m], eq)
                peak = np.maximum(peak, eq)
                floor = np.where(peak >= START + LOCK, START, peak - TRAIL)
                broke = act & (eq <= floor)
                alive &= ~broke
                hit = act & ~broke & (eq >= START + TARGET)
                passed |= hit
                days_to_pass = np.where(hit & np.isnan(days_to_pass), d0 + d + 1, days_to_pass)
                if daily_limit:
                    over = act & ~broke & ~hit & (eq <= day_open - DAILY_LIMIT)
                    if hard_daily:
                        alive &= ~over
                    else:
                        paused |= over
        if not (alive & ~passed).any():
            break
    return {"p_pass": float(passed.mean()), "median_days": float(np.nanmedian(days_to_pass))
            if passed.any() else float("nan")}


def simulate_funded(rng, n: int, sigma_day: float, sharpe: float, hard_daily: bool) -> dict:
    eq = np.full(n, START); peak = eq.copy(); alive = np.ones(n, bool)
    paid = np.zeros(n); chunk = 63
    for d0 in range(0, FUNDED_DAYS, chunk):
        steps = _steps(rng, n, min(chunk, FUNDED_DAYS - d0), sigma_day, sharpe)
        for d in range(steps.shape[1]):
            day_open = eq.copy(); paused = np.zeros(n, bool)
            for m in range(MARKS):
                act = alive & ~paused
                eq = np.where(act, eq + steps[:, d, m], eq)
                peak = np.maximum(peak, eq)
                floor = np.where(peak >= START + LOCK, START, peak - TRAIL)
                broke = act & (eq <= floor)
                alive &= ~broke
                over = act & ~broke & (eq <= day_open - DAILY_LIMIT)
                if hard_daily:
                    alive &= ~over
                else:
                    paused |= over
            if (d0 + d + 1) % MONTH == 0:
                excess = np.where(alive, np.maximum(eq - (START + LOCK), 0.0), 0.0)
                paid += SPLIT * excess
                eq -= excess
        if not alive.any():
            break
    return {"expected_payout": float(paid.mean()), "p_survive": float(alive.mean())}


def validate(rng) -> dict:
    """No drift, no daily limit: P(pass) should approach exp(-1) * 2/3 = 0.245."""
    n = 40_000
    r = simulate_eval(rng, n, 400.0, 0.0, hard_daily=True, daily_limit=False)
    target = math.exp(-1) * 2 / 3
    mc = 2 * math.sqrt(target * (1 - target) / n)
    # discrete monitoring overstates survival slightly (§62: 0.372 vs 0.368 at 52k marks; ours is coarser)
    ok = abs(r["p_pass"] - target) <= mc + 0.02
    return {"p_pass": r["p_pass"], "closed_form": target, "tolerance": mc + 0.02, "ok": ok}


def run(n: int = 6_000, seed: int = 20261003) -> dict:
    rng = np.random.default_rng(seed)
    val = validate(rng)
    if not val["ok"]:
        raise SystemExit(f"simulator fails validation: {val}")
    grid = []
    for hard in (True, False):
        for s in SHARPES:
            for sig in DAILY_SIGMAS:
                e = simulate_eval(rng, n, sig, s, hard)
                f = simulate_funded(rng, n, sig, s, hard)
                ev = e["p_pass"] * f["expected_payout"] - FEE
                grid.append({"daily_limit": "hard" if hard else "soft", "sharpe": s,
                             "daily_sigma": sig, **e, **f, "ev": ev})
                print(f"{'hard' if hard else 'soft'} S={s:<4} sigma={sig:<4} pass {e['p_pass']:.3f} "
                      f"payout {f['expected_payout']:8.0f} EV {ev:+8.0f}", flush=True)
    return {"validation": val, "n_paths": n, "grid": grid}


def render(r: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# W-series success condition — EV of one $80 evaluation")
    a("")
    a("Generated by `python -m futuresres.reporting.w_prop_ev`. A computation, no trial. Terms and "
      "readings in the module docstring; `decisions.md` §73.")
    a("")
    v = r["validation"]
    a(f"**Validated first:** no drift, no daily limit, P(pass) {v['p_pass']:.3f} against the closed form "
      f"exp(−1)·2/3 = {v['closed_form']:.3f} (tolerance {v['tolerance']:.3f}).")
    a("")
    for lim in ("hard", "soft"):
        a(f"## Daily loss limit {lim.upper()} — EV per evaluation (USD), by Sharpe and daily $σ")
        a("")
        a("| Sharpe | " + " | ".join(f"σ ${s}/day" for s in DAILY_SIGMAS) + " | best |")
        a("|---|" + "---|" * (len(DAILY_SIGMAS) + 1))
        for s in SHARPES:
            row = [g for g in r["grid"] if g["daily_limit"] == lim and g["sharpe"] == s]
            best = max(row, key=lambda g: g["ev"])
            a(f"| {s} | " + " | ".join(f"{g['ev']:+,.0f} ({g['p_pass']:.0%})" for g in row)
              + f" | **{best['ev']:+,.0f}** at ${best['daily_sigma']} |")
        a("")
        a("Cells: EV (P(pass)). EV = P(pass) × expected 2-year payout − $80.")
        a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.w_prop_ev")
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args(argv)
    if args.log and OUT_JSON.exists():
        r = json.loads(OUT_JSON.read_text())
    else:
        r = run()
        OUT_JSON.write_text(json.dumps(r, indent=1) + "\n")
    OUT_MD.write_text(render(r))
    print(f"wrote {OUT_JSON.name}, {OUT_MD.name}")
    if args.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        best = {f"{g['daily_limit']}_S{g['sharpe']}": round(g["ev"], 1) for g in r["grid"]
                if g["daily_sigma"] == 400}
        rec = log.append(Trial(
            trial_id=log.next_id("m"), hypothesis_id="W-series", symbol="account",
            date_range=("n/a", "n/a"), status="completed",
            params={"kind": "prop_eval_ev", "validation": r["validation"], "ev_at_400": best},
            note=("kind=computation; NOT a trial and NOT counted in N. W-series success condition: "
                  "EV of one $80 evaluation by Sharpe and size, this account's terms. "
                  "decisions.md 73."),
        ))
        print(f"logged {rec['trial_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
