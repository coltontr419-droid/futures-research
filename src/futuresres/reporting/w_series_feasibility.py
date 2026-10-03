"""W-series feasibility: can daily-horizon strategies run inside this account, and at what cost?

A MEASUREMENT: no trial spent, NO STRATEGY RETURN computed. Logs one record per product with --log.

    python -m futuresres.reporting.w_series_feasibility --product INDEX
    python -m futuresres.reporting.w_series_feasibility --product MGC
    python -m futuresres.reporting.w_series_feasibility --log

THE PREMISE BEING CHECKED. The programme searched intraday, where a 0.48 bps round trip is the same
size as the effects found. At a daily horizon the same cost is ~0.4% of a session's typical move. The
record files daily and multi-day horizons as forbidden by the account ("flat by 17:00 ET"), but a
position opened at the 18:00 reopen and closed at 16:55 never crosses 17:00; chaining such session
holds re-creates daily exposure at one round trip per day. Three things decide whether that is real,
and this module measures the two that data can answer:

  1. RE-ENTRY. The chained position is flat from 16:55 to the next session's first print. Reported:
     the SD of that excluded window's return against the SD of the full close-to-close day (how much
     of the day's movement the chain gives up) and the per-day cost of one round trip in bps of the
     day's SD. ONLY dispersions are computed - a MEAN of the excluded window would be the return of an
     unregistered overnight-hold hypothesis (F13's), which is exactly what §59 declined to compute.
  2. GRANULARITY. Notional per contract and its annualised dollar volatility against a $50,000
     account, by era. If one contract already exceeds the operative bar's 12.4% volatility ceiling,
     no position can be sized to it.
  3. Correlation of daily returns between the two instruments, for diversification arithmetic. Not a
     strategy return; the same class of measurement as §59's conditioner correlations.

The third question - whether the firm treats an 18:00-to-16:55 hold as within "flat by 17:00" - is not
a data question and is stated in decisions.md 72 as the load-bearing premise to confirm.
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
RESULT_JSON: Final[Path] = ROOT / "reports" / "w_series_feasibility.json"
REPORT_MD: Final[Path] = ROOT / "reports" / "w_series_feasibility.md"
SERIES: Final[dict[str, str]] = {"INDEX": "NQ_MNQ_spliced", "MGC": "MGC"}
MULTIPLIER: Final[dict[str, float]] = {"INDEX": 2.0, "MGC": 10.0}      # MNQ $2/pt, MGC 10 oz
COST_BPS: Final[dict[str, float]] = {"INDEX": 0.48, "MGC": 0.65}
ACCOUNT: Final[float] = 50_000.0
VOL_CEILING: Final[float] = 0.124        # operative bar's max vol at <=3 events (CHECKPOINT, §62)
ERAS: Final = (("2010-2015", 2010, 2015), ("2016-2020", 2016, 2020), ("2021-2026", 2021, 2026))


def daily(product: str) -> pl.DataFrame:
    """Per CME session: last close at or before 16:55 ET, first open, last close. Complete sessions
    only (traded within 5 minutes of their modal close - the U01 rule), so truncated early-NQ sessions
    (§67, §68) cannot pose as days."""
    et = pl.col("ts_event").dt.convert_time_zone("America/New_York")
    mod = et.dt.hour().cast(pl.Int32) * 60 + et.dt.minute().cast(pl.Int32)
    lf = (pl.scan_parquet(CONTINUOUS / f"{SERIES[product]}.parquet")
            .select("ts_event", "contract", "session", "open", "close")
            .with_columns(mod.alias("mod")))
    agg = (lf.sort("ts_event").group_by(["session", "contract"])
             .agg(pl.col("open").first().alias("open0"),
                  pl.col("close").last().alias("close_last"),
                  pl.col("mod").last().alias("last_mod"),
                  pl.col("close").filter((pl.col("mod") <= 16 * 60 + 55) &
                                         (pl.col("mod") >= 9 * 60)).last().alias("close_1655"))
             .sort("session").collect(engine="streaming"))
    agg = agg.with_columns(pl.col("session").dt.year().alias("year"))
    agg = agg.with_columns(pl.col("last_mod").mode().first().over("year").alias("close_mod"))
    agg = agg.with_columns((((pl.col("close_mod") - pl.col("last_mod")) % 1440) <= 5).alias("complete"))
    same = pl.col("contract") == pl.col("contract").shift(1)
    agg = agg.with_columns(
        (pl.col("close_last") / pl.col("close_last").shift(1)).log().alias("r_day"),
        (pl.col("open0") / pl.col("close_1655").shift(1)).log().alias("r_excluded"),
        (pl.col("close_1655") / pl.col("open0")).log().alias("r_held"),
        (same & pl.col("complete") & pl.col("complete").shift(1)).alias("ok"),
    )
    return agg.filter(pl.col("ok") & pl.col("r_day").is_finite() & pl.col("r_excluded").is_finite()
                      & pl.col("r_held").is_finite())


def run(product: str) -> dict:
    d = daily(product)
    out: dict = {"product": product, "sessions": d.height, "eras": {}}
    for name, lo, hi in ERAS:
        e = d.filter(pl.col("year").is_between(lo, hi))
        if e.height < 50:
            continue
        sd_day = float(e["r_day"].std())
        sd_ex = float(e["r_excluded"].std())
        price = float(e["close_last"].median())
        notional = price * MULTIPLIER[product]
        vol_ann = sd_day * math.sqrt(252)
        out["eras"][name] = {
            "sessions": e.height,
            "sd_day_bps": sd_day * 1e4,
            "sd_excluded_window_bps": sd_ex * 1e4,
            "excluded_share_of_day_variance": (sd_ex / sd_day) ** 2,
            "corr_held_vs_day": float(np.corrcoef(e["r_held"].to_numpy(), e["r_day"].to_numpy())[0, 1]),
            "round_trip_cost_over_day_sd": COST_BPS[product] / (sd_day * 1e4),
            "round_trip_cost_pct_per_year": COST_BPS[product] * 252 / 100,
            "median_price": price,
            "notional_per_contract": notional,
            "annual_vol": vol_ann,
            "one_contract_vol_on_account": notional * vol_ann / ACCOUNT,
            "contracts_at_vol_ceiling": VOL_CEILING * ACCOUNT / (notional * vol_ann),
        }
    out["daily_returns"] = {str(s): float(r) for s, r in d.select("session", "r_day").iter_rows()}
    return out


def correlation(res: dict) -> dict:
    a, b = res.get("INDEX", {}).get("daily_returns"), res.get("MGC", {}).get("daily_returns")
    if not a or not b:
        return {}
    common = sorted(set(a) & set(b))
    x = np.array([a[s] for s in common]); y = np.array([b[s] for s in common])
    post = np.array([s >= "2021-01-01" for s in common])
    return {"sessions": len(common), "full": float(np.corrcoef(x, y)[0, 1]),
            "post_2021": float(np.corrcoef(x[post], y[post])[0, 1]), "post_n": int(post.sum())}


def render(res: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# W-series feasibility — daily horizons through chained session holds")
    a("")
    a("Generated by `python -m futuresres.reporting.w_series_feasibility`. **A measurement: no trial, "
      "no strategy return** (dispersions only). `decisions.md` §72.")
    a("")
    a("## 1. What the chain gives up, and what it costs")
    a("")
    a("| product | era | sessions | day SD (bps) | excluded 16:55→reopen SD | share of day variance | corr(held, day) | round trip / day SD | round trips, %/yr |")
    a("|---|---|---|---|---|---|---|---|---|")
    for p in ("INDEX", "MGC"):
        r = res.get(p)
        if not r:
            continue
        for era, x in r["eras"].items():
            a(f"| {p} | {era} | {x['sessions']:,} | {x['sd_day_bps']:.1f} | {x['sd_excluded_window_bps']:.1f} | "
              f"{x['excluded_share_of_day_variance']:.1%} | {x['corr_held_vs_day']:.3f} | "
              f"{x['round_trip_cost_over_day_sd']:.2%} | {x['round_trip_cost_pct_per_year']:.2f}% |")
    a("")
    a("## 2. Contract granularity against a $50,000 account")
    a("")
    a("| product | era | median price | notional / contract | annual vol | one contract's vol on the account | contracts at the 12.4% ceiling |")
    a("|---|---|---|---|---|---|---|")
    for p in ("INDEX", "MGC"):
        r = res.get(p)
        if not r:
            continue
        for era, x in r["eras"].items():
            a(f"| {p} | {era} | {x['median_price']:,.0f} | ${x['notional_per_contract']:,.0f} | "
              f"{x['annual_vol']:.1%} | **{x['one_contract_vol_on_account']:.1%}** | "
              f"{x['contracts_at_vol_ceiling']:.2f} |")
    a("")
    a("## 3. The multiple-testing bar a DAILY strategy faces")
    a("")
    from futuresres.reporting.s_series_s2 import expected_max_sharpe, trial_state
    n0, var = trial_state()
    a(f"SR\\* is reported as one per-observation number (0.1368 at N = {n0}), built from the "
      f"variance of trial Sharpes that are mostly PER-TRADE intraday figures. Applied to a DAILY "
      f"observation that is {0.1368 * math.sqrt(252):.2f} annualised. The unit-consistent version "
      f"takes the null variance of a daily Sharpe estimate at the strategy's own sample size, "
      f"1/T, with N unchanged:")
    a("")
    a("| N | sample | T (sessions) | SR\\* per day | **SR\\* annualised** |")
    a("|---|---|---|---|---|")
    for n in (n0, n0 + 30):
        for label, t in (("post-2021 (decisive)", 1320), ("full", 2780)):
            sr = expected_max_sharpe(n, 1.0 / t)
            a(f"| {n} | {label} | {t:,} | {sr:.4f} | **{sr * math.sqrt(252):.2f}** |")
    a("")
    a("Which convention applies is a decision, not a computation (`decisions.md` §72).")
    a("")
    c = res.get("correlation") or {}
    if c:
        a("## 4. Daily-return correlation, index vs MGC")
        a("")
        a(f"Full sample {c['full']:+.3f} over {c['sessions']:,} common sessions; post-2021 "
          f"{c['post_2021']:+.3f} over {c['post_n']:,}.")
        a("")
    return "\n".join(w)


def log_measurements(res: dict) -> None:
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "measurements.jsonl")
    for p in ("INDEX", "MGC"):
        r = res[p]
        post = r["eras"].get("2021-2026", {})
        rec = log.append(Trial(
            trial_id=log.next_id("m"), hypothesis_id="W-series", symbol=p,
            date_range=("2010-06-06", "2026-08-27"), status="completed",
            params={"kind": "daily_horizon_feasibility",
                    "post_2021": {k: v for k, v in post.items()},
                    "correlation": res.get("correlation")},
            note=("kind=measurement; NOT a trial and NOT counted in N. W-series feasibility: "
                  "dispersion of the excluded 16:55->reopen window, round-trip cost against daily "
                  "SD, contract granularity on a $50k account, cross-instrument correlation. No "
                  "strategy return computed. decisions.md 72."),
        ))
        print(f"logged {rec['trial_id']} ({p})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.w_series_feasibility")
    ap.add_argument("--product", choices=list(SERIES))
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args(argv)
    res: dict = json.loads(RESULT_JSON.read_text()) if RESULT_JSON.exists() else {}
    if args.product:
        res[args.product] = json.loads(json.dumps(run(args.product)))
    if res.get("INDEX", {}).get("daily_returns") and res.get("MGC", {}).get("daily_returns"):
        res["correlation"] = correlation(res)
    # The daily return series exist only to compute the correlation. Once it is computed they are
    # dropped: a full series derived from licensed vendor data does not belong in a committed report.
    if res.get("correlation"):
        for p in ("INDEX", "MGC"):
            res.get(p, {}).pop("daily_returns", None)
    RESULT_JSON.write_text(json.dumps(res, indent=1) + "\n")
    REPORT_MD.write_text(render(res))
    print(f"wrote {RESULT_JSON.name}, {REPORT_MD.name}")
    if args.log:
        log_measurements(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
