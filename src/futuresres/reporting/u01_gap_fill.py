"""U01 — large opening gap non-fill. Firing rate and the fill-rate curve, BEFORE registration.

A MEASUREMENT: no trial spent; one record per product to `measurements.jsonl` with `--log`.

    python -m futuresres.reporting.u01_gap_fill --product INDEX
    python -m futuresres.reporting.u01_gap_fill --product MGC
    python -m futuresres.reporting.u01_gap_fill --log

INDEX is the spliced NQ -> MNQ series (2010-2026). Gaps are price ratios on one price grid, so the
splice is valid for them (`reports/splice.md` verifies the convention); MNQ alone starts in 2019
and is reported as the post-2019 subset of the same rows, not as a second sample.

THE CONDITION, FIXED BEFORE ANY COUNT. "The open of a new trading day, or a new week, gaps 0.4% or
more from the prior close", read in this programme's session convention (CME trading day,
18:00-17:00 ET):

  daily   the 18:00 ET reopen after the 17:00-18:00 maintenance break, against the prior
          session's last close; Monday-Thursday sessions.
  weekly  the Sunday 18:00 ET reopen, against Friday's last close.

The 09:30 RTH open against the 16:00 close is NOT used: index futures trade through it, so it is a
move during continuous trading, not a gap in the futures price. Choosing between the two readings
after seeing which one fires more, or fills less, would be selecting the condition by its result.

A session is counted only if its first bar and the prior session's last bar are the same contract
(a roll is not a gap), the break is a normal one (< 6 hours daily, < 3 days weekly), the session
first traded within 5 minutes of the 18:00 ET reopen, and the PRIOR session traded within 5
minutes of its own scheduled close (MAX_FIRST_PRINT_MIN, MAX_STALE_CLOSE_MIN - read their
comments for when and why each was fixed). Others are excluded and the exclusions are counted,
not dropped.

FILL. Same session: an up-gap fills if any later price in the session trades at or below the prior
close (session low), a down-gap if any trades at or above it (session high).

THE RANDOM-WALK BENCHMARK. Fill must fall with gap size mechanically: a larger gap needs a larger
move to close. For a driftless Brownian path with volatility sigma over the session, the chance of
touching a level at distance g is 2 * (1 - Phi(g / sigma)) - the reflection principle. Two sigmas,
both reported:

  own     the session's own realised volatility after the open (1-minute returns, the gap
          excluded). Conditions on how much the session actually moved, so it absorbs the
          volatility-regime confound the brief names.
  ex ante the median realised volatility of the previous 20 sessions. What a trader could know at
          the open.

Realised volatility on 1-minute bars carries microstructure noise and so slightly OVERSTATES sigma
(and the predicted fill); continuous-path touching is approximated by 1-minute highs and lows.
Both biases are small at session scale and are stated rather than corrected.

NO THRESHOLD IS SELECTED FROM THE CURVE. The curve is reported over a fixed grid of gap sizes
chosen before measuring. Picking the size that performs best would be a search over thresholds and
would have to be counted as one.
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
from scipy.stats import norm

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
RESULT_JSON: Final[Path] = ROOT / "reports" / "u01_gap_fill.json"
REPORT_MD: Final[Path] = ROOT / "reports" / "u01_gap_fill.md"

SERIES: Final[dict[str, str]] = {"INDEX": "NQ_MNQ_spliced", "MGC": "MGC"}
THRESHOLD: Final[float] = 0.004                 # the registered condition, 0.4%
#: fixed before measuring; edges in percent
BIN_EDGES_PCT: Final[tuple[float, ...]] = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 100.0)
#: smallest sample at which a detection floor resolved (`level_rates.SMALLEST_RESOLVING`). A
#: session-length hold has no resolved floor at all; the 180-minute proxy is the most generous
#: one that exists and is used as the yardstick.
FLOOR_180M: Final[dict[str, int]] = {"INDEX": 5_884, "MGC": 2_862}
#: An open is an OPEN only if the session traded at the reopen. MGC in 2010-2015 often first
#: printed 15 minutes to hours after 18:00 ET (87% of 2010 sessions later than 15 minutes); a
#: "gap" to a print hours later measures price discovery during untraded time, not the break.
#: Fixed at 5 minutes on 2026-10-02 after seeing that delay distribution and BEFORE any fill
#: rate or count of large gaps was computed.
MAX_FIRST_PRINT_MIN: Final[int] = 5
#: The PRIOR close must be a close: the prior session must have traded within 5 minutes of its
#: own scheduled close. Index sessions in 2010-2012 often hold ~110 bars ending around 20:30 ET,
#: and MGC sessions before ~2016 are thin; a "gap" to a last print hours before the close
#: includes untraded drift. Added 2026-10-02 AFTER a first count had been seen - diagnosed from a
#: 21-hour "break" anomaly, not from the fill rates - and it can only REMOVE sessions, so it
#: cannot move the event count toward the floor.
MAX_STALE_CLOSE_MIN: Final[int] = 5


def sessions(product: str) -> pl.DataFrame:
    """Per-(session, contract) aggregates, computed lazily so the 4.7M-row splice never
    materialises."""
    lf = pl.scan_parquet(CONTINUOUS / f"{SERIES[product]}.parquet").select(
        "ts_event", "contract", "session", "open", "high", "low", "close")
    keys = ["session", "contract"]
    r = (pl.col("close").log() - pl.col("close").log().shift(1).over(keys))
    agg = (lf.sort("ts_event")
             .with_columns(r.alias("r"))
             .group_by(keys)
             .agg(pl.col("ts_event").first().alias("t0"),
                  pl.col("ts_event").last().alias("t1"),
                  pl.col("open").first().alias("open0"),
                  pl.col("close").last().alias("close1"),
                  pl.col("high").max().alias("hi"),
                  pl.col("low").min().alias("lo"),
                  (pl.col("r") ** 2).sum().alias("rv"),
                  pl.len().alias("bars"))
             .sort("t0")
             .collect(engine="streaming"))
    return agg


def events(product: str) -> pl.DataFrame:
    s = sessions(product)
    et = pl.col("t0").dt.convert_time_zone("America/New_York")
    s = s.with_columns(
        pl.col("close1").shift(1).alias("prior_close"),
        pl.col("contract").shift(1).alias("prior_contract"),
        (pl.col("t0") - pl.col("t1").shift(1)).dt.total_minutes().alias("break_min"),
        (et.dt.weekday() == 7).alias("sunday_open"),          # polars: Monday=1 .. Sunday=7
        pl.col("rv").sqrt().alias("sigma_own"),
        pl.col("rv").sqrt().shift(1).rolling_median(window_size=20).alias("sigma_exante"),
        pl.col("session").dt.year().alias("year"),
    ).with_columns(
        pl.when(pl.col("sunday_open")).then(pl.lit("weekly")).otherwise(pl.lit("daily"))
          .alias("kind"),
        (pl.col("open0") / pl.col("prior_close")).log().alias("gap"),
    )
    # minutes after the 18:00 ET reopen at which the session first traded
    mod = et.dt.hour().cast(pl.Int32) * 60 + et.dt.minute().cast(pl.Int32)
    s = s.with_columns(((mod - 18 * 60) % 1440).alias("first_print_offset"))
    # how far before its OWN scheduled close the session last traded. The schedule moved
    # (index bars after 16:15 ET do not exist before 2015, decisions.md 59; MGC closed 17:15 in
    # 2010), so the close is the modal last-print minute of that product-year, not a constant.
    et1 = pl.col("t1").dt.convert_time_zone("America/New_York")
    s = s.with_columns((et1.dt.hour().cast(pl.Int32) * 60 + et1.dt.minute().cast(pl.Int32))
                       .alias("last_mod"))
    s = s.with_columns(pl.col("last_mod").mode().first().over("year").alias("close_mod"))
    s = s.with_columns(((pl.col("close_mod") - pl.col("last_mod")) % 1440 <= MAX_STALE_CLOSE_MIN)
                       .alias("traded_at_close"))
    s = s.with_columns(pl.col("traded_at_close").shift(1).alias("prior_traded_at_close"))
    ok_contract = pl.col("contract") == pl.col("prior_contract")
    ok_print = pl.col("first_print_offset") <= MAX_FIRST_PRINT_MIN
    ok_close = pl.col("prior_traded_at_close").fill_null(False)
    ok_break = (pl.when(pl.col("kind") == "daily").then(pl.col("break_min") < 6 * 60)
                  .otherwise(pl.col("break_min") < 3 * 24 * 60))
    s = s.with_columns((ok_contract & ok_break & ok_print & ok_close
                        & pl.col("prior_close").is_not_null()).alias("valid"))
    filled = (pl.when(pl.col("gap") > 0).then(pl.col("lo") <= pl.col("prior_close"))
                .otherwise(pl.col("hi") >= pl.col("prior_close")))
    return s.with_columns(filled.alias("filled"))


def rw_fill(g: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return 2.0 * (1.0 - norm.cdf(np.abs(g) / sigma))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def run(product: str) -> dict:
    ev = events(product)
    total = ev.height
    valid = ev.filter(pl.col("valid"))
    late = ev.filter(pl.col("first_print_offset") > MAX_FIRST_PRINT_MIN).height
    stale = ev.filter(~pl.col("prior_traded_at_close").fill_null(False)).height
    excluded = {"sessions": total, "valid": valid.height,
                "excluded_total": total - valid.height,
                "excluded_late_first_print": late,
                "excluded_stale_prior_close": stale,
                "valid_by_year": {int(y): int(n) for y, n in
                                  valid.group_by("year").len().sort("year").iter_rows()}}
    out: dict = {"product": product, "series": SERIES[product], "sessions": excluded}

    # ── firing rate at the registered 0.4% ────────────────────────────────────
    fire = {}
    for kind in ("daily", "weekly"):
        k = valid.filter(pl.col("kind") == kind)
        hit = k.filter(pl.col("gap").abs() >= THRESHOLD)
        yrs = hit["year"].to_numpy()
        fire[kind] = {
            "opens": k.height, "gaps_ge_0.4pct": hit.height,
            "share": hit.height / max(k.height, 1),
            "post_2021": int((yrs >= 2021).sum()),
            "post_2019_mnq_era": int((yrs >= 2019).sum()),
            "up": int((hit["gap"] > 0).sum()), "down": int((hit["gap"] < 0).sum()),
            "fill_rate": float(hit["filled"].mean()) if hit.height else float("nan"),
            "fill_ci": wilson(int(hit["filled"].sum()), hit.height),
            "clean_pool_sessions": k.height - hit.height,
        }
    out["firing"] = fire
    out["floor_180m"] = FLOOR_180M[product]

    # ── the curve ──────────────────────────────────────────────────────────────
    curve = {}
    edges = np.array(BIN_EDGES_PCT) / 100.0
    for kind in ("daily", "weekly"):
        k = valid.filter(pl.col("kind") == kind)
        g = np.abs(k["gap"].to_numpy())
        f = k["filled"].to_numpy().astype(bool)
        so = k["sigma_own"].to_numpy()
        se = k["sigma_exante"].to_numpy()
        rows = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            m = (g >= lo) & (g < hi)
            n = int(m.sum())
            if n == 0:
                rows.append({"lo_pct": lo * 100, "hi_pct": hi * 100, "n": 0})
                continue
            p_own = rw_fill(g[m], so[m])
            p_ex = rw_fill(g[m], se[m])
            ok_ex = np.isfinite(p_ex)
            obs = float(f[m].mean())
            # per-event Bernoulli variance under the prediction: the SE of (obs - pred)
            se_own = float(np.sqrt(np.nansum(p_own * (1 - p_own))) / n)
            rows.append({
                "lo_pct": lo * 100, "hi_pct": hi * 100, "n": n,
                "fill_obs": obs, "fill_ci": wilson(int(f[m].sum()), n),
                "fill_rw_own": float(np.nanmean(p_own)),
                "fill_rw_exante": float(np.nanmean(p_ex[ok_ex])) if ok_ex.any() else float("nan"),
                "obs_minus_own": obs - float(np.nanmean(p_own)),
                "z_vs_own": (obs - float(np.nanmean(p_own))) / se_own if se_own > 0 else float("nan"),
                "median_gap_over_sigma_own": float(np.nanmedian(g[m] / so[m])),
            })
        curve[kind] = rows
    out["curve"] = curve

    # ── calibration over all valid opens, the one-number summary of "tracks or not" ──
    cal = {}
    for kind in ("daily", "weekly"):
        k = valid.filter(pl.col("kind") == kind)
        g = np.abs(k["gap"].to_numpy())
        keep = g >= edges[0]
        f = k["filled"].to_numpy().astype(bool)[keep]
        p = rw_fill(g[keep], k["sigma_own"].to_numpy()[keep])
        ok = np.isfinite(p)
        f, p = f[ok], p[ok]
        cal[kind] = {"n": int(f.size), "obs": float(f.mean()), "rw_own": float(p.mean()),
                     "z": float((f.mean() - p.mean()) / (np.sqrt((p * (1 - p)).sum()) / f.size))}
    out["calibration_vs_rw_own"] = cal
    return out


def render(res: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# U01 — opening gaps: firing rate and the fill curve, before registration")
    a("")
    a("Generated by `python -m futuresres.reporting.u01_gap_fill`. A measurement, **no trial "
      "spent**. Condition and definitions are fixed in the module docstring; the summary is "
      "here, the account is `decisions.md` §67.")
    a("")
    a("## Firing rate at the registered 0.4%")
    a("")
    a("| product | open | valid opens | gaps ≥ 0.4% | share | post-2021 | up / down | same-session fill | floor (180m proxy) |")
    a("|---|---|---|---|---|---|---|---|---|")
    for p, r in res.items():
        for kind in ("daily", "weekly"):
            x = r["firing"][kind]
            a(f"| {p} | {kind} | {x['opens']:,} | **{x['gaps_ge_0.4pct']:,}** | {x['share']:.2%} | "
              f"{x['post_2021']:,} | {x['up']} / {x['down']} | "
              f"{x['fill_rate']:.1%} [{x['fill_ci'][0]:.1%}, {x['fill_ci'][1]:.1%}] | "
              f"{r['floor_180m']:,} |")
    a("")
    for p, r in res.items():
        s = r["sessions"]
        a(f"{p}: {s['sessions']:,} sessions, **{s['valid']:,} with a valid open**; "
          f"{s['excluded_total']:,} excluded — {s['excluded_stale_prior_close']:,} whose prior "
          f"session did not trade within 5 minutes of its scheduled close, "
          f"{s['excluded_late_first_print']:,} that first traded more than 5 minutes after the "
          f"reopen (overlapping), and the rest roll or abnormal break. Valid opens by year: "
          + ", ".join(f"{y} {n}" for y, n in s['valid_by_year'].items()) + ".")
    a("")
    a("## The fill curve against a driftless random walk")
    a("")
    a("Observed same-session fill against the reflection-principle prediction "
      "2·(1 − Φ(g/σ)), with σ the session's own realised volatility after the open (`own`) and "
      "the trailing 20-session median (`ex ante`). `z` is observed minus `own`, in units of the "
      "binomial SE the prediction implies.")
    a("")
    for p, r in res.items():
        for kind in ("daily", "weekly"):
            a(f"### {p}, {kind} opens")
            a("")
            a("| gap (%) | n | observed fill | 95% CI | RW, own σ | RW, ex-ante σ | obs − own | z | median g/σ |")
            a("|---|---|---|---|---|---|---|---|---|")
            for b in r["curve"][kind]:
                hi = "∞" if b["hi_pct"] >= 100 else f"{b['hi_pct']:g}"
                if b["n"] == 0:
                    a(f"| {b['lo_pct']:g}–{hi} | 0 | | | | | | | |")
                    continue
                a(f"| {b['lo_pct']:g}–{hi} | {b['n']:,} | {b['fill_obs']:.1%} | "
                  f"[{b['fill_ci'][0]:.1%}, {b['fill_ci'][1]:.1%}] | {b['fill_rw_own']:.1%} | "
                  f"{b['fill_rw_exante']:.1%} | {b['obs_minus_own']:+.1%} | {b['z_vs_own']:+.2f} | "
                  f"{b['median_gap_over_sigma_own']:.2f} |")
            c = r["calibration_vs_rw_own"][kind]
            a("")
            a(f"All {kind} opens with |gap| ≥ 0.05%: n = {c['n']:,}, observed {c['obs']:.1%} against "
              f"{c['rw_own']:.1%} predicted, z = {c['z']:+.2f}.")
            a("")
    a("## Reopen microstructure — a measured property, recorded in its own right")
    a("")
    a("At **daily** opens (18:00 ET after a one-hour break), small gaps fill more often than the "
      "driftless walk predicts. Not what U01 registered, and not pursued — but a property of the "
      "data, not discarded with the hypothesis (`decisions.md` §68).")
    a("")
    a("| product | open | gap (%) | n | observed | RW, own σ | excess | z |")
    a("|---|---|---|---|---|---|---|---|")
    for p, r in res.items():
        for kind in ("daily", "weekly"):
            for b in r["curve"][kind]:
                if b["n"] and b["hi_pct"] <= 0.3 + 1e-9:
                    a(f"| {p} | {kind} | {b['lo_pct']:g}–{b['hi_pct']:g} | {b['n']:,} | "
                      f"{b['fill_obs']:.1%} | {b['fill_rw_own']:.1%} | "
                      f"{b['obs_minus_own']:+.1%} | {b['z_vs_own']:+.2f} |")
    a("")
    a("Gaps of 5–30 bps: from about 6 ticks (MGC, 2010) to over 200 (the index today), small only "
      "relative to session volatility. The excess is a touch-probability difference, not a "
      "measured return, so tradeability is not established either way. Consistent with the "
      "reopen print reverting against thin liquidity after the break — an interpretation, not a "
      "test.")
    a("")
    return "\n".join(w)


def log_measurements(res: dict) -> None:
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "measurements.jsonl")
    for p, r in res.items():
        rec = log.append(Trial(
            trial_id=log.next_id("m"), hypothesis_id="U01", symbol=p,
            date_range=("2010-06-06", "2026-08-27"), status="completed",
            params={"kind": "firing_rate_and_fill_curve", "threshold": THRESHOLD,
                    "firing": {k: {kk: vv for kk, vv in v.items() if kk != "fill_ci"}
                               for k, v in r["firing"].items()},
                    "calibration_vs_rw_own": r["calibration_vs_rw_own"]},
            note=("kind=measurement; NOT a trial and NOT counted in N. U01 firing rate at 0.4% "
                  "(daily and weekly CME reopens) and the same-session fill curve against a "
                  "driftless random walk scaled by session volatility. decisions.md 67."),
        ))
        print(f"logged {rec['trial_id']} ({p})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.u01_gap_fill")
    ap.add_argument("--product", choices=list(SERIES))
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args(argv)
    res: dict = json.loads(RESULT_JSON.read_text()) if RESULT_JSON.exists() else {}
    if args.product:
        res[args.product] = json.loads(json.dumps(run(args.product)))
    RESULT_JSON.write_text(json.dumps(res, indent=1) + "\n")
    REPORT_MD.write_text(render(res))
    print(f"wrote {RESULT_JSON.name}, {REPORT_MD.name}")
    if args.log:
        log_measurements(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
