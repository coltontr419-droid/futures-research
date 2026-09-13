"""Q09: survival under the CONFIRMED drawdown rule, against the ASSUMED one it replaces.

NOT A HYPOTHESIS. NO MARKET DATA, NO TRIALS. Given a Sharpe and a sizing it computes
P(reach a target before a drawdown), which is a first-passage problem with a known answer.
Same standing as R06 (r-series), which logs to measurements.jsonl for the same reason.

THE RULE, CONFIRMED WITH THE FIRM (decisions.md §59). The floor starts 4% below the starting
balance and trails the running equity peak. It stops trailing when it reaches the starting
balance - which happens when the PEAK reaches +4% - and then sits at breakeven permanently.

THE RULE THE HANDOFF ASSUMED. 4% trailing until +10% is made, then static at +6%. Its Phase 1
table is reproduced below from the same formula, both to show where it came from and so it
reads as superseded rather than lost.

THE FORMULA. For X_t = mu*t + sigma*W_t with running maximum M_t, the maximum reached before
the first drawdown of size d is exponential (Taylor 1975; Lehoczky 1977):

    P(M reaches a before a drawdown of d) = exp(-a / m(d)),  m(d) = (exp(g*d) - 1) / g
    g = 2*mu / sigma^2                                          m(d) -> d as mu -> 0

So a driftless walk reaches +4% before a 4% TRAILING drawdown with probability exp(-1) = 36.8%,
not the 50% of the static gambler's-ruin problem: a trailing floor follows every new high up.
Formula recalled from the literature and therefore VERIFIED here by Monte Carlo rather than
trusted, and checked against the handoff's own figures, which it must reproduce exactly.

SIZING CONVENTION, kept from the handoff for comparability: "sized m per month" means the
expected return is m per month at that Sharpe, so annual vol is 12*m / Sharpe. A second table
fixes VOLATILITY instead and varies Sharpe, because that is the comparison the ordering
question actually needs - the first convention lets sizing and edge move together.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Final

import numpy as np
from scipy.stats import t as student_t

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
OUT: Final[Path] = ROOT / "reports" / "q09_drawdown.json"

DRAWDOWN: Final[float] = 0.04
TARGET_CONFIRMED: Final[float] = 0.04      # peak +4% locks the floor at breakeven
TARGET_ASSUMED: Final[float] = 0.10        # the handoff's +10%, superseded

SHARPES: Final[tuple[float, ...]] = (1.0, 1.5, 2.1)
MONTHLY: Final[tuple[float, ...]] = (0.01, 0.005, 0.0025)

#: The programme's measured cadence, ~2,000 trades a year. Used only to discretise the Monte
#: Carlo; the analytic formula is continuous.
TRADES_PER_YEAR: Final[int] = 2000

#: The handoff's Phase 1 table, as printed. The formula must reproduce these or the
#: comparison below is not like for like.
HANDOFF_TABLE: Final[dict[tuple[float, float], float]] = {
    (1.0, 0.01): 0.17, (1.0, 0.005): 0.30, (1.0, 0.0025): 0.61,
    (1.5, 0.01): 0.34, (1.5, 0.005): 0.46, (1.5, 0.0025): 0.83,
    (2.1, 0.01): 0.64, (2.1, 0.005): 0.76, (2.1, 0.0025): 0.95,
}


def gamma(sharpe: float, sigma: float) -> float:
    return 2.0 * sharpe / sigma


def p_reach_before_trailing(a: float, d: float, sharpe: float, sigma: float) -> float:
    """P(peak reaches +a before any peak-to-trough drawdown of d). Continuous, Gaussian."""
    g = gamma(sharpe, sigma)
    mean_max = d if abs(g * d) < 1e-12 else math.expm1(g * d) / g
    return math.exp(-a / mean_max)


def p_ruin_static(cushion: float, sharpe: float, sigma: float) -> float:
    """P(EVER falling `cushion` below the current level) with a STATIC floor, fixed sizing."""
    if sharpe <= 0:
        return 1.0
    return math.exp(-gamma(sharpe, sigma) * cushion)


def monte_carlo(a: float, d: float, sharpe: float, sigma: float, *, paths: int,
                years: float, nu: float | None, seed: int) -> dict[str, float]:
    """Trade-by-trade first passage with an INTRADAY-granular trailing peak.

    `nu=None` is Gaussian and should agree with the formula. A finite `nu` draws Student-t
    trade returns scaled to the same variance, because barrier problems are dominated by tails
    and the formula is not. Paths still unresolved at the horizon are reported, not dropped.
    """
    rng = np.random.default_rng(seed)
    n = int(years * TRADES_PER_YEAR)
    drift = sharpe * sigma / TRADES_PER_YEAR
    vol = sigma / math.sqrt(TRADES_PER_YEAR)
    x = np.zeros(paths)
    peak = np.zeros(paths)
    done = np.zeros(paths, dtype=bool)
    win = np.zeros(paths, dtype=bool)
    t_hit = np.full(paths, np.nan)
    scale = 1.0 if nu is None else math.sqrt((nu - 2.0) / nu)
    for step in range(n):
        live = ~done
        if not live.any():
            break
        k = int(live.sum())
        z = rng.standard_normal(k) if nu is None else rng.standard_t(nu, k) * scale
        x[live] += drift + vol * z
        peak[live] = np.maximum(peak[live], x[live])
        lost = live & (peak - x >= d)
        won = live & ~lost & (peak >= a)
        done |= lost | won
        win |= won
        t_hit[won] = (step + 1) / TRADES_PER_YEAR
    return {
        "p_reach": float(win.mean()),
        "unresolved": float((~done).mean()),
        "median_years_to_lock": float(np.nanmedian(t_hit)) if win.any() else float("nan"),
        # P(reach the target WITHIN h years), from the same paths - how a finite horizon
        # would have been read, which is the candidate explanation for the handoff's table
        "p_within": {str(h): float(np.mean(win & (t_hit <= h))) for h in (0.5, 1, 2, 3, 5)
                     if h <= years},
    }


def main() -> int:
    out: dict[str, object] = {}

    # ---- 1. provenance: does the formula reproduce the handoff's table? -------------------
    print("=" * 84)
    print("1. THE SUPERSEDED TABLE - assumed rule, target +10% before a 4% trailing drawdown")
    print("=" * 84)
    print(f"{'Sharpe':>7} {'1%/mo':>16} {'0.5%/mo':>16} {'0.25%/mo':>16}")
    superseded, worst = {}, 0.0
    for s in SHARPES:
        row = []
        for m in MONTHLY:
            p = p_reach_before_trailing(TARGET_ASSUMED, DRAWDOWN, s, 12 * m / s)
            superseded[f"{s}|{m}"] = p
            worst = max(worst, abs(round(p, 2) - HANDOFF_TABLE[(s, m)]))
            row.append(f"{p:6.1%} (was {HANDOFF_TABLE[(s, m)]:.0%})")
        print(f"{s:>7.1f} " + " ".join(f"{c:>16}" for c in row))
    print(f"   largest disagreement with the handoff after rounding: {worst:.2f}")
    out["superseded_table"] = superseded
    out["handoff_reproduced_max_abs_diff"] = worst

    # ---- 1b. can a FINITE horizon reproduce the cells the formula does not? ------------------
    # The infinite-horizon formula matches the handoff where the target is reached quickly and
    # overstates it where sizing is small, which is the signature of a time limit. Tested, not
    # assumed: one Monte Carlo per cell, read at several horizons from the same paths.
    print("\n   1b. P(+10% within h years) - does any horizon reproduce the handoff?")
    print(f"{'cell':>16} {'handoff':>8} " + " ".join(f"{'h=' + str(h):>7}" for h in (0.5, 1, 2, 3, 5))
          + f" {'inf':>7}")
    finite = {}
    for s in SHARPES:
        for m in MONTHLY:
            res = monte_carlo(TARGET_ASSUMED, DRAWDOWN, s, 12 * m / s, paths=10000, years=5,
                              nu=None, seed=11)
            finite[f"{s}|{m}"] = res["p_within"]
            cells = " ".join(f"{res['p_within'][str(h)]:>7.1%}" for h in (0.5, 1, 2, 3, 5))
            print(f"{'S=' + str(s) + ' ' + format(m, '.2%'):>16} {HANDOFF_TABLE[(s, m)]:>8.0%} "
                  f"{cells} {superseded[f'{s}|{m}']:>7.1%}")
    best_h, best_err = None, 9.0
    for h in (0.5, 1, 2, 3, 5):
        err = max(abs(finite[f"{s}|{m}"][str(h)] - HANDOFF_TABLE[(s, m)])
                  for s in SHARPES for m in MONTHLY)
        if err < best_err:
            best_h, best_err = h, err
    print(f"   best single horizon: h={best_h} years, worst cell error {best_err:.2f}")
    out["superseded_finite_horizon"] = {"cells": finite, "best_h": best_h,
                                        "best_h_max_abs_err": best_err}

    # ---- 2. the corrected table ------------------------------------------------------------
    print("\n" + "=" * 84)
    print("2. THE CORRECTED TABLE - confirmed rule, peak +4% before a 4% trailing drawdown")
    print("=" * 84)
    print(f"{'Sharpe':>7} {'1%/mo':>9} {'0.5%/mo':>9} {'0.25%/mo':>9}   {'yrs to +4% at drift':>20}")
    corrected = {}
    for s in SHARPES:
        cells = []
        for m in MONTHLY:
            p = p_reach_before_trailing(TARGET_CONFIRMED, DRAWDOWN, s, 12 * m / s)
            corrected[f"{s}|{m}"] = p
            cells.append(p)
        drift_years = " / ".join(f"{TARGET_CONFIRMED / (12 * m):.1f}" for m in MONTHLY)
        print(f"{s:>7.1f} " + " ".join(f"{c:>9.1%}" for c in cells) + f"   {drift_years:>20}")
    zero = math.exp(-TARGET_CONFIRMED / DRAWDOWN)
    print(f"{'0.0':>7} {zero:>9.1%} {zero:>9.1%} {zero:>9.1%}   (no drift: exp(-1), ANY sizing)")
    out["corrected_table"] = corrected
    out["driftless_any_sizing"] = zero

    # ---- 3. the Monte Carlo check -----------------------------------------------------------
    print("\n" + "=" * 84)
    print("3. VERIFICATION - trade-by-trade Monte Carlo, 20,000 paths, 10-year horizon")
    print("=" * 84)
    print(f"{'cell':>18} {'formula':>8} {'Gaussian':>9} {'t(nu=5)':>9} {'t(nu=4.05)':>11} "
          f"{'median yrs to lock':>19}")
    mc = {}
    for s, m in ((1.0, 0.01), (1.5, 0.005), (1.5, 0.0025), (2.1, 0.0025), (0.0, None)):
        sigma = 12 * m / s if m else 0.06
        label = f"S={s} {m:.2%}/mo" if m else "S=0 vol 6%/yr"
        f = p_reach_before_trailing(TARGET_CONFIRMED, DRAWDOWN, s, sigma)
        g = monte_carlo(TARGET_CONFIRMED, DRAWDOWN, s, sigma, paths=20000, years=10,
                        nu=None, seed=1)
        t5 = monte_carlo(TARGET_CONFIRMED, DRAWDOWN, s, sigma, paths=20000, years=10,
                         nu=5.0, seed=2)
        t4 = monte_carlo(TARGET_CONFIRMED, DRAWDOWN, s, sigma, paths=20000, years=10,
                         nu=4.05, seed=3)
        mc[label] = {"formula": f, "gaussian": g, "t5": t5, "t405": t4}
        print(f"{label:>18} {f:>8.1%} {g['p_reach']:>9.1%} {t5['p_reach']:>9.1%} "
              f"{t4['p_reach']:>11.1%} {g['median_years_to_lock']:>19.2f}")
    out["monte_carlo"] = mc

    # ---- 4. sizing lever vs edge lever, at fixed volatility -----------------------------------
    print("\n" + "=" * 84)
    print("4. SIZING vs EDGE - Phase 1 survival at FIXED annual volatility")
    print("=" * 84)
    vols = (0.12, 0.08, 0.04, 0.02)
    print(f"{'Sharpe':>7} " + " ".join(f"{'vol ' + format(v, '.0%'):>10}" for v in vols))
    grid = {}
    for s in (0.0, 0.5, 1.0, 1.5, 2.1):
        row = [p_reach_before_trailing(TARGET_CONFIRMED, DRAWDOWN, s, v) for v in vols]
        grid[str(s)] = row
        print(f"{s:>7.1f} " + " ".join(f"{p:>10.1%}" for p in row))
    out["fixed_vol_grid"] = {"vols": list(vols), "rows": grid}

    # ---- 5. Phase 2: a static floor at breakeven ---------------------------------------------
    print("\n" + "=" * 84)
    print("5. PHASE 2 - floor static at breakeven; cushion = accumulated profit")
    print("=" * 84)
    print("   P(ever breaching) with FIXED sizing, cushion 4% at the moment of lock:")
    print(f"{'Sharpe':>7} {'size':>9} {'1x':>8} {'2x':>8} {'3x':>8} {'4x':>8}")
    phase2 = {}
    for s in SHARPES:
        for m in (0.005, 0.0025):
            sigma = 12 * m / s
            row = [p_ruin_static(DRAWDOWN, s, k * sigma) for k in (1, 2, 3, 4)]
            phase2[f"{s}|{m}"] = row
            print(f"{s:>7.1f} {m:>8.2%} " + " ".join(f"{p:>8.1%}" for p in row))
    out["phase2_step_up_at_lock"] = phase2

    print("\n   Cushion-proportional sizing: holding breach probability at its 1x-at-lock value "
          "needs size proportional to cushion, so")
    for k in (2, 3, 4):
        print(f"     {k}x the Phase 1 size is earned at a cushion of {k * DRAWDOWN:.0%} "
              f"(equity +{k * DRAWDOWN:.0%})")

    print("\n   Gap risk under cushion-proportional sizing: a breach then needs ONE trade to lose")
    print("   more than the cushion. At Phase 1 sizing that is a single-trade loss of 4% of equity:")
    tail = {}
    for s, m in ((1.5, 0.005), (1.5, 0.0025), (2.1, 0.0025)):
        per_trade_sd = (12 * m / s) / math.sqrt(TRADES_PER_YEAR)
        z = DRAWDOWN / per_trade_sd
        row = {}
        for nu in (5.0, 4.05):
            scale = math.sqrt(nu / (nu - 2.0))
            p1 = float(student_t.cdf(-z * scale, nu))
            p5y = 1.0 - (1.0 - p1) ** (5 * TRADES_PER_YEAR)
            row[str(nu)] = {"z": z, "p_per_trade": p1, "p_over_5_years": p5y}
        tail[f"{s}|{m}"] = row
        print(f"     S={s} {m:.2%}/mo: {z:.0f} trade-sd; P(over 5 yrs) t5 "
              f"{row['5.0']['p_over_5_years']:.2e}, t4.05 {row['4.05']['p_over_5_years']:.2e}")
    out["phase2_gap_risk"] = tail

    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
