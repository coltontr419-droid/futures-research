"""S-series S2 arithmetic: BH bars, cost comparison and cumulative SR*.

NOTHING IS REGISTERED BY THIS MODULE AND NO TRIAL IS SPENT. It reads the trial log to
reproduce SR* and projects it forward; everything else is arithmetic on firing counts that
are either MEASURED in an existing report (provenance recorded per row) or EXTRAPOLATED from
one by a stated rule.

Method, inherited unchanged from decisions.md §54 (P-series) and §59 (Q-series) so the
S-series filter is comparable to theirs:

    bar = z(1 - 0.05/(2k)) * anchor(H) / sqrt(units)
    anchor(H) = 64.7 * sqrt(H / 180)      bps per event, L12's measured paired bootstrap
    units     = raw_firings / DEFF
    k         = cells in the entry's own grid (BH rank-1, within-entry)

Post-2021 decides (STAGES.md, S8), so every bar is reported post-2021 as well as full sample.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict, field
from pathlib import Path

import numpy as np
from scipy.stats import norm

REPO = Path(__file__).resolve().parents[3]
TRIALS = REPO / "trials.jsonl"
OUT = REPO / "reports" / "s_series_s2.json"

ANCHOR_180 = 64.7          # bps per event at H=180m; L12's paired bootstrap (§57)
EULER = 0.5772156649015329
COST = {"MNQ": 0.48, "MGC": 0.65}

# Sessions, from reports/level_rates.md ("Data" table) and §59's post-2021 counts.
SESSIONS = {"MNQ": 4124, "MGC": 4005}
POST_2021 = 1390           # programme_conclusion.md §4: "about 1,390-1,440 sessions"


def anchor(h_minutes: float) -> float:
    return ANCHOR_180 * math.sqrt(h_minutes / 180.0)


def bh_rank1_z(k: int) -> float:
    """Two-sided z for the rank-1 Benjamini-Hochberg threshold at FDR 0.05 over k cells."""
    return float(norm.ppf(1.0 - (0.05 / k) / 2.0))


def bar_bps(units: float, k: int, h_minutes: float) -> float:
    return bh_rank1_z(k) * anchor(h_minutes) / math.sqrt(units)


def expected_max_sharpe(n_trials: int, variance: float) -> float:
    """Verbatim from stats/dsr.py, duplicated here only so this module reads standalone."""
    if n_trials <= 1 or variance == 0:
        return 0.0
    n = float(n_trials)
    return float(
        math.sqrt(variance)
        * ((1.0 - EULER) * norm.ppf(1.0 - 1.0 / n) + EULER * norm.ppf(1.0 - 1.0 / (n * math.e)))
    )


def trial_state() -> tuple[int, float]:
    n, sharpes = 0, []
    for line in TRIALS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        n += 1
        rec = json.loads(line)
        if rec.get("sharpe") is not None:
            sharpes.append(rec["sharpe"])
    return n, float(np.var(sharpes, ddof=1))


# --------------------------------------------------------------------------- entries
@dataclass
class Cell:
    tf: str
    n_raw: int                 # raw firings, MNQ, full sample
    deff: float
    provenance: str


@dataclass
class Entry:
    sid: str
    label: str
    overlap: str               # new | timeframe extension | repeat
    prior: str
    kind: str                  # state | level
    k: int                     # cells in its own grid
    horizon: float             # minutes
    predicted_lo: float
    predicted_hi: float
    predicted_basis: str
    threshold_units: str
    cells: list[Cell] = field(default_factory=list)


# DEFF provenance:
#   5.79-12.72  MEASURED for FVG at 15m/30m, reports/peak_bps_l07.json
#   2.19        MEASURED for a once-per-session level family (§45)
#   1.14        MEASURED for sparse events (§45)
# A frequent intrabar indicator is given the FVG-measured bracket's low end, 5.8, because
# that is the only measurement of this quantity the programme has on an intrabar object.
D_STATE, D_LEVEL = 5.8, 2.19

ENTRIES = [
    Entry(
        "S01", "Fair value gaps", "repeat", "L07 - ran, 108 trials, retired at S8",
        "state", 30, 180.0, 1.18, 5.79,
        "MEASURED, not a prior: L07's own real-minus-placebo difference, -1.176 to -5.008 bps "
        "(tick widths, §38) and -5.79 bps at tf=15m w=1.6bps (peak_bps_l07.json). NEGATIVE.",
        "gap width in bps (1.6 / 4.8 / 12.8), already re-specified in bps by §53",
        [
            Cell("5m",  56310, D_STATE, "EXTRAPOLATED x3 from the 15m bps measurement"),
            Cell("15m", 18770, 5.79,   "MEASURED peak_bps_l07.json w=1.6bps"),
            Cell("30m",  6601, 6.86,   "MEASURED peak_bps_l07.json w=1.6bps"),
            Cell("1h",   3301, D_STATE, "EXTRAPOLATED /2 from the 30m measurement"),
            Cell("4h",    825, D_STATE, "EXTRAPOLATED /8 from the 30m measurement"),
        ],
    ),
    Entry(
        "S02", "RSI(14) threshold crossings", "timeframe extension",
        "F10 - registered, firing rate measured, retired unpowered",
        "state", 30, 180.0, 0.0, 2.0,
        "PRIOR. No literature bps figure for intraday futures RSI; bracketed by the "
        "programme's own observed range (typical 0.3-3.5 bps) with zero included because "
        "decay since publication is the stated prior (§59).",
        "RSI is already unit-free; thresholds 30/70, 20/80, 25/75 are scale-invariant",
        [
            Cell("5m",  33564, D_STATE, "EXTRAPOLATED 1/tf from the 30m measurement"),
            Cell("15m", 10550, D_STATE, "EXTRAPOLATED 1/tf from the 30m measurement"),
            Cell("30m",  5594, D_STATE, "MEASURED firing_rates.md F10 MNQ 30m"),
            Cell("1h",   2966, D_STATE, "MEASURED firing_rates.md F10 MNQ 60m"),
            Cell("4h",    793, D_STATE, "EXTRAPOLATED /2 from the MEASURED 120m count 1,585"),
        ],
    ),
    Entry(
        "S03", "VWAP touch after separation", "repeat",
        "L01 - registered, firing rate measured, blocked at S4",
        "level", 30, 180.0, 0.0, 1.5,
        "PRIOR. L01 never ran. The nearest measured level-reaction magnitudes are L03's null, "
        "L04's +3.54 bps (did not replicate) and L12's +0.306 bps out of sample.",
        "d in ATR multiples - scale-invariant, but WHICH ATR is the open specification "
        "(CHECKPOINT: the d-ATR reference period, deliberately frozen)",
        [
            Cell("5m",  237, D_LEVEL, "MEASURED level_rates.md L01 MNQ best cell (anchor=CME d=0.5)"),
            Cell("15m", 237, D_LEVEL, "MEASURED - the level set is identical; tf is detection granularity only"),
            Cell("30m", 237, D_LEVEL, "MEASURED - as above"),
            Cell("1h",  237, D_LEVEL, "MEASURED - as above"),
            Cell("4h",  237, D_LEVEL, "MEASURED - as above"),
        ],
    ),
    Entry(
        "S04", "EMA(20/50/200) touch after separation", "timeframe extension",
        "L08 - registered, firing rate measured at 5m and 15m, blocked at S4; "
        "F11 ma_crossover retired on premise",
        "level", 30, 180.0, 0.0, 1.5,
        "PRIOR. Same basis as S03. L08's own registry entry grades the mechanism weak: "
        "'no institution executes against a 50 EMA'.",
        "d in ATR multiples; same open ATR-period specification as S03",
        [
            Cell("5m",  659, D_LEVEL, "MEASURED level_rates.md L08 MNQ ema200 5m d=0.5"),
            Cell("15m", 705, D_LEVEL, "MEASURED level_rates.md L08 MNQ ema200 15m d=0.5"),
            Cell("30m", 850, D_LEVEL, "EXTRAPOLATED - rises with tf as the EMA lags further"),
            Cell("1h",  950, D_LEVEL, "EXTRAPOLATED - as above"),
            Cell("4h",  600, D_LEVEL, "EXTRAPOLATED - falls again; ~5.75 4h bars/session caps it"),
        ],
    ),
    Entry(
        "S05", "Volume profile POC / VAH / VAL", "new", "none - absent from all six series",
        "level", 30, 180.0, 0.0, 1.5,
        "PRIOR. Same basis as S03. No published bps figure; the mechanism is the same "
        "self-fulfilling story L08 carries.",
        "value area at 70% of volume and bin width in bps, not ticks",
        [
            Cell("5m",  5643, D_LEVEL, "EXTRAPOLATED x1.5 from L03's MEASURED 3,762 (3 levels/session vs 2)"),
            Cell("15m", 5643, D_LEVEL, "EXTRAPOLATED - level set identical across tf"),
            Cell("30m", 5643, D_LEVEL, "EXTRAPOLATED - as above"),
            Cell("1h",  5643, D_LEVEL, "EXTRAPOLATED - as above"),
            Cell("4h",  5643, D_LEVEL, "EXTRAPOLATED - as above"),
        ],
    ),
    Entry(
        "S06", "Bollinger band breakout", "repeat",
        "L11 - registered then WITHDRAWN at S5; never actually tested (confirmed_break defect)",
        "state", 30, 180.0, 0.0, 2.0,
        "PRIOR. L11's only numbers are recorded under `degenerate_measurements` and are "
        "explicitly not evidence.",
        "k in standard deviations - scale-invariant by construction",
        [
            Cell("5m",  56800, D_STATE, "EXTRAPOLATED ~5% of bars, from bars/session x sessions"),
            Cell("15m", 18950, D_STATE, "EXTRAPOLATED - as above"),
            Cell("30m",  9475, D_STATE, "EXTRAPOLATED - as above"),
            Cell("1h",   4740, D_STATE, "EXTRAPOLATED - as above"),
            Cell("4h",   1185, D_STATE, "EXTRAPOLATED - as above"),
        ],
    ),
    Entry(
        "S07", "MACD(12,26,9) signal cross", "repeat",
        "F11 ma_crossover_control - RETIRED ON PREMISE, never run",
        "state", 30, 180.0, 0.0, 2.0,
        "PRIOR. F11's retirement is on premise, not power, so no magnitude was ever stated.",
        "MACD is a price difference; its threshold is a sign change, which is unit-free",
        [
            Cell("5m",  60000, D_STATE, "EXTRAPOLATED from F11's MEASURED 164,775 in-state 30m bars"),
            Cell("15m", 20000, D_STATE, "EXTRAPOLATED - as above"),
            Cell("30m", 10000, D_STATE, "EXTRAPOLATED - as above"),
            Cell("1h",   5000, D_STATE, "EXTRAPOLATED - as above"),
            Cell("4h",   1250, D_STATE, "EXTRAPOLATED - as above"),
        ],
    ),
    Entry(
        "S08", "Stochastic %K/%D threshold crossings", "new",
        "none directly; same family as F10 (RSI)",
        "state", 30, 180.0, 0.0, 2.0,
        "PRIOR. Same basis as S02, to which it is expected to be near-collinear.",
        "%K is bounded 0-100; thresholds are scale-invariant",
        [
            Cell("5m",  83910, D_STATE, "EXTRAPOLATED 2.5x F10's MEASURED counts (looser bounds fire more)"),
            Cell("15m", 26375, D_STATE, "EXTRAPOLATED - as above"),
            Cell("30m", 13985, D_STATE, "EXTRAPOLATED - as above"),
            Cell("1h",   7415, D_STATE, "EXTRAPOLATED - as above"),
            Cell("4h",   1983, D_STATE, "EXTRAPOLATED - as above"),
        ],
    ),
    Entry(
        "S09", "Classic floor pivots (PP, R1/S1, R2/S2)", "new",
        "none as specified; a deterministic function of L03's prior-day H/L/C",
        "level", 30, 180.0, 0.0, 1.5,
        "PRIOR. Same basis as S03; L03 tested the inputs and returned 0 of 18.",
        "pivot distances are price levels by construction - the registration must state "
        "the price range and pre-register the era split (S2 scale rule, escape hatch)",
        [
            Cell("5m",  5000, D_LEVEL, "EXTRAPOLATED from L03's MEASURED 3,762 prior-day touches"),
            Cell("15m", 5000, D_LEVEL, "EXTRAPOLATED - level set identical across tf"),
            Cell("30m", 5000, D_LEVEL, "EXTRAPOLATED - as above"),
            Cell("1h",  5000, D_LEVEL, "EXTRAPOLATED - as above"),
            Cell("4h",  5000, D_LEVEL, "EXTRAPOLATED - as above"),
        ],
    ),
]


# Horizons reported. 180m is the P-series filter's horizon, so the bars are comparable to
# §54's. 30m is the FAVOURABLE case: the bar falls as sqrt(H) while the cost floor does not,
# and several of these indicators are short-horizon objects. Both are reported because
# picking the horizon that closes the series would be choosing a parameter to get a result
# (§53), and so would picking the one that opens it.
HORIZONS = (180.0, 30.0)

# The programme's three measured effects with a known S7 outcome, used to check that this
# arithmetic recovers verdicts already on file before it is used to predict new ones (§60:
# a pipeline must be shown to recover what it seeks).
VALIDATION = [
    ("L07 @ tf=15m, w=1.6bps", 5.79, 22.8, 0.1357, "separated in 108/108 cells"),
    ("L04 best cell", 3.543, 64.7, 0.1367, "nominal separation, 0 BH survivors"),
    ("L12", 0.306, 64.7, 0.1367, "0 of 9 cells separated"),
]


def sr_star_in_bps(sr_star: float, h_minutes: float) -> float:
    """The per-event effect whose per-observation Sharpe equals SR*.

    SR* is a Sharpe, the entry bars are in bps, and they are not comparable until one is
    converted. A per-event effect of `e` bps against per-event noise `anchor(H)` has
    per-observation Sharpe e/anchor(H), so the effect that merely REACHES SR* is
    SR* * anchor(H). Below it, a cell's Sharpe is inside what the best of N worthless
    strategies reaches by chance, whatever its own BH bar says.
    """
    return sr_star * anchor(h_minutes)


def main() -> dict:
    n0, variance = trial_state()
    sr0 = expected_max_sharpe(n0, variance)
    post_share = POST_2021 / SESSIONS["MNQ"]

    out: dict = {
        "note": "NOTHING REGISTERED, NO TRIAL SPENT. Bars are S2 arithmetic only.",
        "method": {
            "bar": "z(1-0.05/(2k)) * 64.7*sqrt(H/180) / sqrt(units)",
            "units": "raw firings / DEFF",
            "anchor_bps_at_180m": ANCHOR_180,
            "deff_provenance": {
                "5.79-12.72": "MEASURED, FVG at 15m/30m, reports/peak_bps_l07.json",
                "2.19": "MEASURED, once-per-session level family, §45",
                "5.8": "the FVG bracket's low end, applied to other intrabar states",
            },
            "post_2021_share_of_sessions": round(post_share, 4),
            "cost_floor_bps": COST,
            "sr_star_projection_holds_trial_variance_fixed": variance,
        },
        "at_pickup": {"N": n0, "SR_star": round(sr0, 4), "trial_sharpe_variance": variance},
        "sr_star_as_an_effect_bps": {
            f"H={int(h)}m": round(sr_star_in_bps(sr0, h), 3) for h in HORIZONS
        },
        "validation": [
            {
                "case": name, "effect_bps": eff, "per_event_sd_bps": sd,
                "sharpe": round(eff / sd, 4), "SR_star_then": srs,
                "clears_SR_star": (eff / sd) > srs, "recorded_outcome": outcome,
            }
            for name, eff, sd, srs, outcome in VALIDATION
        ],
        "entries": [],
    }

    n_running = n0
    for e in ENTRIES:
        cells = []
        for c in e.cells:
            units_full = c.n_raw / c.deff
            units_post = units_full * post_share
            cells.append({
                "tf": c.tf, "n_raw": c.n_raw, "deff": c.deff,
                "units_full": round(units_full, 1), "units_post": round(units_post, 1),
                "bar_post_bps_H180": round(bar_bps(units_post, e.k, 180.0), 3),
                "bar_post_bps_H30": round(bar_bps(units_post, e.k, 30.0), 3),
                "bar_full_bps_H180": round(bar_bps(units_full, e.k, 180.0), 3),
                "provenance": c.provenance,
            })
        best = min(c["bar_post_bps_H180"] for c in cells)
        worst = max(c["bar_post_bps_H180"] for c in cells)
        best30 = min(c["bar_post_bps_H30"] for c in cells)

        n_running += e.k
        sr_after = expected_max_sharpe(n_running, variance)

        pred_hi, pred_lo = e.predicted_hi, e.predicted_lo
        above_cost = pred_hi > COST["MNQ"]
        above_bar = pred_hi >= best
        above_bar30 = pred_hi >= best30
        # SR* is evaluated at the SAME N the entry would face: cumulative, not at pickup.
        srs_bps = {int(h): round(sr_star_in_bps(sr_after, h), 3) for h in HORIZONS}
        clears_srstar = {int(h): pred_hi >= v for h, v in srs_bps.items()}
        out["entries"].append({
            "id": e.sid, "label": e.label, "overlap": e.overlap, "prior_work": e.prior,
            "kind": e.kind, "cells_k": e.k, "horizon_min": e.horizon,
            "predicted_bps": [pred_lo, pred_hi], "predicted_basis": e.predicted_basis,
            "threshold_units": e.threshold_units,
            "bar_post_best_bps_H180": best, "bar_post_worst_bps_H180": worst,
            "bar_post_best_bps_H30": best30,
            "vs_cost_floor": "above" if above_cost else "at or below",
            "vs_own_bar_H180": ("above at top of range" if above_bar else "BELOW even at top of range"),
            "vs_own_bar_H30": ("above at top of range" if above_bar30 else "BELOW even at top of range"),
            "N_after": n_running, "SR_star_after": round(sr_after, 4),
            "SR_star_after_as_effect_bps": srs_bps,
            "top_of_range_clears_SR_star": clears_srstar,
            "cells": cells,
        })

    out["sequence"] = {
        "N_start": n0, "N_end": n_running, "trials_added": n_running - n0,
        "SR_star_start": round(sr0, 4), "SR_star_end": round(expected_max_sharpe(n_running, variance), 4),
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    r = main()
    print(f"N {r['at_pickup']['N']} -> {r['sequence']['N_end']}  "
          f"SR* {r['at_pickup']['SR_star']} -> {r['sequence']['SR_star_end']}")
    print()
    print("VALIDATION - does this arithmetic recover verdicts already on file?")
    for v in r["validation"]:
        print(f"  {v['case']:<26} eff {v['effect_bps']:>6.3f}  SR {v['sharpe']:>7.4f}  "
              f"vs SR* {v['SR_star_then']}  clears={str(v['clears_SR_star']):<5}  {v['recorded_outcome']}")
    print()
    print("SR* at pickup expressed as a required per-event effect:",
          r["sr_star_as_an_effect_bps"])
    print()
    print(f"{'id':<5}{'overlap':<21}{'predhi':>7}{'barH180':>8}{'barH30':>7}"
          f"{'SR*bps180':>10}{'SR*bps30':>9}{'N':>6}{'SR*':>7}  verdict")
    for e in r["entries"]:
        s180 = e["SR_star_after_as_effect_bps"][180]
        s30 = e["SR_star_after_as_effect_bps"][30]
        v = ("ABOVE bar+cost" if e["vs_own_bar_H180"].startswith("above")
             else ("straddles at H=30m/5m" if e["vs_own_bar_H30"].startswith("above")
                   else "BELOW bar at both horizons"))
        print(f"{e['id']:<5}{e['overlap']:<21}{e['predicted_bps'][1]:>7.2f}"
              f"{e['bar_post_best_bps_H180']:>8.2f}{e['bar_post_best_bps_H30']:>7.2f}"
              f"{s180:>10.2f}{s30:>9.2f}{e['N_after']:>6}{e['SR_star_after']:>7.4f}  {v}")
