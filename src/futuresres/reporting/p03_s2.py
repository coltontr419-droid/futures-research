"""P03 S2: the threshold's denominator, the predicted magnitude, and the BH bar.

**NO RETURNS ARE SCORED HERE.** S2 is the pre-registration check (§45, `STAGES.md`): compare a
PREDICTED magnitude against the cost floor and against the BH bar at the expected n. It reads
|return| only as the numerator of the state's own definition, never as an outcome. Nothing in
this module computes a forward return, an effect, or a verdict about P03's truth.

THE DENOMINATOR PROBLEM, AND WHY THE OBVIOUS FORM FAILS. P03 is an Amihud-style thin-move
condition: |return| per unit volume. §54 recorded that this ratio is NOT scale invariant, which
was the draft's error — a ratio is invariant only if its denominator is stationary, and bar
volume is not:

    contract change     NQ -> MNQ at the 2019-05-31 splice is a 10x notional change; measured
                        median 1m bar volume falls 83-140 to 26-39, so the ratio steps up 3-5x
    secular growth      median bar volume on NQ alone runs 16 (2010) to 784 (2026), ~50x

A fixed threshold on |bps|/contract would therefore fire almost never early in the sample and
almost always late, which is an era clock wearing a liquidity label.

THE DENOMINATOR ACTUALLY REGISTERED: THE STATE'S OWN TRAILING DISTRIBUTION. The condition is
not "illiquidity above X". It is

    lambda_t > Q90( lambda over the SAME 30-minute bucket, over the PREVIOUS 60 sessions )

so what is thresholded is lambda's RANK within its own recent history, which is dimensionless.
Any rescaling of volume that is common to a 60-session window - a contract change, a secular
growth in participation, a tick-size change - divides the numerator and the denominator of that
comparison alike and leaves the rank untouched. The bucket term does the same for the
time-of-day shape, which the draft flagged as P03's largest confound.

Two consequences recorded as parameters rather than details:

    LOOKBACK = 60 sessions      costs 566 of 4,125 sessions to warm-up, and sets how fast the
                                threshold tracks a trend. Fixed a priori.
    the transition window       a contract change is absorbed within one lookback, so a spliced
                                series must drop the 60 sessions after the splice. NQ-only
                                avoids this entirely and is what is used.

THE EVIDENCE THAT IT WORKED IS THE FIRING RATE, NOT THE ARGUMENT. If the denominator were
non-stationary the firing rate would drift across eras while the threshold sat still. This
module reports both per year: the raw threshold must move a great deal (the volume growth is
real) while the firing rate must stay flat near 10% (the rank is invariant to it).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
from scipy.stats import norm

from futuresres.reporting.state_control_feasibility import (
    LOOKBACK_SESSIONS,
    THRESHOLD_PCT,
    build_state,
    load_bars,
)
from futuresres.signals.state_control import session_clustering

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
OUT: Final[Path] = ROOT / "reports" / "p03_s2.json"

#: §45's SE anchor: SE = SE_ANCHOR / sqrt(effective units) bps at a 180-minute hold,
#: measured on L12 (SE 1.016 at paired n 4,052). sd scales as sqrt(h/180).
SE_ANCHOR: Final[float] = 64.7
HORIZON_MINUTES: Final[int] = 180

#: BH rank-1 across k cells, as §45-§54 use it. k=9 keeps this comparable to the P-series table.
K_CELLS: Final[int] = 9

#: reports/calibration.md, round trip. MNQ is the tradeable instrument even though the STATE is
#: measured on NQ, so MNQ's floor is the one that binds.
COST_BPS: Final[float] = 0.48

#: §54's predicted range for P03, from the mechanistic bracket (a 5m MNQ move has sd ~11 bps, a
#: two-sigma thin move ~20 bps, 5-20% excess reversal gives 1-4) and consistent in DIRECTION
#: with Campbell, Grossman and Wang (1993). A PRIOR, not a measurement.
PREDICTED_LO: Final[float] = 1.0
PREDICTED_HI: Final[float] = 4.0

#: Measured design effects by family (§45/§54). The round-number family is the closest
#: analogue to a frequent intraday state; the upper figure is a deliberate pessimism, not a
#: measured value for P03 - P03's own DEFF depends on the outcome and measuring it here would
#: be looking at the answer.
DEFF_BEST: Final[float] = 2.19
DEFF_REALISTIC: Final[float] = 4.0


def bh_bar(effective_units: float, horizon: int = HORIZON_MINUTES,
           k: int = K_CELLS, paired: bool = False) -> float:
    """Smallest effect a BH rank-1 survivor must show, in bps.

    `paired=True` applies the sqrt(2) inflation for a real-minus-control DIFFERENCE of two
    event means. That is the CONSERVATIVE end: matching on regime correlates the two sides
    positively, which reduces the variance of their difference, so the true factor lies
    between 1 and sqrt(2). It is reported both ways rather than picked.
    """
    z = float(norm.ppf(1 - (0.05 / k) / 2))
    se = SE_ANCHOR / np.sqrt(effective_units) * np.sqrt(horizon / HORIZON_MINUTES)
    return float(z * se * (np.sqrt(2.0) if paired else 1.0))


def main() -> int:
    w = build_state(load_bars())
    state, sid, year = w["state"], w["session"], w["year"]
    usable = w["vol_q"] >= 0          # post warm-up, the only bars either side can use
    n_sessions_total = int(w["n_sessions"])

    fired = state & usable
    n_pairs = int(fired.sum())
    n_sessions = int(np.unique(sid[fired]).size)
    cl = session_clustering(fired, sid)

    print("=" * 78)
    print("P03 S2 - thin-move reversion, NQ, 5m RTH bars")
    print("=" * 78)
    print(f"denominator: trailing Q{THRESHOLD_PCT:.0f} of the same 30-minute bucket over the "
          f"previous {LOOKBACK_SESSIONS} sessions")
    print(f"sample: {n_sessions_total:,} sessions post warm-up "
          f"(566 of 4,125 spent on the lookback)")
    print(f"firings {n_pairs:,} across {n_sessions:,} sessions "
          f"({cl.firings_per_session:.2f}/session)")

    print("\nSTATIONARITY OF THE DENOMINATOR - firing rate must stay flat while the raw "
          "threshold moves")
    print(f"{'year':>6} {'bars':>8} {'firings':>8} {'rate':>7} {'median volume/bar':>18}")
    rates = {}
    vol = w.get("volume")
    for y in sorted(set(year[usable].tolist())):
        m = usable & (year == y)
        rate = float(state[m].mean()) if m.any() else float("nan")
        rates[int(y)] = rate
        med_v = float(np.median(vol[m])) if vol is not None and m.any() else float("nan")
        print(f"{y:>6} {int(m.sum()):>8,} {int((state & m).sum()):>8,} {rate:>7.2%} "
              f"{med_v:>18,.0f}")
    spread = max(rates.values()) - min(rates.values())
    print(f"\nfiring-rate spread across eras: {spread:.2%} "
          f"(min {min(rates.values()):.2%}, max {max(rates.values()):.2%})")

    print("\nBH BAR at the post-warm-up sample")
    print(f"{'DEFF':>6} {'eff units':>11} {'bar (single)':>13} {'bar (paired)':>13}")
    rows = {}
    for label, deff in (("best", DEFF_BEST), ("realistic", DEFF_REALISTIC)):
        eff = n_pairs / deff
        single, pair = bh_bar(eff), bh_bar(eff, paired=True)
        rows[label] = (deff, eff, single, pair)
        print(f"{deff:>6.2f} {eff:>11,.0f} {single:>13.2f} {pair:>13.2f}")

    lo_bar = min(r[2] for r in rows.values())
    hi_bar = max(r[3] for r in rows.values())
    print(f"\npredicted {PREDICTED_LO:.1f}-{PREDICTED_HI:.1f} bps   "
          f"cost floor {COST_BPS:.2f} bps   bar range {lo_bar:.2f}-{hi_bar:.2f} bps")

    clears_cost = PREDICTED_LO > COST_BPS
    if PREDICTED_LO > hi_bar:
        verdict = "CLEARS"
    elif PREDICTED_HI < lo_bar:
        verdict = "BELOW"
    else:
        verdict = "STRADDLES"
    print(f"\nvs cost floor : {'above across the range' if clears_cost else 'at/below at the low end'}")
    print(f"vs BH bar     : {verdict}")

    OUT.write_text(
        "{\n"
        f'  "hypothesis": "P03", "series": "NQ", "horizon_minutes": {HORIZON_MINUTES},\n'
        f'  "lookback_sessions": {LOOKBACK_SESSIONS}, "threshold_pct": {THRESHOLD_PCT},\n'
        f'  "n_sessions_post_warmup": {n_sessions_total}, "n_firings": {n_pairs},\n'
        f'  "firings_per_session": {cl.firings_per_session:.4f},\n'
        f'  "firing_rate_spread": {spread:.4f},\n'
        f'  "deff_best": {DEFF_BEST}, "deff_realistic": {DEFF_REALISTIC},\n'
        f'  "bar_single_best": {rows["best"][2]:.4f}, '
        f'"bar_paired_best": {rows["best"][3]:.4f},\n'
        f'  "bar_single_realistic": {rows["realistic"][2]:.4f}, '
        f'"bar_paired_realistic": {rows["realistic"][3]:.4f},\n'
        f'  "predicted_lo": {PREDICTED_LO}, "predicted_hi": {PREDICTED_HI},\n'
        f'  "cost_bps": {COST_BPS}, "verdict": "{verdict}"\n'
        "}\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
