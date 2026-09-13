"""Q-series S1 measurements on NQ. NO STRATEGY IS RUN AND NO FORWARD MEAN IS REPORTED.

Three things are measured, all properties of the series or of the CONDITIONS, never of a
trade's outcome:

1. COVERAGE. How many sessions carry each window the Q candidates need, per year - because
   the drafts quote "six years" and the F-series used the 2010-2026 NQ lineage, and the answer
   decides n for every entry.

2. THE Q01/Q02 CONDITIONERS. Q01 fires on the bottom tercile of last-30m RTH price change per
   unit volume; Q02 fades the last-30m move. Both are built from the same 15:30-16:00 price
   change, so their correlation is measured directly - it costs no trial because it reads no
   forward return. F02's own conditioner (15:00-16:00 return below -1 sigma) is included
   because Q01 turned out to re-register F02.

3. A BETTER IMBALANCE PROXY, available from OHLCV on disk. Price change per unit volume is an
   ILLIQUIDITY measure (P03's Amihud construction, signed), not an order-imbalance measure:
   dividing by volume ranks a heavy-volume selloff - the largest imbalance - as SMALLER than a
   thin one. Bulk volume classification (Easley, Lopez de Prado & O'Hara 2012) signs each bar's
   volume by its standardised return, so imbalance scales WITH volume instead. Reported as an
   order-flow imbalance RATIO in [-1, 1], which is dimensionless and survives volume growth.

4. UNCONDITIONAL WINDOW VOLATILITY, for the S2 bars. Standard deviations only; no mean is
   printed or stored, so nothing here can be read as an effect.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl
from scipy.stats import norm, spearmanr

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
SERIES: Final[Path] = ROOT / "data" / "continuous" / "NQ.parquet"
OUT: Final[Path] = ROOT / "reports" / "q_series_s1.json"

TERCILE_LOOKBACK: Final[int] = 60     # sessions, causal - the P03 convention
F02_K: Final[float] = 1.0             # F02's middle k


def minute_of_day() -> pl.Expr:
    # Cast BEFORE the arithmetic: dt.hour() is Int8 and wraps (decisions.md §54).
    return (pl.col("et").dt.hour().cast(pl.Int32) * 60
            + pl.col("et").dt.minute().cast(pl.Int32))


def last_close(lo: int, hi: int, name: str) -> pl.Expr:
    """Close of the last bar whose minute-of-day lies in [lo, hi)."""
    return pl.col("close").filter((pl.col("mod") >= lo) & (pl.col("mod") < hi)).last().alias(name)


def first_close(lo: int, hi: int, name: str) -> pl.Expr:
    """Close of the FIRST bar in [lo, hi). The session open is the first bar after 18:00, and an
    earlier version took the LAST bar before midnight, silently dropping six hours from the
    Q05 and Q06 windows."""
    return pl.col("close").filter((pl.col("mod") >= lo) & (pl.col("mod") < hi)).first().alias(name)


def main() -> int:
    base = (pl.scan_parquet(SERIES).select("ts_event", "close", "volume", "session")
            .with_columns(pl.col("ts_event").dt.convert_time_zone("America/New_York").alias("et"))
            .with_columns(minute_of_day().alias("mod")))

    # ---- per-session endpoints --------------------------------------------------------------
    ends = (base.group_by("session").agg(
        first_close(1080, 1440, "ovn_open"),    # the first bar after the 18:00 ET reopen
        last_close(0, 105, "q01_start"),        # 01:45 ET
        last_close(150, 195, "q01_end"),        # 03:15 ET
        last_close(0, 570, "pre_rth"),          # 09:30 ET reference
        last_close(540, 840, "rth_1400"),       # 14:00 ET
        last_close(840, 900, "c1500"),          # 15:00 ET reference (last bar before 15:00)
        last_close(870, 930, "c1530"),          # 15:30 ET reference
        last_close(930, 960, "c1600"),          # 16:00 ET close
        last_close(960, 975, "c1614"),          # 16:14 ET (pre-2021 halt at 16:15)
        last_close(975, 1020, "c1659"),         # 16:59 ET
        pl.col("close").filter((pl.col("mod") >= 975) & (pl.col("mod") < 990)).len()
            .alias("bars_1615_1630"),
        pl.col("volume").filter((pl.col("mod") >= 930) & (pl.col("mod") < 960)).sum()
            .alias("v_last30"),
        pl.col("close").filter((pl.col("mod") >= 930) & (pl.col("mod") < 960)).len()
            .alias("bars_last30"),
    ).sort("session").collect())

    # ---- BVC over 15:30-16:00, with sigma from that session's own 09:30-15:30 bars -------------
    rth = (base.filter((pl.col("mod") >= 570) & (pl.col("mod") < 960))
           .select("session", "mod", "close", "volume").sort("session", "mod").collect())
    sess = rth["session"].to_numpy()
    close = rth["close"].to_numpy()
    vol = rth["volume"].to_numpy().astype(float)
    mod = rth["mod"].to_numpy()
    r = np.full(close.size, np.nan)
    same = np.r_[False, sess[1:] == sess[:-1]]
    r[1:] = np.log(close[1:] / close[:-1])
    r[~same] = np.nan

    uniq, starts = np.unique(sess, return_index=True)
    bounds = np.r_[starts, sess.size]
    oir = {}
    for s, a, b in zip(uniq, bounds[:-1], bounds[1:]):
        rr, vv, mm = r[a:b], vol[a:b], mod[a:b]
        early = np.isfinite(rr) & (mm < 930)
        late = np.isfinite(rr) & (mm >= 930)
        if early.sum() < 60 or late.sum() < 20:
            continue
        sd = float(np.std(rr[early]))
        if sd <= 0:
            continue
        buy_share = norm.cdf(rr[late] / sd)
        signed = float(np.sum(vv[late] * (2 * buy_share - 1)))
        total = float(np.sum(vv[late]))
        if total > 0:
            oir[s] = signed / total

    # JOIN, NOT map_elements. The dict was keyed by numpy datetime64 while map_elements hands
    # over python dates, so every lookup missed and the ratio came back null for every session -
    # which turned every correlation below into NaN rather than into an error.
    oir_frame = pl.DataFrame({"session": pl.Series(np.array(list(oir.keys()))).cast(pl.Date),
                              "oir": list(oir.values())})
    df = ends.join(oir_frame, on="session", how="left")
    bp = lambda a, b: (pl.col(b) / pl.col(a)).log() * 1e4   # noqa: E731
    df = df.with_columns(
        bp("c1530", "c1600").alias("last30_bps"),
        bp("c1500", "c1600").alias("f02_imb_bps"),
        bp("q01_start", "q01_end").alias("q01_win"),
        bp("c1600", "c1659").alias("q02_post_hour"),
        bp("c1600", "c1614").alias("q02_pre_halt"),
        bp("pre_rth", "rth_1400").alias("q03_0930_1400"),
        # to 16:00, not 16:59: bars after 16:15 do not exist before 2016, so a 16:59 endpoint
        # would silently drop the first six years from a calendar hypothesis
        bp("ovn_open", "c1600").alias("q05_session"),
        bp("ovn_open", "pre_rth").alias("q06_overnight"),
        pl.col("session").dt.year().alias("yr"),
        pl.col("session").dt.weekday().alias("wd"),
    ).with_columns(
        (pl.col("last30_bps") / pl.col("v_last30")).alias("q01_proxy"),
    )

    # ---- coverage -----------------------------------------------------------------------------
    cov = (df.group_by("yr").agg(
        pl.len().alias("sessions"),
        pl.col("last30_bps").is_not_null().sum().alias("eod_window"),
        pl.col("q01_win").is_not_null().sum().alias("q01_window"),
        (pl.col("bars_1615_1630") > 0).sum().alias("trades_1615_1630"),
        pl.col("q02_post_hour").is_not_null().sum().alias("post_hour"),
    ).sort("yr"))
    with pl.Config(tbl_rows=40):
        print("COVERAGE BY YEAR (NQ)")
        print(cov)

    # ---- the conditioners ----------------------------------------------------------------------
    d = df.to_pandas().set_index("session").sort_index()
    # Q01 fires on the night AFTER a bottom-tercile end-of-day session: shift to the next session
    # ROLL OVER VALID SESSIONS, not calendar rows. A 60-row window demanding 60 values goes
    # undefined whenever one holiday or early close falls inside it, which left 64 sessions.
    proxy = d["q01_proxy"].replace([np.inf, -np.inf], np.nan).dropna()
    tercile = proxy.rolling(TERCILE_LOOKBACK, min_periods=TERCILE_LOOKBACK).quantile(1 / 3).shift(1)
    q01_fires = (proxy < tercile).reindex(d.index, fill_value=False)
    tercile = tercile.reindex(d.index)
    q02_long = d["last30_bps"] < 0
    f02_raw = d["f02_imb_bps"].dropna()
    f02_sigma = f02_raw.rolling(TERCILE_LOOKBACK, min_periods=TERCILE_LOOKBACK).std().shift(1)
    f02_fires = (f02_raw < -F02_K * f02_sigma).reindex(d.index, fill_value=False)
    f02_sigma = f02_sigma.reindex(d.index)
    threshold_negative = float((tercile.dropna() < 0).mean())

    both = d[["q01_proxy", "last30_bps", "oir", "f02_imb_bps"]].dropna()
    post = both[both.index >= np.datetime64("2021-01-01")]

    def rho(frame, a, b):
        return float(spearmanr(frame[a], frame[b]).statistic)

    valid = tercile.notna() & d["last30_bps"].notna() & d["v_last30"].gt(0)
    fires, longs = q01_fires[valid], q02_long[valid]
    phi = float(np.corrcoef(fires.astype(float), longs.astype(float))[0, 1])
    p_long_given_fire = float(longs[fires].mean())
    f_valid = valid & f02_sigma.notna()
    overlap_f02 = float((q01_fires[f_valid] & f02_fires[f_valid]).sum()
                        / max(f02_fires[f_valid].sum(), 1))

    print("\nCONDITIONER CORRELATIONS (Spearman, per session)")
    rows = [("Q01 proxy (dp/V)", "Q02 signal (dp)", "q01_proxy", "last30_bps"),
            ("Q01 proxy (dp/V)", "BVC imbalance ratio", "q01_proxy", "oir"),
            ("Q02 signal (dp)", "BVC imbalance ratio", "last30_bps", "oir"),
            ("Q02 signal (dp)", "F02 conditioner", "last30_bps", "f02_imb_bps")]
    corr = {}
    for la, lb, a, b in rows:
        full, late = rho(both, a, b), rho(post, a, b)
        corr[f"{la} vs {lb}"] = {"full": full, "post_2021": late}
        print(f"  {la:>18} vs {lb:<22} full {full:+.3f}   post-2021 {late:+.3f}")
    print(f"\n  sessions with a defined Q01 tercile: {int(valid.sum()):,}")
    print(f"  Q01 fires on {fires.mean():.1%} of them")
    print(f"  phi(Q01 fires, Q02 long) = {phi:+.3f}")
    print(f"  P(Q02 is LONG | Q01 fires) = {p_long_given_fire:.1%}")
    print(f"  share of sessions whose Q01 threshold is itself NEGATIVE: {threshold_negative:.1%}"
          f"  (where it is, Q01 firing IMPLIES dp < 0 and so implies Q02 long - an identity)")
    print(f"  share of F02 (k=1) firings that Q01 also fires on: {overlap_f02:.1%}")

    # Is the Q01 proxy scale-invariant? Its median magnitude by year says.
    scale = (df.filter(pl.col("q01_proxy").is_not_null())
             .group_by("yr").agg(pl.col("q01_proxy").abs().median().alias("median_abs_dp_per_V"),
                                 pl.col("v_last30").median().alias("median_vol_last30"),
                                 pl.col("oir").abs().median().alias("median_abs_oir"))
             .sort("yr"))
    with pl.Config(tbl_rows=40):
        print("\nSCALE: |dp/V| moves with volume growth; the BVC ratio should not")
        print(scale)

    # ---- unconditional window volatility (SD ONLY - no mean is computed for output) -------------
    print("\nUNCONDITIONAL WINDOW SD (bps), no condition applied, no mean reported")
    sds = {}
    for col, label in (("q01_win", "Q01 01:45-03:15"),
                       ("q02_post_hour", "Q02 16:00-16:59"),
                       ("q02_pre_halt", "Q02 16:00-16:14"),
                       ("q03_0930_1400", "Q03 09:30-14:00"),
                       ("q05_session", "Q05 18:00 to 16:00"),
                       ("q06_overnight", "Q06 overnight to 09:30")):
        x = d[col].dropna()
        pre, late = x[x.index < np.datetime64("2021-01-01")], x[x.index >= np.datetime64("2021-01-01")]
        entry = {"n": int(x.size), "sd": float(x.std()),
                 "n_pre": int(pre.size), "sd_pre": float(pre.std()) if pre.size > 2 else None,
                 "n_post": int(late.size), "sd_post": float(late.std()) if late.size > 2 else None}
        if col == "q06_overnight":
            mon = x[d.loc[x.index, "wd"] == 1]
            entry.update({"n_monday": int(mon.size), "sd_monday": float(mon.std())})
        sds[label] = entry
        extra = f"  Mondays n {entry['n_monday']:,} sd {entry['sd_monday']:.1f}" if "n_monday" in entry else ""
        print(f"  {label:>28}: n {entry['n']:>5,}  sd {entry['sd']:6.1f}   "
              f"pre-2021 n {entry['n_pre']:>5,}   post n {entry['n_post']:>5,}{extra}")

    # ---- S2 inputs: COUNTS and MAGNITUDES OF CONDITIONERS only, never an outcome ------------
    import pandas as pd

    post_idx = d.index >= np.datetime64("2021-01-01")
    # Q01 trades the NIGHT AFTER an end-of-day firing, so a firing counts only if the next
    # session's 01:45-03:15 window exists.
    nxt = d["q01_win"].shift(-1).notna()
    fired = q01_fires & valid & nxt
    unfired = (~q01_fires) & valid & nxt
    q01_counts = {"fires_pre": int((fired & ~post_idx).sum()),
                  "fires_post": int((fired & post_idx).sum()),
                  "nonfires_pre": int((unfired & ~post_idx).sum()),
                  "nonfires_post": int((unfired & post_idx).sum())}
    l30 = d["last30_bps"].dropna()
    med_abs_last30 = {"full": float(l30.abs().median()),
                      "post_2021": float(l30[l30.index >= np.datetime64("2021-01-01")].abs().median())}
    q5 = d["q05_session"].dropna()
    q5_post = q5.index >= np.datetime64("2021-01-01")
    months = {"pre": int(pd.DatetimeIndex(q5.index[~q5_post]).to_period("M").nunique()),
              "post": int(pd.DatetimeIndex(q5.index[q5_post]).to_period("M").nunique()),
              "sessions_pre": int((~q5_post).sum()), "sessions_post": int(q5_post.sum())}
    q6 = d["q06_overnight"].dropna()
    q6_post = q6.index >= np.datetime64("2021-01-01")
    is_mon = (d.loc[q6.index, "wd"] == 1).to_numpy()
    mondays = {"mon_pre": int((is_mon & ~q6_post).sum()), "mon_post": int((is_mon & q6_post).sum()),
               "other_pre": int((~is_mon & ~q6_post).sum()),
               "other_post": int((~is_mon & q6_post).sum()),
               "sd_post": float(q6[q6_post].std())}
    print(f"\nS2 INPUTS  Q01 {q01_counts}")
    print(f"           median |last-30m move| bps {med_abs_last30}")
    print(f"           Q05 {months}")
    print(f"           Q06 {mondays}")

    OUT.write_text(json.dumps({
        "q01_counts": q01_counts,
        "median_abs_last30_bps": med_abs_last30,
        "q05_months": months,
        "q06_mondays": mondays,
        "coverage": cov.to_dicts(),
        "conditioner_correlation": corr,
        "q01_sessions_defined": int(valid.sum()),
        "q01_fire_rate": float(fires.mean()),
        "phi_q01_fires_q02_long": phi,
        "p_q02_long_given_q01_fires": p_long_given_fire,
        "q01_threshold_negative_share": threshold_negative,
        "share_f02_firings_also_q01": overlap_f02,
        "scale_by_year": scale.to_dicts(),
        "window_sd": sds,
    }, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
