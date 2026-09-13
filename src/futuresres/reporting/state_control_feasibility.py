"""Can a P03-shaped state condition actually be controlled on real data? Matching only.

THIS LOOKS AT NO RETURNS. It measures whether a matched control can be BUILT for a thin-move
state on NQ — firing counts, cell occupancy, match rates, fallback rates — and stops there.
Nothing here spends a trial or tests a hypothesis: `state_control.verify_control` consumes
time-of-day, volatility quantile and year, and never a price change. The one number that
could be mistaken for a result, effective units, is a count.

WHY NQ RATHER THAN THE SPLICED SERIES. §54 recorded that |return| per contract is not scale
invariant across the 2019-05-31 splice: median 1m bar volume falls 83-140 to 26-39 when NQ
hands over to MNQ, so the ratio steps up ~3-5x at a contract change that has nothing to do
with liquidity. `NQ.parquet` is one contract lineage over 4,125 sessions from 2010, which
removes the discontinuity instead of modelling it.

THE STATE, FIXED A PRIORI. Every number below is chosen before running and recorded as a
PARAMETER, not a detail — §45's point about the firing rate being a design lever, not a free
one:

    bar                     5 minutes, RTH only (09:30-16:00 ET)
    illiquidity             |log return in bps| / bar volume        (Amihud, per bar)
    NORMALISATION LOOKBACK  60 sessions, same 30-minute bucket      <- the parameter
    threshold               trailing 90th percentile of that bucket's own illiquidity
    volatility quantile     session realised vol, 5 buckets, ranked on the same 60 sessions

The lookback is not free: it sets how much of the sample is warm-up (60 sessions lost), how
fast the threshold tracks a volume trend, and how much the state clusters. It is fixed here
so that it is a registered choice rather than something tuned after seeing a result.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

from futuresres.signals.state_control import (
    make_matched_control,
    session_clustering,
    trailing_vol_quantile,
    verify_control,
)

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
SERIES: Final[Path] = ROOT / "data" / "continuous" / "NQ.parquet"
OUT: Final[Path] = ROOT / "reports" / "state_control_feasibility.json"

BAR_MINUTES: Final[int] = 5
BUCKET_MINUTES: Final[int] = 30
LOOKBACK_SESSIONS: Final[int] = 60
N_VOL_QUANTILES: Final[int] = 5
THRESHOLD_PCT: Final[float] = 90.0


def load_bars() -> pl.DataFrame:
    """RTH 5-minute bars with volume, in ET, one contract lineage."""
    lf = (
        pl.scan_parquet(SERIES)
        .select("ts_event", "close", "volume", "session")
        .with_columns(pl.col("ts_event").dt.convert_time_zone("America/New_York").alias("et"))
    )
    # CAST BEFORE THE ARITHMETIC. `dt.hour()` is Int8, so `hour * 60` wraps silently -
    # 18:00 ET came out as 56 rather than 1080 and the RTH filter matched nothing. It
    # failed loudly downstream this time; a narrower window would have returned a wrong
    # number instead of an empty frame.
    lf = lf.with_columns(
        (pl.col("et").dt.hour().cast(pl.Int32) * 60
         + pl.col("et").dt.minute().cast(pl.Int32)).alias("mod")
    ).filter((pl.col("mod") >= 9 * 60 + 30) & (pl.col("mod") < 16 * 60))
    lf = lf.with_columns(
        ((pl.col("mod") - (9 * 60 + 30)) // BAR_MINUTES).alias("slot"),
        ((pl.col("mod") - (9 * 60 + 30)) // BUCKET_MINUTES).alias("tod"),
    )
    return (
        lf.group_by("session", "slot", "tod")
        .agg(pl.col("close").last().alias("close"), pl.col("volume").sum().alias("volume"))
        .sort("session", "slot")
        .collect()
    )


def build_state(df: pl.DataFrame) -> dict[str, np.ndarray]:
    """The a priori state, its nuisance covariates, and the session index."""
    sessions = df["session"].unique(maintain_order=True).to_numpy()
    sess_id = {s: i for i, s in enumerate(sessions)}
    sid = np.array([sess_id[s] for s in df["session"].to_numpy()])
    tod = df["tod"].to_numpy().astype(int)
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy().astype(float)

    ret_bps = np.zeros(close.size)
    same = np.concatenate([[False], sid[1:] == sid[:-1]])
    with np.errstate(divide="ignore", invalid="ignore"):
        ret_bps[1:] = np.abs(np.log(close[1:] / close[:-1])) * 1e4
    ret_bps[~same] = np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        illiq = np.where(volume > 0, ret_bps / volume, np.nan)

    # Trailing same-bucket threshold: previous LOOKBACK_SESSIONS only, never this one.
    n_sessions = sessions.size
    state = np.zeros(illiq.size, dtype=bool)
    for bucket in np.unique(tod):
        in_bucket = np.flatnonzero(tod == bucket)
        b_sid, b_val = sid[in_bucket], illiq[in_bucket]
        by_session: list[list[float]] = [[] for _ in range(n_sessions)]
        for s, v in zip(b_sid, b_val):
            if np.isfinite(v):
                by_session[s].append(float(v))
        window: list[float] = []
        counts: list[int] = []
        thresh = np.full(n_sessions, np.nan)
        for s in range(n_sessions):
            if len(counts) >= LOOKBACK_SESSIONS:
                drop = counts.pop(0)
                del window[:drop]
            if window:
                thresh[s] = float(np.percentile(window, THRESHOLD_PCT))
            window.extend(by_session[s])
            counts.append(len(by_session[s]))
        ok = np.isfinite(b_val) & np.isfinite(thresh[b_sid])
        state[in_bucket[ok]] = b_val[ok] > thresh[b_sid][ok]

    # Session realised volatility, ranked causally against the same lookback.
    sess_vol = np.full(n_sessions, np.nan)
    for s in range(n_sessions):
        r = ret_bps[(sid == s) & np.isfinite(ret_bps)]
        if r.size > 10:
            sess_vol[s] = float(np.std(r))
    vol_q = trailing_vol_quantile(sess_vol, LOOKBACK_SESSIONS, N_VOL_QUANTILES)[sid]

    year = sessions.astype("datetime64[Y]").astype(int)[sid] + 1970
    return {"state": state, "session": sid, "tod": tod, "vol_q": vol_q, "year": year,
            "n_sessions": n_sessions}


def main() -> int:
    if not SERIES.exists():
        print(f"missing {SERIES}", file=sys.stderr)
        return 1
    df = load_bars()
    w = build_state(df)
    state, sid = w["state"], w["session"]
    fired = np.unique(sid[state])
    n_sessions = int(w["n_sessions"])

    print(f"bars {state.size:,}   sessions {n_sessions:,}   firings {int(state.sum()):,}")
    print(f"firings/session {state.sum() / n_sessions:.2f}   "
          f"sessions touched by the state {fired.size:,} "
          f"({fired.size / n_sessions:.1%})")

    real_idx = np.flatnonzero(state & (w["vol_q"] >= 0))
    cl = session_clustering(state, sid)
    print(f"variance ratio vs Poisson {cl.variance_ratio:.2f}   "
          f"clean sessions {cl.clean_sessions:,}   "
          f"strict mode available: {cl.strict_is_available}")

    reps = {}
    for mode in ("strict", "bar"):
        draw = make_matched_control(state, sid, w["tod"], w["vol_q"],
                                    condition_name="p03-thin-move", year=w["year"],
                                    session_exclusion=mode)
        rep = verify_control("p03-thin-move", "NQ", real_idx, draw,
                             w["tod"], w["vol_q"], w["year"], strict=False)
        reps[mode] = rep
        print(f"\n{mode:>6} exclusion: matched {rep.n_matched:,}/{rep.n_real:,} "
              f"({1 - rep.unmatched_rate:.1%})  control bars {rep.n_control_bars:,}  "
              f"reuse {rep.reuse_rate:.1%}  fallback {rep.fallback_rate:.1%}  "
              f"verdict {rep.verdict}")
        for f in rep.failures:
            print(f"  - {f}")
    rep = reps["bar"]

    OUT.write_text(
        '{\n'
        f'  "series": "NQ", "bar_minutes": {BAR_MINUTES}, '
        f'"lookback_sessions": {LOOKBACK_SESSIONS},\n'
        f'  "threshold_pct": {THRESHOLD_PCT}, "n_bars": {int(state.size)}, '
        f'"n_sessions": {n_sessions},\n'
        f'  "n_firings": {int(state.sum())}, '
        f'"firings_per_session": {state.sum() / n_sessions:.4f},\n'
        f'  "sessions_touched": {int(fired.size)}, '
        f'"sessions_touched_share": {fired.size / n_sessions:.4f},\n'
        f'  "firings_per_session_variance_ratio": {cl.variance_ratio:.4f},\n'
        f'  "clean_sessions": {cl.clean_sessions}, '
        f'"strict_available": {str(cl.strict_is_available).lower()},\n'
        f'  "strict_verdict": "{reps["strict"].verdict}", '
        f'"strict_fallback_rate": {reps["strict"].fallback_rate:.4f},\n'
        f'  "bar_verdict": "{reps["bar"].verdict}", '
        f'"bar_fallback_rate": {reps["bar"].fallback_rate:.4f},\n'
        f'  "bar_reuse_rate": {reps["bar"].reuse_rate:.4f}, '
        f'"n_matched": {rep.n_matched}\n'
        '}\n', encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
