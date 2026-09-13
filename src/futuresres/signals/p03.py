"""P03 — thin-move reversion. S5 gate, matched control, S7. `decisions.md` §54-§57.

THE ORDER IS THE POINT AND IT IS ENFORCED BY CONTROL FLOW, NOT BY INTENTION. S5 is a
permanent gate (§46: L11's placebo was measured before anything verified its condition
discriminated, and the result had to be discarded). So this module runs, in order:

    1. S5   does the condition actually select events?      -> abort if it fails
    2. S6   is the matched control MATCHED?                  -> abort if it fails
    3. S7   the comparison, and only here is a trial spent
    4. S8   era split by default (§53), plus the economics against the cost floor

**A trial is spent only if 1 and 2 pass.** `stage1_run` is entered after both, so an aborted
run appends nothing and N is unchanged - which is the correct accounting, because a run that
never compared anything never had a chance to produce a false positive.

WHAT WAS PRE-REGISTERED, BEFORE THIS FILE EXISTED. P03 clears iff the real-minus-control mean
exceeds **+0.625 bps**, which is 6.8% of the 9.18 bps excess displacement measured in
`p03_mechanism.py`. The 9.18 is a CEILING - part of it is permanent information rather than
transitory impact - so the honest prior on the reversion fraction is UNKNOWN, not high. A null
is informative here because the threshold is low, not because the effect was expected.

THE BINDING CONSTRAINT IS ECONOMICS, NOT SIGNIFICANCE, and that was recorded before the run.
Cost floor 0.48 bps against a BH bar of 0.463-0.625. Every earlier P-series entry was
significance-dominated - P01 needed 4.2-5.4 bps, P09 needed 72-102 - so a null at P03 says the
effect is small in bps, not that the test could not see it.

DIRECTION IS A PROPERTY OF THE EVENT, SO THE CONTROL TAKES ITS OWN. `sweep_stage1` records the
distinction: L07's placebo inherited the real zone's direction because direction was a property
of the GAP, while L02/L03/L04's takes its own because direction is a property of the EVENT.
Here direction is -sign(the firing bar's return), computed at the bar, so the control computes
its own by the same rule. Forcing the real bar's sign onto the control would compare the rule
against a counterfactual that never happened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

from futuresres.reporting.state_control_feasibility import (
    LOOKBACK_SESSIONS,
    THRESHOLD_PCT,
    build_state,
    load_bars,
)
from futuresres.signals.logged_run import stage1_run
from futuresres.signals.state_control import (
    UNMATCHED,
    make_matched_control,
    paired_state_stats,
    session_clustering,
    verify_control,
)

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
OUT: Final[Path] = ROOT / "reports" / "p03_stage1.json"

HORIZON_MINUTES: Final[int] = 15
BAR_MINUTES: Final[int] = 5
HOLD_BARS: Final[int] = HORIZON_MINUTES // BAR_MINUTES

#: reports/calibration.md, MNQ round trip.
COST_BPS: Final[float] = 0.48

#: PRE-REGISTERED 2026-09-13, before this file existed. 6.8% of the measured 9.18 bps excess.
REFUTATION_THRESHOLD_BPS: Final[float] = 0.625

#: S5 part 2 compares the registered threshold against its neighbours. These are NOT extra
#: cells and spend no trials - they exist only to show the parameter changes WHICH events
#: fire rather than merely when.
S5_NEIGHBOUR_PCTS: Final[tuple[float, ...]] = (85.0, 95.0)


@dataclass(frozen=True, slots=True)
class Cell:
    product: str
    horizon: int
    lookback: int
    threshold_pct: float
    events: int
    real_bps: float
    control_bps: float
    mean_bps: float
    ci_low: float
    ci_high: float
    p_value: float
    separated: bool
    clears_preregistered: bool
    sharpe: float | None


def outcomes(w: dict[str, np.ndarray], idx: np.ndarray) -> np.ndarray:
    """Faded forward return over H, in bps. NaN where the hold runs past the session close.

    Direction is -sign(the bar's own return): the state says the move was made on thin volume,
    the claim is that it gives part of itself back, so the trade is to fade it.
    """
    close, sid, ret = w["close"], w["session"], w["ret_bps"]
    out = np.full(idx.size, np.nan)
    nxt = idx + HOLD_BARS
    ok = (nxt < close.size) & (idx >= 0)
    ok[ok] &= sid[nxt[ok]] == sid[idx[ok]]
    ok &= np.isfinite(ret[idx]) & (ret[idx] != 0)
    i, j = idx[ok], nxt[ok]
    # `ret_bps` carries the ABSOLUTE move, so the sign is recovered from consecutive closes.
    # Bars with no defined prior bar are already excluded above, so i-1 is same-session.
    signed = np.log(close[i] / close[i - 1]) * 1e4
    direction = -np.sign(signed)
    fwd = np.log(close[j] / close[i]) * 1e4
    out[ok] = direction * fwd
    return out


def s5_gate(w: dict[str, np.ndarray]) -> dict[str, object]:
    """Condition validity. STAGES.md S5: a permanent gate, three parts.

    Part 3 (directional collapse) is N/A by construction and says so rather than being
    silently skipped: P03 has no level set carrying a high and a low. A bar has one return
    with one sign, so the two directions cannot fire at the same (session, minute).
    """
    state, tod = w["state"] & (w["vol_q"] >= 0), w["tod"]
    slot = w["slot"]
    minutes = slot[state] * BAR_MINUTES
    sd = float(np.std(minutes))
    spread = int(minutes.max() - minutes.min()) if minutes.size else 0

    # Part 2: do neighbouring thresholds change WHICH bars fire, or only how many?
    lam = w["illiq"] / w["thresh"]
    overlaps = {}
    base = set(np.flatnonzero(state).tolist())
    for pct in S5_NEIGHBOUR_PCTS:
        # the threshold is a quantile of the same trailing pool, so a neighbouring pct
        # rescales it by the ratio of those quantiles; approximate with the pooled ratio
        scale = float(np.nanpercentile(lam[np.isfinite(lam)], pct)
                      / np.nanpercentile(lam[np.isfinite(lam)], THRESHOLD_PCT))
        alt = set(np.flatnonzero((lam > scale) & (w["vol_q"] >= 0)).tolist())
        shared = len(base & alt) / max(len(base | alt), 1)
        overlaps[pct] = {"events": len(alt), "jaccard_with_registered": round(shared, 4)}

    fires_at_fixed_minute = sd < 1.0
    parameter_is_an_offset = all(v["jaccard_with_registered"] > 0.99 for v in overlaps.values())
    passed = not fires_at_fixed_minute and not parameter_is_an_offset
    return {
        "passed": passed,
        "entry_minute_sd": round(sd, 1),
        "entry_minute_spread": spread,
        "neighbour_thresholds": overlaps,
        "directional_collapse": "N/A - no level set; a bar carries one signed return",
        "reason": "" if passed else (
            "fires at a fixed minute" if fires_at_fixed_minute
            else "neighbouring thresholds select the same events"),
    }


def era_split(real: np.ndarray, ctrl: np.ndarray, sess: np.ndarray,
              rng: np.random.Generator) -> list[dict[str, float]]:
    """§53: the era split runs by DEFAULT, not when decay is suspected."""
    cut = int(np.median(sess))
    out = []
    for name, m in (("early", sess <= cut), ("late", sess > cut)):
        r, c, d, lo, hi, n, p = paired_state_stats(real[m], ctrl[m], sess[m], rng)
        out.append({"era": name, "n": n, "real_bps": r, "control_bps": c,
                    "diff_bps": d, "ci_low": lo, "ci_high": hi, "p_value": p})
    return out


def main() -> int:
    rng = np.random.default_rng(20260913)
    df = load_bars()
    w = build_state(df)
    w["close"] = df["close"].to_numpy()
    w["slot"] = df["slot"].to_numpy().astype(int)

    print("=" * 78)
    print("P03 — thin-move reversion, NQ state / MNQ economics, H = 15")
    print("=" * 78)

    gate = s5_gate(w)
    print(f"\nS5 GATE: {'PASS' if gate['passed'] else 'FAIL'}")
    print(f"  entry-minute sd {gate['entry_minute_sd']} over a spread of "
          f"{gate['entry_minute_spread']} minutes")
    for pct, v in gate["neighbour_thresholds"].items():
        print(f"  Q{pct:g}: {v['events']:,} events, Jaccard vs registered "
              f"{v['jaccard_with_registered']}")
    print(f"  directional collapse: {gate['directional_collapse']}")
    if not gate["passed"]:
        print(f"\nABORTED at S5 ({gate['reason']}). No trial spent.")
        return 1

    state = w["state"] & (w["vol_q"] >= 0)
    sid = w["session"]
    real_idx = np.flatnonzero(state)
    cl = session_clustering(state, sid)
    draw = make_matched_control(state, sid, w["tod"], w["vol_q"],
                                condition_name="P03", year=w["year"],
                                session_exclusion="bar")
    rep = verify_control("P03", "NQ", real_idx, draw, w["tod"], w["vol_q"], w["year"],
                         strict=False)
    print(f"\nS6 CONTROL ({'bar'} mode): {rep.verdict}")
    print(f"  matched {rep.n_matched:,}/{rep.n_real:,}, distinct control bars "
          f"{rep.n_control_bars:,}, reuse {rep.reuse_rate:.1%}")
    print(f"  ToD dev {rep.tod_max_ratio_dev:.3f}, vol dev {rep.vol_max_ratio_dev:.3f}, "
          f"year dev {rep.year_max_ratio_dev:.3f}, era fallback {rep.fallback_rate:.1%}")
    for f in rep.failures:
        print(f"  - {f}")
    if not rep.ok:
        print("\nABORTED at S6: the control is not matched, so no comparison is valid. "
              "No trial spent.")
        return 1

    paired = draw.index != UNMATCHED
    r_idx, c_idx = real_idx[paired], draw.index[paired]
    real_out, ctrl_out = outcomes(w, r_idx), outcomes(w, c_idx)
    both = np.isfinite(real_out) & np.isfinite(ctrl_out)
    real_out, ctrl_out, sess = real_out[both], ctrl_out[both], sid[r_idx][both]
    print(f"\npairs with a full {HORIZON_MINUTES}-minute hold on both sides: "
          f"{both.sum():,} of {paired.sum():,}")

    r, c, diff, lo, hi, n, p = paired_state_stats(real_out, ctrl_out, sess, rng)
    sharpe = float(np.mean(real_out) / np.std(real_out)) if real_out.size else None
    separated = bool((lo > 0 or hi < 0) and p < 0.05)
    clears = bool(diff > REFUTATION_THRESHOLD_BPS)

    cell = Cell("MNQ", HORIZON_MINUTES, LOOKBACK_SESSIONS, THRESHOLD_PCT, n,
                r, c, diff, lo, hi, p, separated, clears, sharpe)

    with stage1_run("P03", provenance="native",
                    date_range=("2010-06-07", "2026-08-27"),
                    note="thin-move reversion vs matched state control, bar mode, H=15") as log:
        log.record([cell])
    print(f"\ntrial logged ({log.written} cell)")

    print("\nECONOMICS FIRST (cost floor {:.2f} bps round trip)".format(COST_BPS))
    print(f"  real leg gross            {r:+.4f} bps")
    print(f"  real leg net of cost      {r - COST_BPS:+.4f} bps")
    print(f"  control leg gross         {c:+.4f} bps")
    print(f"  REAL - CONTROL            {diff:+.4f} bps")
    print(f"  pre-registered threshold  {REFUTATION_THRESHOLD_BPS:+.4f} bps "
          f"-> {'CLEARS' if clears else 'DOES NOT CLEAR'}")
    print(f"  per-trade Sharpe (real)   {sharpe:.4f}")

    print("\nSEPARATION SECOND")
    print(f"  CI [{lo:+.4f}, {hi:+.4f}]   p = {p:.4f}   separated: {separated}")

    print("\nERA SPLIT (§53, by default)")
    eras = era_split(real_out, ctrl_out, sess, rng)
    for e in eras:
        print(f"  {e['era']:>5}: n {e['n']:,}  real {e['real_bps']:+.4f}  "
              f"control {e['control_bps']:+.4f}  diff {e['diff_bps']:+.4f}  "
              f"CI [{e['ci_low']:+.4f}, {e['ci_high']:+.4f}]  p {e['p_value']:.4f}")

    OUT.write_text(json.dumps({
        "hypothesis": "P03", "horizon_minutes": HORIZON_MINUTES,
        "lookback_sessions": LOOKBACK_SESSIONS, "threshold_pct": THRESHOLD_PCT,
        "s5": gate,
        "control": {"mode": "bar", "verdict": rep.verdict, "n_real": rep.n_real,
                    "n_matched": rep.n_matched, "control_bars": rep.n_control_bars,
                    "reuse_rate": rep.reuse_rate, "fallback_rate": rep.fallback_rate,
                    "tod_dev": rep.tod_max_ratio_dev, "vol_dev": rep.vol_max_ratio_dev,
                    "year_dev": rep.year_max_ratio_dev,
                    "firings_per_session": cl.firings_per_session,
                    "sessions_touched_share": cl.sessions_touched_share},
        "result": {"n": n, "real_bps": r, "control_bps": c, "diff_bps": diff,
                   "ci_low": lo, "ci_high": hi, "p_value": p, "separated": separated,
                   "sharpe": sharpe, "cost_bps": COST_BPS,
                   "real_net_of_cost_bps": r - COST_BPS,
                   "preregistered_threshold_bps": REFUTATION_THRESHOLD_BPS,
                   "clears_preregistered": clears},
        "era_split": eras,
    }, indent=1) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
