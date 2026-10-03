"""W04 data alignment: do UTC-day bars stand in for the 18:00-to-16:55 session holds W04 trades?

A MEASUREMENT: no trial spent, NO STRATEGY RETURN computed - correlations of price changes only, the
same class as `w_series_feasibility.py`. Logs one record per product with --log. decisions.md 73.

    python -m futuresres.reporting.w_daily_alignment --product INDEX     # one product per process
    python -m futuresres.reporting.w_daily_alignment --product MGC
    python -m futuresres.reporting.w_daily_alignment --log

WHY. GLBX.MDP3 offers ohlcv-1d, not ohlcv-eod, and ohlcv-1h costs ~10x more. A 1d bar closes at
00:00 UTC (19:00/20:00 ET): it misses the first 1-2 hours of its own session and carries the first 1-2
hours of the next. W04 is registered on those bars, with a one-session delay against look-ahead. This
module measures, from the on-disk 1-minute data, what the substitution costs:

  1. corr(UTC-day return D, held session return D)   - how well a bar stands in for its session.
  2. corr(UTC-day return D, held session return D+1) - the overlap into the next session (the reason
     for the one-session delay).
  3. corr of 21-day block sums                       - the span a monthly-rebalanced rule lives on.
  4. VENDOR CHECK: on the purchased file's MNQ / MGC rows, the 1d close against the 1-minute last close
     before 00:00 UTC for the same contract and UTC date - confirms what the bar is - and the weekday
     distribution of 1d bars (Sunday-evening bars exist and must be merged into Monday).

UTC-day series rule, as the W04 runner will use it: Sunday bars are dropped, so Monday's return runs
Friday's UTC close to Monday's and includes Sunday evening. Returns same-contract only.
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
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
DAILY_RAW: Final[Path] = ROOT / "data" / "raw_daily" / "glbx-mdp3-20100606-20260912.ohlcv-1d.csv.zst"
RESULT_JSON: Final[Path] = ROOT / "reports" / "w_daily_alignment.json"
REPORT_MD: Final[Path] = ROOT / "reports" / "w_daily_alignment.md"
SERIES: Final[dict[str, str]] = {"INDEX": "NQ_MNQ_spliced", "MGC": "MGC"}
VENDOR_ROOT: Final[dict[str, str]] = {"INDEX": "MNQ", "MGC": "MGC"}
TICK: Final[dict[str, float]] = {"INDEX": 0.25, "MGC": 0.10}
BLOCK: Final[int] = 21


def _minute(product: str) -> pl.LazyFrame:
    et = pl.col("ts_event").dt.convert_time_zone("America/New_York")
    return (pl.scan_parquet(CONTINUOUS / f"{SERIES[product]}.parquet")
              .select("ts_event", "contract", "session", "open", "close")
              .with_columns((et.dt.hour().cast(pl.Int32) * 60 + et.dt.minute().cast(pl.Int32)).alias("mod"),
                            pl.col("ts_event").dt.date().alias("utc_date")))


def sessions(product: str) -> pl.DataFrame:
    """Held session return 18:00 open -> last close at or before 16:55 ET; complete sessions only (the
    U01 / feasibility rule)."""
    agg = (_minute(product).sort("ts_event").group_by(["session", "contract"])
             .agg(pl.col("open").first().alias("open0"),
                  pl.col("mod").last().alias("last_mod"),
                  pl.col("close").filter((pl.col("mod") <= 16 * 60 + 55) &
                                         (pl.col("mod") >= 9 * 60)).last().alias("close_1655"))
             .sort("session").collect(engine="streaming"))
    agg = agg.with_columns(pl.col("session").dt.year().alias("year"))
    agg = agg.with_columns(pl.col("last_mod").mode().first().over("year").alias("close_mod"))
    agg = agg.with_columns((((pl.col("close_mod") - pl.col("last_mod")) % 1440) <= 5).alias("complete"),
                           (pl.col("close_1655") / pl.col("open0")).log().alias("r_held"))
    return (agg.filter(pl.col("complete") & pl.col("r_held").is_finite())
               .select("session", "contract", "r_held"))


def utc_days(product: str) -> pl.DataFrame:
    """Last 1-minute close per (contract, UTC date), Sundays dropped, log return same-contract."""
    d = (_minute(product).sort("ts_event").group_by(["utc_date", "contract"])
           .agg(pl.col("close").last().alias("utc_close"))
           .filter(pl.col("utc_date").dt.weekday() != 7)
           .sort(["contract", "utc_date"]).collect(engine="streaming"))
    return (d.with_columns((pl.col("utc_close") / pl.col("utc_close").shift(1).over("contract"))
                           .log().alias("r_utc"))
             .filter(pl.col("r_utc").is_finite()))


def _block_corr(x: np.ndarray, y: np.ndarray) -> tuple[float, int]:
    n = len(x) // BLOCK
    if n < 10:
        return float("nan"), n
    bx = x[: n * BLOCK].reshape(n, BLOCK).sum(1); by = y[: n * BLOCK].reshape(n, BLOCK).sum(1)
    return float(np.corrcoef(bx, by)[0, 1]), n


def vendor_check(product: str, u: pl.DataFrame) -> dict:
    root = VENDOR_ROOT[product]
    v = (pl.scan_csv(DAILY_RAW).select("ts_event", "close", "symbol")
           .filter(pl.col("symbol").str.contains(f"^{root}[FGHJKMNQUVXZ][0-9]+$"))
           .with_columns(pl.col("ts_event").str.slice(0, 10).str.to_date().alias("utc_date"))
           .collect())
    weekdays = {str(k): int(n) for k, n in
                v.group_by(pl.col("utc_date").dt.weekday()).len().sort("utc_date").iter_rows()}
    one_min = (_minute(product).sort("ts_event").group_by(["utc_date", "contract"])
                 .agg(pl.col("close").last().alias("m_close"))
                 # the vendor names contracts with a ONE-digit year (MGCM9); the decade is resolved by
                 # the bar's date - the W04 runner must do the same
                 .with_columns((pl.col("contract").str.slice(0, pl.col("contract").str.len_chars() - 4)
                                + pl.col("contract").str.slice(-1)).alias("vendor_symbol"))
                 .collect(engine="streaming"))
    j = v.join(one_min, left_on=["utc_date", "symbol"], right_on=["utc_date", "vendor_symbol"], how="inner")
    diff = (j["close"] - j["m_close"]).abs().to_numpy()
    return {"vendor_bars": v.height, "matched_to_1m": j.height,
            "share_within_half_tick": float((diff <= TICK[product] / 2).mean()) if len(diff) else None,
            "median_abs_diff_ticks": float(np.median(diff) / TICK[product]) if len(diff) else None,
            "bars_by_iso_weekday": weekdays}


def run(product: str) -> dict:
    s = sessions(product)
    u = utc_days(product)
    j = (u.join(s, left_on=["utc_date", "contract"], right_on=["session", "contract"], how="inner")
          .sort("utc_date"))
    nxt = s.with_columns(pl.col("r_held").alias("r_next")).select("session", "contract", "r_next")
    j = j.with_columns(pl.col("utc_date").alias("key"))
    out: dict = {"product": product, "eras": {}}
    for name, lo in (("full", "2010-01-01"), ("post_2021", "2021-01-01")):
        e = j.filter(pl.col("utc_date") >= pl.lit(lo).str.to_date())
        x, y = e["r_utc"].to_numpy(), e["r_held"].to_numpy()
        # next session: the first held session after this UTC date, same contract
        e2 = (e.sort("utc_date").join_asof(nxt.sort("session").rename({"session": "next_session"}),
                                           left_on="utc_date", right_on="next_session", by="contract",
                                           strategy="forward", allow_exact_matches=False)
                .filter(pl.col("r_next").is_finite()))
        bc, nb = _block_corr(x, y)
        out["eras"][name] = {
            "days": e.height,
            "corr_same_session": float(np.corrcoef(x, y)[0, 1]),
            "corr_next_session": float(np.corrcoef(e2["r_utc"].to_numpy(), e2["r_next"].to_numpy())[0, 1]),
            "sd_ratio_utc_over_held": float(x.std() / y.std()),
            f"corr_{BLOCK}d_blocks": bc, "blocks": nb,
        }
    out["vendor"] = vendor_check(product, u)
    return out


def render(res: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# W04 data alignment — UTC-day bars against 18:00→16:55 session holds")
    a("")
    a("Generated by `python -m futuresres.reporting.w_daily_alignment`. A measurement: correlations of "
      "price changes, no strategy return, no trial. `decisions.md` §73–§74.")
    a("")
    a("| product | era | days | corr, same session | corr, next session | SD ratio | corr, 21-day blocks (n) |")
    a("|---|---|---|---|---|---|---|")
    for p in ("INDEX", "MGC"):
        if p not in res:
            continue
        for era, e in res[p]["eras"].items():
            a(f"| {p} | {era} | {e['days']:,} | {e['corr_same_session']:.3f} | {e['corr_next_session']:.3f} | "
              f"{e['sd_ratio_utc_over_held']:.3f} | {e['corr_21d_blocks']:.3f} ({e['blocks']}) |")
    a("")
    a("**Vendor check** (purchased ohlcv-1d rows for the micro, against the 1-minute last close before "
      "00:00 UTC, same contract and date):")
    a("")
    for p in ("INDEX", "MGC"):
        if p not in res:
            continue
        v = res[p]["vendor"]
        a(f"- {VENDOR_ROOT[p]}: {v['matched_to_1m']:,} of {v['vendor_bars']:,} bars matched; "
          f"{v['share_within_half_tick']:.1%} within half a tick (median {v['median_abs_diff_ticks']:.1f} "
          f"ticks); bars by ISO weekday {v['bars_by_iso_weekday']}")
    a("")
    return "\n".join(w)


def log_measurements(res: dict) -> None:
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "measurements.jsonl")
    for p in ("INDEX", "MGC"):
        rec = log.append(Trial(
            trial_id=log.next_id("m"), hypothesis_id="W04", symbol=p,
            date_range=("2010-06-06", "2026-08-27"), status="completed",
            params={"kind": "daily_bar_alignment", **res[p]},
            note=("kind=measurement; NOT a trial and NOT counted in N. UTC-day (ohlcv-1d) returns against "
                  "18:00-to-16:55 held session returns: correlations and SD ratio only, no strategy "
                  "return. decisions.md 74."),
        ))
        print(f"logged {rec['trial_id']} ({p})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.w_daily_alignment")
    ap.add_argument("--product", choices=list(SERIES))
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args(argv)
    res: dict = json.loads(RESULT_JSON.read_text()) if RESULT_JSON.exists() else {}
    if args.product:
        res[args.product] = run(args.product)
        RESULT_JSON.write_text(json.dumps(res, indent=1) + "\n")
    REPORT_MD.write_text(render(res))
    print(f"wrote {RESULT_JSON.name}, {REPORT_MD.name}")
    if args.log:
        log_measurements(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
