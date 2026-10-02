"""T01 — volume-clock resampling. T_SERIES_CANDIDATES.md Class A. A MEASUREMENT, NOT A
HYPOTHESIS. Consumes no trials; logs to `measurements.jsonl`.

    python -m futuresres.reporting.t01_volume_clock --product MNQ --k 1
    python -m futuresres.reporting.t01_volume_clock --product MNQ --k 5
    python -m futuresres.reporting.t01_volume_clock --product MNQ --k 15
    python -m futuresres.reporting.t01_volume_clock --product MGC --k 1
    python -m futuresres.reporting.t01_volume_clock --product MGC --k 5
    python -m futuresres.reporting.t01_volume_clock --product MGC --k 15

ONE (PRODUCT, K) PER PROCESS. Loading both continuous series in one process was OOM-killed
even via a streaming single-column scan; looping all three k values for one product in a
single process was ALSO OOM-killed, measured at ~600 MB peak for one k alone with headroom as
low as ~900 MB available and falling under contention from other processes. This machine has
2.7 GB total — CHECKPOINT's documented constraint.
Each invocation does exactly one (product, k) and merges its result into
`reports/t01_volume_clock.json`; nothing is held across invocations.

WHAT THIS MEASURES. Three bar sizes, k in {1, 5, 15}. For each k:

  TRADE-MINUTE comparator ("calendar" in the JSON) — group consecutive existing rows (session, contract) into buckets of
  size k' rows, k' chosen so the resulting bar count matches the volume partition's ACTUAL
  count at this k (not assumed to be exactly k) — see "cardinality matching" below.

  VOLUME partition — accumulate volume within (session, contract); close a bar when
  cumulative volume crosses a threshold of k times the product's mean row volume. The
  resulting bar count is whatever it is; it is not forced to anything.

Both partitions are built from the SAME underlying rows — no new data, no different price
path — so this is a comparison of partitions, not of information.

A CORRECTION TO THE DESIGN DOCUMENT, FOUND BEFORE BUILDING ANYTHING. T01 as drafted describes
"dead-hour bars counted as full observations" and a resampling that would remove them. The
continuous parquet has **zero** volume==0 rows: an untraded minute is simply ABSENT, not
forward-filled. There is no dead bar to remove. What volume sampling can act on instead, and
it is still real: volume per TRADED row spans orders of magnitude (measured below), so
calendar sampling gives a 1-contract minute the same weight as a multi-thousand-contract one.
The mechanism is unequal weighting of traded rows, not inclusion of untraded ones. Recorded as
a correction to the draft rather than silently matched, per programme convention.

CARDINALITY MATCHING, WHICH IS THE TRAP CHECK. Build the volume partition first at threshold
k * mean_volume and measure its actual bar count n_vol. Then build the calendar comparator
with row-group size round(n_rows / n_vol), so its bar count n_cal is as close to n_vol as
integer grouping allows. With n held equal on both sides, ANY kurtosis difference is NOT
attributable to a change in n — it is attributable to where the partition boundaries fall.
Report n_vol, n_cal and their ratio explicitly so this is checked, not assumed. Also report
realised variance (sum of squared log returns) under each partition: both partition the SAME
price path, so realised variance should be close across partitions at matched n, and a large
divergence would mean the construction is wrong rather than that volume sampling works.

[Added after the first run, and kept beside the sentence above rather than replacing it.] The
raw ratio came back 0.69-0.96. Rather than explain that after the fact, it was TESTED: a
bar-to-bar series drops each session's first leg (first traded close -> first bar close), and
that leg differs by partition. `realised_var_ratio_same_path` adds it back to both, so both
cover the identical path. The criterion above is then applied to THAT ratio.

A STATED LIMITATION OF BUILDING VOLUME BARS FROM ALREADY-AGGREGATED ROWS, NOT RAW TICKS. A
single very-high-volume MINUTE can by itself exceed several bars' worth of the volume
threshold. Since only one OHLC observation exists for that minute, it cannot be split — it
appears as one (wide) bar rather than several. This under-resolves exactly the kind of event
(a news print, a session open) most relevant to kurtosis, in the direction of UNDERSTATING any
kurtosis reduction the true tick-level volume clock would show. Measured and reported, not
assumed away.

n_min (the DSR event floor) reuses `kurtosis.dsr_min_events` — this report does not define a
second formula for the same quantity.

NOT MEASURED HERE: the SMALLEST_RESOLVING sample-size floor (`level_rates.py`,
`detectability.py` — e.g. 19,722 non-overlapping MNQ events at 60m) that blocks L01/L08/F01.
That floor comes from `integrity/calibration.run_floor`, a bootstrap injection-recovery sweep
over sample-size rungs with many replications — a different, much larger computation from the
one here, and re-running it under a volume clock is out of scope for a zero-trial S1
measurement. This module does not claim to speak to it beyond the arithmetic check in its own
report.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

from futuresres.reporting.kurtosis import dsr_min_events

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
RESULT_JSON: Final[Path] = ROOT / "reports" / "t01_volume_clock.json"
REPORT_MD: Final[Path] = ROOT / "reports" / "t01_volume_clock.md"

K_VALUES: Final[tuple[int, ...]] = (1, 5, 15)

# S4-blocked firing counts this measurement is asked to check against (level_rates.md,
# firing_rates.md). The floor these are blocked against (SMALLEST_RESOLVING) is NOT
# recalibrated here — see module docstring.
# Best (largest) measured cell per entry and product. L01/L08 from `level_rates.md`. F01 from
# `measured_rates.json`, NOT the 4,125 the T-series brief quotes: 4,125 is the once-per-session
# DATA CEILING the gate used before decisions.md S22 measured the condition - 3,523 MNQ /
# 3,449 MGC at best, 66 / 115 at worst. Using the ceiling would overstate F01 by 17-62x at the
# cells that matter.
S4_BLOCKED: Final[dict[str, dict[str, int]]] = {
    "L01": {"MNQ": 237, "MGC": 211},
    "L08": {"MNQ": 705, "MGC": 698},
    "F01": {"MNQ": 3523, "MGC": 3449},
}
SMALLEST_RESOLVING_60M: Final[dict[str, int]] = {"MNQ": 19_722, "MGC": 5_620}


@dataclass(slots=True)
class PartitionStat:
    kind: str          # "calendar" | "volume"
    k: int
    n_bars: int
    n_returns: int
    skew: float
    kurtosis: float     # non-excess
    n_min: int
    realised_var: float  # sum of squared log returns


def _log_returns_1step(close: pl.Series, session: pl.Series, contract: pl.Series,
                        same_group: pl.Series) -> np.ndarray:
    """Bar-to-bar log return, excluding any step that crosses a (session, contract) boundary."""
    logp = close.log()
    prev = logp.shift(1)
    ok = same_group & prev.is_not_null()
    r = (logp - prev).filter(ok)
    return r.to_numpy()


def _stat(kind: str, k: int, r: np.ndarray, n_bars: int) -> PartitionStat:
    r = r[np.isfinite(r)]
    mean, sd = r.mean(), r.std(ddof=1)
    z = (r - mean) / sd
    skew = float((z ** 3).mean())
    kurt = float((z ** 4).mean())
    return PartitionStat(kind, k, n_bars, r.size, skew, kurt, dsr_min_events(kurt),
                          float((r ** 2).sum()))


def calendar_partition(df: pl.DataFrame, group_size: int) -> pl.DataFrame:
    """Non-overlapping buckets of `group_size` consecutive existing rows, within
    (session, contract). A bucket never spans a session or contract boundary."""
    idx = pl.int_range(pl.len()).over(["session", "contract"])
    bucket = (idx // group_size).alias("bucket")
    return (
        df.with_columns(bucket)
        .group_by(["session", "contract", "bucket"], maintain_order=True)
        .agg(
            pl.col("ts_event").last(),
            pl.col("close").last(),
            pl.col("volume").sum(),
            pl.len().alias("n_rows"),
        )
        .sort(["contract", "ts_event"])
    )


def volume_partition(df: pl.DataFrame, threshold: float) -> pl.DataFrame:
    """Non-overlapping buckets closing each time cumulative volume within (session,
    contract) crosses `threshold`. A single row whose own volume exceeds several
    thresholds' worth still yields one bucket — see module docstring."""
    cumvol = pl.col("volume").cum_sum().over(["session", "contract"])
    bucket = ((cumvol - 1) // threshold).cast(pl.Int64).alias("bucket")
    return (
        df.with_columns(bucket)
        .group_by(["session", "contract", "bucket"], maintain_order=True)
        .agg(
            pl.col("ts_event").last(),
            pl.col("close").last(),
            pl.col("volume").sum(),
            pl.len().alias("n_rows"),
        )
        .sort(["contract", "ts_event"])
    )


def bars_to_stat(kind: str, k: int, bars: pl.DataFrame) -> PartitionStat:
    same_group = (
        (bars["contract"] == bars["contract"].shift(1))
        & (bars["session"] == bars["session"].shift(1))
    ).fill_null(False)
    r = _log_returns_1step(bars["close"], bars["session"], bars["contract"], same_group)
    return _stat(kind, k, r, bars.height)


def first_leg_rv(df: pl.DataFrame, bars: pl.DataFrame) -> float:
    """Sum over sessions of the squared log move from the session's first traded close to its
    first BAR close - the stretch of path every bar-to-bar return series drops, because a
    session's first bar has no predecessor. It differs by partition: a volume clock's first
    bar can span hours of thin overnight trade. Adding it back makes both partitions cover the
    same path, which is what the pre-stated realised-variance check needs."""
    keys = ["session", "contract"]
    first_row = df.group_by(keys, maintain_order=True).agg(pl.col("close").first().alias("c0"))
    first_bar = bars.group_by(keys, maintain_order=True).agg(pl.col("close").first().alias("c1"))
    j = first_row.join(first_bar, on=keys, how="inner")
    leg = (j["c1"].log() - j["c0"].log()).to_numpy()
    return float(np.nansum(leg ** 2))


def run_one_k(product: str, k: int) -> dict:
    """One (product, k). See module docstring for why this is the unit of a process."""
    import gc

    df = pl.read_parquet(CONTINUOUS / f"{product}.parquet",
                         columns=["ts_event", "contract", "session", "close", "volume"])
    n_rows = df.height
    total_volume = int(df["volume"].sum())
    mean_vol = total_volume / n_rows
    vol = df["volume"]
    vol_dist = {
        "min": int(vol.min()), "p50": float(vol.quantile(0.5)),
        "p90": float(vol.quantile(0.9)), "p99": float(vol.quantile(0.99)),
        "max": int(vol.max()), "mean": round(mean_vol, 3),
    }
    del vol

    threshold = k * mean_vol
    vol_bars = volume_partition(df, threshold=threshold)
    vstat = bars_to_stat("volume", k, vol_bars)
    v_leg = first_leg_rv(df, vol_bars)
    # Single-row absorption, the limitation stated in the docstring BEFORE any result: a row
    # whose own volume exceeds several thresholds cannot be split, so it becomes one wide bar.
    absorption = {
        "single_row_bar_share": float((vol_bars["n_rows"] == 1).mean()),
        "bars_over_3x_threshold": int((vol_bars["volume"] > 3 * threshold).sum()),
        "bars_over_3x_threshold_single_row": int(
            ((vol_bars["volume"] > 3 * threshold) & (vol_bars["n_rows"] == 1)).sum()),
        "max_row_volume_over_threshold": float(df["volume"].max() / threshold),
    }
    del vol_bars
    gc.collect()

    # cardinality match: calendar group size chosen so n_bars tracks the volume
    # partition's ACTUAL count, not an assumed k.
    group_size = max(1, round(n_rows / vstat.n_bars))
    cal_bars = calendar_partition(df, group_size)
    cstat = bars_to_stat("calendar", group_size, cal_bars)
    c_leg = first_leg_rv(df, cal_bars)
    del cal_bars, df
    gc.collect()

    k_result = {
        "k_nominal": k,
        "calendar_group_size_used": group_size,
        "volume_threshold": round(k * mean_vol, 3),
        "absorption": absorption,
        "volume": asdict(vstat),
        "calendar": asdict(cstat),
        "n_ratio_volume_over_calendar": round(vstat.n_bars / cstat.n_bars, 4),
        "realised_var_ratio_same_path": (
            round((vstat.realised_var + v_leg) / (cstat.realised_var + c_leg), 4)),
        "first_leg_share_of_rv": {
            "volume": round(v_leg / (vstat.realised_var + v_leg), 4),
            "calendar": round(c_leg / (cstat.realised_var + c_leg), 4)},
        "realised_var_ratio_volume_over_calendar": (
            round(vstat.realised_var / cstat.realised_var, 4)
            if cstat.realised_var else None
        ),
    }

    s4 = {hid: counts.get(product) for hid, counts in S4_BLOCKED.items()}
    return {
        "product": product,
        "n_rows_native": n_rows,
        "total_volume": total_volume,
        "volume_per_row_distribution": vol_dist,
        "k_result": k_result,
        "s4_blocked_firing_counts": s4,
        "smallest_resolving_60m": SMALLEST_RESOLVING_60M.get(product),
    }


def render(all_results: dict[str, dict]) -> str:
    w: list[str] = []
    a = w.append
    a("# T01 — volume-clock resampling")
    a("")
    a("Generated by `python -m futuresres.reporting.t01_volume_clock`, one (product, k) per "
      "process. A MEASUREMENT: **no trial spent**, one record per product in "
      "`measurements.jsonl`. `T_SERIES_CANDIDATES.md` T01; `decisions.md` §65.")
    a("")
    a("## 1. The draft's mechanism is wrong as stated: there are no dead bars")
    a("")
    a("The continuous parquet has **zero** `volume == 0` rows in either product — an untraded "
      "minute is absent, not forward-filled. What volume sampling can act on is unequal "
      "weighting of *traded* minutes:")
    a("")
    a("| product | traded rows | min | p50 | p90 | p99 | max | mean |")
    a("|---|---|---|---|---|---|---|---|")
    for p, r in all_results.items():
        d = r["volume_per_row_distribution"]
        a(f"| {p} | {r['n_rows_native']:,} | {d['min']} | {d['p50']:.0f} | {d['p90']:.0f} | "
          f"{d['p99']:.0f} | {d['max']:,} | {d['mean']:.1f} |")
    a("")
    a("## 2. Effective n falls under a volume clock; it does not rise")
    a("")
    a("At a threshold equal to the mean volume of a traded minute — the volume clock's natural "
      "'one bar per average minute' — the bar count is:")
    a("")
    a("| product | traded rows | volume bars | ratio |")
    a("|---|---|---|---|")
    for p, r in all_results.items():
        k1 = next(x for x in r["k_results"] if x["k_nominal"] == 1)
        a(f"| {p} | {r['n_rows_native']:,} | {k1['volume']['n_bars']:,} | "
          f"{k1['volume']['n_bars'] / r['n_rows_native']:.2f}× |")
    a("")
    a("Volume is right-skewed (median well below mean), so most minutes are merged. **The "
      "draft's trap — 'if effective n rises, check it is not manufactured' — is not reached: "
      "n falls.** Nothing can have been manufactured.")
    a("")
    a("## 3. Kurtosis at matched n")
    a("")
    a("The calendar comparator groups consecutive *traded* rows (a trade-minute clock, not "
      "wall-clock time), with group size chosen after the volume partition so the two bar "
      "counts match. Its kurtosis is therefore NOT comparable to `kurtosis.md`'s 1-minute "
      "figures, which keep only returns exactly one wall-clock minute apart — a different "
      "object, and the reason MGC's comparator reads higher than 226.5.")
    a("")
    a("| product | k | partition | n bars | kurtosis | n_min | single-row bars | bars > 3× thr | max row / thr | RV ratio raw | RV ratio, same path |")
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    for p, r in all_results.items():
        for row in sorted(r["k_results"], key=lambda x: x["k_nominal"]):
            v, c, ab = row["volume"], row["calendar"], row.get("absorption", {})
            a(f"| {p} | {row['k_nominal']} | volume | {v['n_bars']:,} | **{v['kurtosis']:.1f}** | "
              f"{v['n_min']} | {ab.get('single_row_bar_share', float('nan')):.1%} | "
              f"{ab.get('bars_over_3x_threshold', '—')} | "
              f"{ab.get('max_row_volume_over_threshold', float('nan')):.1f} | "
              f"{row['realised_var_ratio_volume_over_calendar']:.2f} | "
              f"{row.get('realised_var_ratio_same_path', float('nan')):.3f} |")
            a(f"| {p} | {row['k_nominal']} | trade-minute ({row['calendar_group_size_used']} rows) | "
              f"{c['n_bars']:,} | {c['kurtosis']:.1f} | {c['n_min']} | | | | | |")
    a("")
    def valid(x: dict) -> bool:
        v = x.get("realised_var_ratio_same_path")
        return v is not None and 0.9 <= v <= 1.1

    cells = [(p, x) for p, r in all_results.items() for x in r["k_results"]]
    good = [(p, x) for p, x in cells if valid(x)]
    bad = [(p, x) for p, x in cells if not valid(x)]
    bad_names = ", ".join(f"{p} k={x['k_nominal']}" for p, x in bad) or "none"
    falls = [(p, x["k_nominal"]) for p, x in good
             if x["volume"]["kurtosis"] < x["calendar"]["kurtosis"]]
    rises = [(p, x["k_nominal"]) for p, x in good
             if x["volume"]["kurtosis"] >= x["calendar"]["kurtosis"]]
    a(f"**Only cells that pass the construction's own pre-stated check (below) are findings.** "
      f"Of {len(cells)} cells, {len(good)} pass; "
      f"{bad_names} "
      f"fail and their kurtosis figures are withdrawn, not interpreted. Among the {len(good)} "
      f"valid cells, kurtosis falls under the volume clock in **{len(falls)}** "
      f"({', '.join(f'{p} k={k}' for p, k in falls) or 'none'}) and rises in **{len(rises)}** "
      f"({', '.join(f'{p} k={k}' for p, k in rises) or 'none'}).")
    a("")
    a("The rise is the limitation the module docstring stated before anything ran: built from "
      "1-minute rows, a volume clock can MERGE quiet minutes but never SPLIT a busy one, so a "
      "minute holding several thresholds' volume becomes one wide bar. The `single-row bars` "
      "and `bars > 3× thr` columns measure it. At k=1 the threshold is the mean minute volume, "
      "so every above-average minute is a single bar by construction — near that threshold the "
      "'volume clock' is still largely the minute clock. A true volume clock needs tick or "
      "sub-minute data; none is on disk (`trades` is null, no `tbbo`).")
    a("")
    same = [x.get("realised_var_ratio_same_path") for r in all_results.values()
            for x in r["k_results"]]
    same = [v for v in same if v is not None]
    raw = [x["realised_var_ratio_volume_over_calendar"] for r in all_results.values()
           for x in r["k_results"]]
    if same:
        ok = all(0.9 <= v <= 1.1 for v in same)
        a(f"**The trap check, applied as pre-stated.** Before any result the module said that "
          f"realised variance should be close across partitions at matched n, and that a large "
          f"divergence would mean the construction is wrong. Raw, it was {min(raw):.2f}–"
          f"{max(raw):.2f}. One candidate cause was tested rather than asserted: each bar-to-bar "
          f"series drops the session's first leg, which is longer on a volume clock. Restoring it to both "
          f"so they cover the identical path gives **{min(same):.3f}–{max(same):.3f}**. The "
          f"boundary leg is a PARTIAL explanation: it closes most of the gap on coarse bars "
          f"(MGC k=15) and almost none on fine ones (MNQ k=1 moves 0.962 to 0.963); the residual "
          f"is unexplained. "
          + ("Within ±10% in every cell: **the construction passes its own pre-stated check**, "
             "and the raw gap was the session boundary, not lost or created information."
             if ok else
             "Outside ±10% in at least one cell: **the construction FAILS its own pre-stated "
             "check in the cells listed above**, whose kurtosis comparisons are therefore "
             "withdrawn. Whether the construction is wrong there or the equal-variance premise "
             "fails under MGC's price discreteness (a 0.10 tick that was 0.78 bps of price in "
             "2010-2018 against a 1-minute sigma of 3.5 bps, with 14% of 1-minute returns "
             "exactly zero - `t02_t04_scale_collinearity.md` - so bid-ask bounce is not the iid "
             "noise the premise assumes) "
             "is NOT resolved by this measurement, and the withdrawal does not depend on which."))
        a("")
    a("## 4. What it does to the S4-blocked entries: nothing, and the reason is on file")
    a("")
    a("The draft says lower kurtosis improves three things at once. Each against the record:")
    a("")
    a("- **Bootstrap α.** `calibration.md` §A measured coverage at MNQ γ₄ = 115 and MGC γ₄ = 226 "
      "and found them **indistinguishable** (spread between cells the size of the Monte Carlo "
      "error). A 2× kurtosis difference is invisible to the calibration, so an 18–80% reduction "
      "cannot move α\\*. Refuted by a measurement already on file.")
    a("- **DSR γ₄ term (n_min).** It does fall — but n_min is tens of events, and the floors that "
      "block anything are thousands. It was never the binding floor.")
    a("- **The detection floor.** The floor that blocks L01, L08 and F01 is `SMALLEST_RESOLVING` "
      "(19,722 MNQ / 5,620 MGC at 60m), from an injection-recovery power sweep on a *mean*. Its "
      "driver is σ and n; at thousands of events the mean's sampling distribution is "
      "near-normal whatever γ₄ is. **Not recalibrated here** — that is `integrity/calibration."
      "run_floor` re-run under a volume clock, out of scope for a zero-trial measurement — so "
      "this point is argued, not measured, and is labelled so.")
    a("")
    rows = []
    for p, r in all_results.items():
        s4 = r["s4_blocked_firing_counts"]
        for hid, n in s4.items():
            if n is not None:
                rows.append(f"{hid} {p} {n:,} vs {r['smallest_resolving_60m']:,} "
                            f"({r['smallest_resolving_60m'] / n:.0f}×)")
    a("Gaps to close, at each entry's BEST measured cell: " + "; ".join(rows) + ". F01's "
      "figures are the measured ones; the brief's 4,125 is the once-per-session ceiling the "
      "gate used before §22 measured the condition (worst cells 66 MNQ / 115 MGC). MGC's 60m "
      "floor (5,620) is lower than MNQ's, so F01 on MGC is the closest of all — still below it, "
      "and F01's MGC cells test a mechanism stated for the equity close. These are counts of how often each "
      "*condition* fires. A clock changes them only by redefining the condition (what '15 "
      "minutes away' or 'one 5m bar' means), which is a new hypothesis, not a resampling. "
      "**No entry crosses its floor. None qualifies for re-registration on this evidence. "
      "Nothing in `hypotheses.yaml` changes.**")
    a("")
    return "\n".join(w)


def log_measurements(all_results: dict[str, dict]) -> None:
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "measurements.jsonl")
    for p, r in all_results.items():
        ks = sorted(r["k_results"], key=lambda x: x["k_nominal"])
        rec = log.append(Trial(
            trial_id=log.next_id("m"), hypothesis_id="T01", symbol=p,
            date_range=("2010-06-06", "2026-08-27"), status="completed",
            params={"kind": "volume_clock",
                    "rows": r["n_rows_native"],
                    "kurtosis_volume": {x["k_nominal"]: x["volume"]["kurtosis"] for x in ks},
                    "kurtosis_calendar": {x["k_nominal"]: x["calendar"]["kurtosis"] for x in ks},
                    "bars_volume_k1": ks[0]["volume"]["n_bars"]},
            note=("kind=measurement; NOT a trial and NOT counted in N. T-series T01: volume vs "
                  "trade-minute clock at matched n. No S4-blocked entry crosses its floor; "
                  "none re-registered. decisions.md 65."),
        ))
        print(f"logged {rec['trial_id']} ({p})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.t01_volume_clock")
    ap.add_argument("--product", choices=["MNQ", "MGC"])
    ap.add_argument("--k", type=int, choices=K_VALUES)
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--render", action="store_true", help="rebuild the report from the JSON")
    args = ap.parse_args(argv)

    if args.render or args.log:
        existing = json.loads(RESULT_JSON.read_text(encoding="utf-8"))
        REPORT_MD.write_text(render(existing), encoding="utf-8")
        print(f"wrote {REPORT_MD}")
        if args.log:
            log_measurements(existing)
        return 0
    if not (args.product and args.k):
        ap.error("--product and --k are required unless --render/--log")

    one = run_one_k(args.product, args.k)

    existing: dict[str, dict] = {}
    if RESULT_JSON.exists():
        existing = json.loads(RESULT_JSON.read_text(encoding="utf-8"))
    entry = existing.setdefault(args.product, {
        "product": args.product,
        "n_rows_native": one["n_rows_native"],
        "total_volume": one["total_volume"],
        "volume_per_row_distribution": one["volume_per_row_distribution"],
        "k_results": [],
        "s4_blocked_firing_counts": one["s4_blocked_firing_counts"],
        "smallest_resolving_60m": one["smallest_resolving_60m"],
    })
    entry["k_results"] = [r for r in entry["k_results"] if r["k_nominal"] != args.k]
    entry["k_results"].append(one["k_result"])

    RESULT_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULT_JSON.write_text(json.dumps(existing, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.product} k={args.k} into {RESULT_JSON}")

    complete = all(
        args.product in existing and len(existing[p]["k_results"]) == len(K_VALUES)
        for p in ("MNQ", "MGC") if p in existing
    ) and set(existing) == {"MNQ", "MGC"}
    if complete:
        REPORT_MD.write_text(render(existing), encoding="utf-8")
        print(f"wrote {REPORT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
