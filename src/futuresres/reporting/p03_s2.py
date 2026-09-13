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

import json
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

#: THE DECLINED ALTERNATIVE, kept so it reads as superseded rather than forgotten. §54
#: predicted 1.0-4.0 bps from a mechanistic sketch (a 5m MNQ move has sd ~11 bps, a two-sigma
#: thin move ~20 bps, 5-20% excess reversal) whose direction was attributed to Campbell,
#: Grossman and Wang (1993). PROVENANCE: RECALLED FROM MEMORY, NEVER CHECKED against the paper,
#: and recorded as such in §54 at the time. It is superseded by the impact measured on this
#: series in `p03_mechanism.py`, which uses the same Amihud/Kyle mechanism and no recollection.
DECLINED_LITERATURE_LO: Final[float] = 1.0
DECLINED_LITERATURE_HI: Final[float] = 4.0

#: Measured design effects by family (§45/§54). The round-number family is the closest
#: analogue to a frequent intraday state; the upper figure is a deliberate pessimism, not a
#: measured value for P03 - P03's own DEFF depends on the outcome and measuring it here would
#: be looking at the answer.
DEFF_BEST: Final[float] = 2.19
DEFF_REALISTIC: Final[float] = 4.0


def bh_bar(effective_units: float, horizon: int = HORIZON_MINUTES,
           k: int = K_CELLS) -> float:
    """Smallest effect a BH rank-1 survivor must show, in bps.

    NO sqrt(2) PAIRING INFLATION IS APPLIED, and an earlier version of this file wrongly
    applied one. The anchor is not the SE of a single mean: L12 measured 1.016 bps as **its
    own bootstrap SE** on a real-minus-placebo table (`real | placebo | diff`), at 4,052
    pairs, and 64.7/sqrt(4052) = 1.016. **The anchor is already the SE of a
    difference-of-two-means**, so inflating it again double-counts the pairing. See §57.
    """
    z = float(norm.ppf(1 - (0.05 / k) / 2))
    se = SE_ANCHOR / np.sqrt(effective_units) * np.sqrt(horizon / HORIZON_MINUTES)
    return float(z * se)


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

    mech = json.loads((ROOT / "reports" / "p03_mechanism.json").read_text())
    horizon = int(mech["chosen_horizon"])
    ceiling = float(mech["median_excess_bps"])
    hl_min = float(mech["half_life_minutes"])

    print(f"\nHORIZON, from the state's own clock (p03_mechanism.py, no forward returns)")
    print(f"   half-life {hl_min:.1f} min -> nearest grid horizon H = {horizon}")
    print(f"   NOTE: the half-life is BELOW the 5-minute bar, so it is resolution-limited -")
    print(f"   any value under 5 min maps to the same grid point, the grid's smallest.")

    print(f"\nBH BAR at H = {horizon}, post-warm-up sample")
    print(f"{'DEFF':>6} {'eff units':>11} {'bar (bps)':>11}")
    rows = {}
    for label, deff in (("best", DEFF_BEST), ("realistic", DEFF_REALISTIC)):
        eff = n_pairs / deff
        bar = bh_bar(eff, horizon=horizon)
        rows[label] = (deff, eff, bar)
        print(f"{deff:>6.2f} {eff:>11,.0f} {bar:>11.3f}")
    lo_bar = min(r[2] for r in rows.values())
    hi_bar = max(r[2] for r in rows.values())

    print(f"\nMAGNITUDE, from measured impact rather than recalled literature")
    print(f"   median move at a firing      {mech['median_move_bps']:.2f} bps")
    print(f"   what its own volume buys     {mech['median_expected_bps']:.2f} bps")
    print(f"   measured excess (CEILING)    {ceiling:.2f} bps")
    print(f"   declined alternative         {DECLINED_LITERATURE_LO:.1f}-"
          f"{DECLINED_LITERATURE_HI:.1f} bps (§54, recalled and unchecked)")

    binding = max(hi_bar, COST_BPS)
    required = binding / ceiling
    print(f"\n   bar {lo_bar:.3f}-{hi_bar:.3f} bps   cost floor {COST_BPS:.2f} bps   "
          f"binding constraint {binding:.3f} bps")
    print(f"   REQUIRED REVERSION FRACTION: {required:.1%} of the measured excess")

    # NO INVENTED CUTOFF. An earlier draft of this file declared CLEARS when the required
    # fraction fell under a tenth - a constant chosen here, in this file, with nothing behind
    # it. That is the same error as the recalled literature this module exists to replace.
    # The measurement can rule the hypothesis OUT (a ceiling below the binding constraint);
    # it cannot rule it IN without a claim about the reversion fraction, which is precisely
    # what the test itself would measure. So the crossing point is reported and the judgement
    # is left where it belongs.
    if ceiling < binding:
        verdict = "BELOW"
        note = "even FULL reversion of the excess cannot reach the binding constraint"
    else:
        verdict = "NOT BELOW"
        note = (f"clears iff more than {required:.1%} of the excess reverts within "
                f"{horizon} min; this measurement cannot bound that fraction")
    print(f"\nvs cost floor : ceiling is {ceiling / COST_BPS:.1f}x the floor")
    print(f"vs BH bar     : {verdict} - {note}")

    OUT.write_text(
        "{\n"
        f'  "hypothesis": "P03", "series": "NQ",\n'
        f'  "lookback_sessions": {LOOKBACK_SESSIONS}, "threshold_pct": {THRESHOLD_PCT},\n'
        f'  "n_sessions_post_warmup": {n_sessions_total}, "n_firings": {n_pairs},\n'
        f'  "firings_per_session": {cl.firings_per_session:.4f},\n'
        f'  "firing_rate_spread": {spread:.4f},\n'
        f'  "deff_best": {DEFF_BEST}, "deff_realistic": {DEFF_REALISTIC},\n'
        f'  "bar_best": {rows["best"][2]:.4f}, '
        f'"bar_realistic": {rows["realistic"][2]:.4f},\n'
        f'  "horizon_minutes": {horizon}, "half_life_minutes": {hl_min:.4f},\n'
        f'  "ceiling_bps": {ceiling:.4f}, "binding_bps": {binding:.4f},\n'
        f'  "required_reversion_fraction": {required:.4f},\n'
        f'  "declined_literature_lo": {DECLINED_LITERATURE_LO}, '
        f'"declined_literature_hi": {DECLINED_LITERATURE_HI},\n'
        f'  "cost_bps": {COST_BPS}, "verdict": "{verdict}"\n'
        "}\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
