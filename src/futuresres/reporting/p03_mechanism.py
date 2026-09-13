"""P03's horizon and magnitude, from the mechanism rather than from assumption.

**NO FORWARD RETURNS ARE READ.** Both quantities here are properties of the state and of the
series, measured before any horizon is chosen and before any effect is computed. The bar a
firing sits on is part of the state's own definition (|return| / volume is the observable);
nothing after it is touched.

WHY THIS EXISTS. §56 computed P03's S2 at an ASSUMED 180-minute horizon and against a
magnitude recalled from literature. Both inputs were unearned. R01's precedent (r-series
`decisions.md` §17) is the one being followed: the MNQ/MES deviation half-life was measured on
the series, the nearest grid horizon was taken, and the choice was recorded as data-informed
rather than as an out-of-sample prior.

THE ORDERING IS THE SAFEGUARD, AND IT IS THE WHOLE POINT. Choosing a horizon after seeing
which one clears the BH bar would be selecting a specification on the outcome - the same error
as tuning a threshold until a result appears. Here the horizon is fixed by the state's own
decay clock, the magnitude by the series' own impact relation, and only then is the bar
recomputed. **Neither measurement can see the bar**: no forward return, no effect, no
statistic exists when they run.

WHAT REPLACES THE RECALLED LITERATURE. §54's 1.0-4.0 bps came from a mechanistic sketch (a 5m
MNQ move has sd ~11 bps, a two-sigma thin move ~20 bps, 5-20% excess reversal) whose direction
was attributed to Campbell, Grossman and Wang (1993) - RECALLED, NOT CHECKED, and recorded as
such in §54. It is superseded here rather than dropped: the same mechanism (Amihud/Kyle) is
measured directly on this series, as the excess displacement a thin move carries over what its
own volume explains. That excess is the pool available to revert, so it is a CEILING: no
reversion strategy can return more than the move that was made.

The fraction of it that actually reverts is not measurable without forward returns, so it is
not guessed. What is reported instead is the REQUIRED REVERSION FRACTION - how much of the
measured excess P03 must recover to reach its BH bar - which is an interpretable number
carrying no invented constant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np

from futuresres.reporting.state_control_feasibility import build_state, load_bars

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
OUT: Final[Path] = ROOT / "reports" / "p03_mechanism.json"

BAR_MINUTES: Final[int] = 5

#: Horizons carried by registered entries in `hypotheses.yaml`. The nearest point on this grid
#: is taken, exactly as R01 took H=30 from an 8.3-minute half-life.
HORIZON_GRID: Final[tuple[int, ...]] = (15, 30, 60, 90, 120, 180, 240)

#: Bars of decay path to follow after a firing, within the same session.
MAX_LAG: Final[int] = 24


def decay_path(w: dict[str, np.ndarray]) -> tuple[np.ndarray, float, float]:
    """Mean elevation of the state variable at each lag after a firing, and its half-life.

    The state variable is log(illiquidity / its own trailing threshold), so zero is the
    threshold and the baseline is wherever ordinary bars sit. Elevation is measured against
    that baseline, and the half-life is where elevation falls to half its value at the firing.
    Paths never cross a session boundary.
    """
    lam = np.log(w["illiq"] / w["thresh"])
    usable = np.isfinite(lam) & (w["vol_q"] >= 0)
    sid, state = w["session"], w["state"] & usable

    baseline = float(np.mean(lam[usable & ~w["state"]]))
    fire = np.flatnonzero(state)
    path = np.full(MAX_LAG + 1, np.nan)
    for lag in range(MAX_LAG + 1):
        nxt = fire + lag
        ok = nxt < lam.size
        nxt = nxt[ok]
        same = sid[nxt] == sid[fire[ok]]
        vals = lam[nxt[same]]
        vals = vals[np.isfinite(vals)]
        if vals.size:
            path[lag] = float(vals.mean())

    elev = path - baseline
    half = elev[0] / 2.0
    hl_bars = float("nan")
    for lag in range(1, MAX_LAG + 1):
        if np.isfinite(elev[lag]) and elev[lag] <= half:
            # linear interpolation between the bracketing lags
            prev = elev[lag - 1]
            frac = (prev - half) / (prev - elev[lag]) if prev != elev[lag] else 0.0
            hl_bars = (lag - 1) + float(frac)
            break
    return elev, hl_bars, baseline


def impact_excess(w: dict[str, np.ndarray]) -> dict[str, float]:
    """How many bps of the firing bar's move its own volume does NOT explain.

    Amihud/Kyle: a move is bought with volume. Within each (year, time-of-day bucket) the
    relation log|return| = a + b log(volume) is fitted on ALL bars, which absorbs both the
    secular volume growth and the intraday shape. The fitted value is the move that bar's
    volume ordinarily buys; the residual in bps is the excess displacement a thin move carries.

    The fit is deliberately local in time. A single pooled regression would be dominated by
    the ~3x growth in bar volume across the sample and would misprice every era but the middle.
    """
    ret, vol = w["ret_bps"], w["volume"]
    ok = np.isfinite(ret) & (ret > 0) & (vol > 0) & (w["vol_q"] >= 0)
    logv, logr = np.full(ret.size, np.nan), np.full(ret.size, np.nan)
    logv[ok], logr[ok] = np.log(vol[ok]), np.log(ret[ok])

    expected = np.full(ret.size, np.nan)
    for y in np.unique(w["year"][ok]):
        for b in np.unique(w["tod"][ok]):
            cell = ok & (w["year"] == y) & (w["tod"] == b)
            n = int(cell.sum())
            if n < 100:
                continue
            x, yv = logv[cell], logr[cell]
            slope, intercept = np.polyfit(x, yv, 1)
            expected[cell] = np.exp(intercept + slope * x)

    fired = w["state"] & np.isfinite(expected)
    excess = ret[fired] - expected[fired]
    return {
        "n": int(fired.sum()),
        "median_move_bps": float(np.median(ret[fired])),
        "median_expected_bps": float(np.median(expected[fired])),
        "median_excess_bps": float(np.median(excess)),
        "q25_excess_bps": float(np.percentile(excess, 25)),
        "q75_excess_bps": float(np.percentile(excess, 75)),
        "mean_excess_bps": float(np.mean(excess)),
    }


def main() -> int:
    w = build_state(load_bars())

    print("=" * 78)
    print("P03 MECHANISM - horizon from the state's clock, magnitude from measured impact")
    print("=" * 78)

    elev, hl_bars, baseline = decay_path(w)
    print("\n1. REVERSION HALF-LIFE OF THE STATE (no forward returns; log illiquidity vs "
          "its own threshold)")
    print(f"   baseline elevation of an ordinary bar: {baseline:+.4f}")
    print(f"   {'lag (bars)':>11} {'minutes':>8} {'elevation':>11} {'vs lag 0':>9}")
    for lag in (0, 1, 2, 3, 4, 6, 8, 12, 18, 24):
        if lag <= MAX_LAG and np.isfinite(elev[lag]):
            print(f"   {lag:>11} {lag * BAR_MINUTES:>8} {elev[lag]:>11.4f} "
                  f"{elev[lag] / elev[0]:>9.2f}")
    hl_min = hl_bars * BAR_MINUTES
    print(f"\n   half-life {hl_bars:.2f} bars = {hl_min:.1f} minutes")
    chosen = min(HORIZON_GRID, key=lambda h: abs(h - hl_min))
    print(f"   nearest grid horizon: H = {chosen} "
          f"(grid {', '.join(str(h) for h in HORIZON_GRID)})")

    imp = impact_excess(w)
    print("\n2. PRICE IMPACT (no forward returns; log|ret| ~ log volume within year x bucket)")
    print(f"   firings fitted                {imp['n']:,}")
    print(f"   median move at a firing       {imp['median_move_bps']:.2f} bps")
    print(f"   median move its volume buys   {imp['median_expected_bps']:.2f} bps")
    print(f"   median EXCESS displacement    {imp['median_excess_bps']:.2f} bps "
          f"(IQR {imp['q25_excess_bps']:.2f}-{imp['q75_excess_bps']:.2f})")
    print("   -> the excess is the CEILING: no reversion returns more than the move made")

    OUT.write_text(
        "{\n"
        f'  "half_life_bars": {hl_bars:.4f}, "half_life_minutes": {hl_min:.4f},\n'
        f'  "bar_minutes": {BAR_MINUTES}, "chosen_horizon": {chosen},\n'
        f'  "horizon_grid": [{", ".join(str(h) for h in HORIZON_GRID)}],\n'
        f'  "baseline_elevation": {baseline:.6f},\n'
        f'  "elevation_by_lag": [{", ".join(f"{v:.6f}" for v in elev[:13])}],\n'
        f'  "n_firings_fitted": {imp["n"]},\n'
        f'  "median_move_bps": {imp["median_move_bps"]:.4f},\n'
        f'  "median_expected_bps": {imp["median_expected_bps"]:.4f},\n'
        f'  "median_excess_bps": {imp["median_excess_bps"]:.4f},\n'
        f'  "q25_excess_bps": {imp["q25_excess_bps"]:.4f}, '
        f'"q75_excess_bps": {imp["q75_excess_bps"]:.4f}\n'
        "}\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
