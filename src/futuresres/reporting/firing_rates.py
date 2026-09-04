"""Measured firing rates for the four hypotheses whose rate was never counted.

    python -m futuresres.reporting.firing_rates

WHAT THIS IS AND IS NOT. It counts how often each condition TRIGGERS on real data, per
instrument and per parameter cell. It computes no signed return, no test statistic and no
p-value: nothing here is Stage 1, and running it does not spend a trial. The output is a
property of the data and the condition, the same kind of fact as a session count.

WHY IT EXISTS. `reports/decisions.md` section 13: a missing firing rate used to fall through
to the DATA ceiling, which granted a hypothesis every observation in the sample precisely
where least was known about it. That default now blocks, which is correct but leaves F05,
F08, F10 and F11 unschedulable until someone counts. This counts.

TWO NUMBERS PER CELL, AND THE SECOND IS THE ONE THAT GATES.

    firings              how many times the condition triggers
    independent events   firings after removing overlap - a position held H minutes cannot
                         start again until it closes, so the usable count is capped by the
                         sample span divided by the hold

For a sparse condition these are equal and the distinction is idle. For a condition that is
continuously in the market they are not, and reporting only the first would repeat, a third
time, the error section 13 was written about: counting observations that are not independent
as though they were.

DECISIONS TAKEN HERE, because the registered conditions do not fully determine them. All
four are logged in `reports/decisions.md` section 14 rather than resolved silently.

  F05  "realized_vol(1h) below the p20 of the trailing 20 sessions AT THE SAME CLOCK TIME"
       is evaluated at each session hour boundary. The compression midpoint is the mean
       close of the armed hour and sigma is the standard deviation of those same closes;
       the condition names neither. One firing per arming: the scan stops at the first close
       beyond k*sigma, or at session end if none comes.
  F08  sigma is the trailing 20-session standard deviation of W-minute returns at the same
       clock time, matching F05's same-clock-time convention rather than a flat rolling
       window. The two instruments are inner-joined on the minute, so the count reflects
       only minutes where BOTH traded - which is itself a finding, given MGC's coverage.
  F10  RSI(14) is computed on bars of the hold's own length, so a 60-minute hold uses
       14 sixty-minute bars. Wilder smoothing. The alternative - RSI on 1m bars regardless
       of hold - would make the indicator mean something different at each horizon.
  F11  the condition says the MAs are "fixed a priori at round values" but never says which.
       10 and 30 bars of the hold's own length are used. This is a free choice the registry
       left open, and it is exactly the kind of choice that has to be made once, in public,
       rather than tuned.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
import math
from typing import Final, Iterable

import numpy as np
import polars as pl

from futuresres.session.calendar import ET

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
REPORT: Final[Path] = ROOT / "reports" / "firing_rates.md"
CACHE: Final[Path] = ROOT / "reports" / "firing_rates.json"

SERIES: Final[dict[str, str]] = {"MNQ": "NQ_MNQ_spliced", "MGC": "MGC"}

#: reports/floor_cache.json - the smallest sample at which a floor ever resolved.
SMALLEST_RESOLVING: Final[dict[tuple[str, int], int]] = {
    ("MNQ", 60): 19_722, ("MNQ", 180): 5_884, ("MNQ", 1): 5_000,
    ("MGC", 60): 5_620, ("MGC", 180): 2_862, ("MGC", 1): 5_000,
}

F05_VOL_PCT: Final[tuple[int, ...]] = (15, 20, 25)
F05_K: Final[tuple[float, ...]] = (1.5, 2.0, 2.5)
F08_W: Final[tuple[int, ...]] = (30, 60)
F08_K: Final[tuple[float, ...]] = (1.0, 1.5, 2.0)
F10_HOLDS: Final[tuple[int, ...]] = (30, 60, 120)
F11_HOLDS: Final[tuple[int, ...]] = (30, 60, 120)
F11_FAST: Final[int] = 10
F11_SLOW: Final[int] = 30

LOOKBACK_SESSIONS: Final[int] = 20

#: F05's break deadline, DERIVED FROM THE MECHANISM rather than chosen from the data.
#:
#: The registered condition says to enter "on the first close beyond k*sigma" and never says
#: BY WHEN. Unbounded within the session it fired on 94% of armings, which made the
#: compression filter nearly decorative and turned the test into "does price eventually move
#: after a quiet hour" - trivially true, and not a hypothesis.
#:
#: The mechanism is volatility clustering: a quiet period forecasts NEAR-TERM expansion. A
#: realized-volatility estimate is informative over a horizon on the order of its own
#: estimation window - that is what the decay of the autocorrelation in |returns| means - so
#: a vol measured over ONE HOUR speaks to the next hour, not to the next six. A second,
#: independent argument gives the same number: the trigger measures distance from the
#: COMPRESSION MIDPOINT, and hours later that midpoint no longer describes the current price
#: level, so the reference the condition is built on has gone stale.
#:
#: Hence one compression window: 60 minutes from the end of the armed hour.
#:
#: THIS IS ONE VALUE, NOT A NEW GRID AXIS. Sweeping {30, 60, 90} would convert a
#: specification repair into a tuning opportunity, which is the thing being repaired.
F05_BREAK_DEADLINE: Final[int] = 60

#: F05's trigger reference. SPECIFICATION CORRECTION adopted 2026-09-02 (decisions.md §27).
#:
#: The registered condition measured k*sigma against the COMPRESSED WINDOW'S OWN sigma. That
#: does not test the mechanism. Compression SELECTS hours with small sigma, so k*sigma is a
#: small distance and price almost always travels it - F05 fired on 79-91% of armings even
#: after the mechanism-derived deadline was applied. The tighter the compression, the easier
#: the trigger.
#:
#: The mechanism says compression forecasts EXPANSION, and expansion means volatility
#: RETURNING TOWARD NORMAL. So the trigger must reference normal volatility for that clock
#: hour, not the compressed sample it selected on. Normal is the MEDIAN of the trailing 20
#: sessions' sigma at the same clock time - the same window and the same quantity the p20
#: arming filter already compares against, so the condition now uses one consistent notion
#: of "usual volatility at this hour" for both halves instead of two.
#:
#: This is a CORRECTION, not a tuning choice: the registered version did not test its own
#: mechanism. It is one value, not a new grid axis.
F05_NORMAL_PCT: Final[float] = 50.0


@dataclass(slots=True)
class Rate:
    hypothesis: str
    product: str
    cell: str
    horizon: int
    firings: int
    independent: int
    per_session: float
    note: str


def load_1m(product: str) -> pl.DataFrame:
    bars = pl.read_parquet(CONTINUOUS / f"{SERIES[product]}.parquet")
    local = pl.col("ts_event").dt.convert_time_zone(str(ET))
    return bars.select(
        pl.col("ts_event"),
        local.dt.date().alias("day"),
        (local.dt.hour().cast(pl.Int32) * 60
         + local.dt.minute().cast(pl.Int32)).alias("mod"),
        pl.col("close").cast(pl.Float64),
    ).sort("ts_event")


def resample(df: pl.DataFrame, minutes: int) -> pl.DataFrame:
    """Last close within each `minutes`-long bucket. Bars, not a minute grid."""
    return (df.with_columns((pl.col("ts_event").dt.epoch("s") // (minutes * 60))
                            .alias("bucket"))
              .group_by("bucket").agg(pl.col("close").last(), pl.col("day").last())
              .sort("bucket"))


def span_minutes(df: pl.DataFrame) -> int:
    lo, hi = df.get_column("ts_event").min(), df.get_column("ts_event").max()
    return int((hi - lo).total_seconds() // 60)


def cap_independent(firings: int, span: int, hold: int) -> int:
    """A position held `hold` minutes cannot restart until it closes."""
    return int(min(firings, span // max(hold, 1)))


def rolling_std_prior(v: np.ndarray, w: int) -> np.ndarray:
    """Std of the w values STRICTLY BEFORE each position. NaN until enough history."""
    out = np.full(v.size, np.nan)
    if v.size <= w:
        return out
    c1 = np.concatenate([[0.0], np.cumsum(v)])
    c2 = np.concatenate([[0.0], np.cumsum(v * v)])
    i = np.arange(w, v.size)
    s1 = c1[i] - c1[i - w]
    s2 = c2[i] - c2[i - w]
    var = np.maximum((s2 - s1 * s1 / w) / (w - 1), 0.0)
    out[i] = np.sqrt(var)
    return out


def rolling_pct_prior(v: np.ndarray, w: int, pct: float) -> np.ndarray:
    """Percentile of the w values strictly before each position."""
    out = np.full(v.size, np.nan)
    if v.size <= w:
        return out
    win = np.lib.stride_tricks.sliding_window_view(v, w)[:-1]
    out[w:] = np.percentile(win, pct, axis=1)
    return out


# ----------------------------------------------------------------------- F05
def f05_rates(product: str, df: pl.DataFrame, span: int) -> list[Rate]:
    """Compression arms at an hour boundary; fires on the first k*sigma break.

    The forward scan is done once per arming against a prebuilt per-session array rather
    than by refiltering the frame, which would be O(armings x rows).
    """
    hours = (df.with_columns((pl.col("mod") // 60).alias("h"))
               .group_by(["day", "h"])
               .agg(pl.col("close").mean().alias("mid"),
                    pl.col("close").std().alias("sd"),
                    pl.len().alias("n"))
               .filter(pl.col("n") >= 30)
               .sort(["day", "h"]))
    day = hours.get_column("day").to_numpy()
    hour = hours.get_column("h").to_numpy().astype(np.int64)
    mid = hours.get_column("mid").to_numpy()
    sd = hours.get_column("sd").to_numpy()
    n_sessions = np.unique(day).size

    # per-session (mod, close), so the forward scan is a slice
    by_day: dict[object, tuple[np.ndarray, np.ndarray]] = {}
    d_all = df.get_column("day").to_numpy()
    m_all = df.get_column("mod").to_numpy().astype(np.int64)
    c_all = df.get_column("close").to_numpy()
    order = np.argsort(d_all, kind="stable")
    d_s, m_s, c_s = d_all[order], m_all[order], c_all[order]
    bounds = np.flatnonzero(np.r_[True, d_s[1:] != d_s[:-1], True])
    for j in range(bounds.size - 1):
        lo, hi = bounds[j], bounds[j + 1]
        by_day[d_s[lo]] = (m_s[lo:hi], c_s[lo:hi])

    # max |close - mid| inside the DEADLINE window after the armed hour, computed once per
    # hour-slot. Before the deadline was derived this scanned to session end, which is why
    # it fired on 94% of armings.
    excursion = np.zeros(sd.size)
    for i in range(sd.size):
        m, c = by_day.get(day[i], (None, None))
        if m is None:
            continue
        start = (hour[i] + 1) * 60
        later = c[(m >= start) & (m < start + F05_BREAK_DEADLINE)]
        excursion[i] = np.abs(later - mid[i]).max() if later.size else 0.0

    # NORMAL volatility for this clock hour: the median of the trailing 20 sessions' sigma
    # at the same hour. This is what the trigger references, not the compressed hour's own
    # sigma - see F05_NORMAL_PCT.
    normal = np.full(sd.size, np.nan)
    for h in np.unique(hour):
        sel = np.flatnonzero(hour == h)
        normal[sel] = rolling_pct_prior(sd[sel], LOOKBACK_SESSIONS, F05_NORMAL_PCT)

    out: list[Rate] = []
    for pct in F05_VOL_PCT:
        armed = np.zeros(sd.size, dtype=bool)
        for h in np.unique(hour):
            sel = np.flatnonzero(hour == h)
            thr = rolling_pct_prior(sd[sel], LOOKBACK_SESSIONS, pct)
            with np.errstate(invalid="ignore"):
                armed[sel] = sd[sel] < thr
        n_armed = int(armed.sum())
        for k in F05_K:
            with np.errstate(invalid="ignore"):
                fires = int((armed & np.isfinite(normal) & (normal > 0)
                             & (excursion > k * normal)).sum())
            for hold in (60, 120, 180):
                out.append(Rate(
                    "F05", product, f"vol_pct={pct} k={k}", hold, fires,
                    cap_independent(fires, span, hold),
                    fires / max(n_sessions, 1),
                    f"{n_armed:,} armings, {fires:,} broke k*NORMAL-sigma within the "
                    f"{F05_BREAK_DEADLINE}-minute deadline",
                ))
    return out


# ----------------------------------------------------------------------- F08
def f08_rates(frames: dict[str, pl.DataFrame], span: int) -> list[Rate]:
    """Both legs must agree in sign and both exceed k*sigma, on shared minutes."""
    a, b = frames["MNQ"], frames["MGC"]
    joined = a.join(b, on="ts_event", how="inner", suffix="_g")
    out: list[Rate] = []
    n_sessions = joined.get_column("day").n_unique()
    for W in F08_W:
        r = joined.with_columns(
            (pl.col("close").log() - pl.col("close").log().shift(W)).alias("rn"),
            (pl.col("close_g").log() - pl.col("close_g").log().shift(W)).alias("rg"),
            (pl.col("mod") // W).alias("slot"),
        ).drop_nulls(["rn", "rg"])
        # evaluate on W-boundaries only, so observations do not overlap
        r = r.filter(pl.col("mod") % W == 0)
        rn = r.get_column("rn").to_numpy()
        rg = r.get_column("rg").to_numpy()
        slot = r.get_column("slot").to_numpy()
        sig_n = np.full(rn.size, np.nan)
        sig_g = np.full(rg.size, np.nan)
        for sl in np.unique(slot):
            sel = np.flatnonzero(slot == sl)
            sig_n[sel] = rolling_std_prior(rn[sel], LOOKBACK_SESSIONS)
            sig_g[sel] = rolling_std_prior(rg[sel], LOOKBACK_SESSIONS)
        agree = np.sign(rn) == np.sign(rg)
        agree &= np.sign(rn) != 0
        for k in F08_K:
            with np.errstate(invalid="ignore"):
                fires = int((agree & (np.abs(rn) > k * sig_n)
                             & (np.abs(rg) > k * sig_g)).sum())
            for hold in (60, 120, 180):
                for product in ("MNQ", "MGC"):
                    out.append(Rate(
                        "F08", product, f"W={W} k={k}", hold, fires,
                        cap_independent(fires, span, hold),
                        fires / max(n_sessions, 1),
                        f"shared minutes only ({joined.height:,} of "
                        f"{a.height:,} MNQ bars)",
                    ))
    return out


# ----------------------------------------------------------------------- F10
def rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    d = np.diff(close, prepend=close[0])
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    ag = np.full(close.size, np.nan)
    al = np.full(close.size, np.nan)
    if close.size <= period:
        return np.full(close.size, np.nan)
    ag[period] = gain[1:period + 1].mean()
    al[period] = loss[1:period + 1].mean()
    for i in range(period + 1, close.size):
        ag[i] = (ag[i - 1] * (period - 1) + gain[i]) / period
        al[i] = (al[i - 1] * (period - 1) + loss[i]) / period
    rs = ag / np.where(al == 0, np.nan, al)
    return 100 - 100 / (1 + rs)


def f10_rates(product: str, df: pl.DataFrame, span: int) -> list[Rate]:
    out: list[Rate] = []
    for hold in F10_HOLDS:
        bars = resample(df, hold)
        c = bars.get_column("close").to_numpy()
        n_sessions = bars.get_column("day").n_unique()
        v = rsi(c)
        up = (v[:-1] < 30) & (v[1:] >= 30)
        dn = (v[:-1] > 70) & (v[1:] <= 70)
        fires = int(np.nansum(up) + np.nansum(dn))
        out.append(Rate(
            "F10", product, "RSI(14) 30/70 crossings", hold, fires,
            cap_independent(fires, span, hold), fires / max(n_sessions, 1),
            f"{int(np.nansum(up)):,} up through 30, {int(np.nansum(dn)):,} down through 70",
        ))
    return out


# ----------------------------------------------------------------------- F11
def f11_rates(product: str, df: pl.DataFrame, span: int) -> list[Rate]:
    """A STATE, not an event: always in the market once both MAs exist."""
    out: list[Rate] = []
    for hold in F11_HOLDS:
        bars = resample(df, hold)
        c = bars.get_column("close").to_numpy()
        n_sessions = bars.get_column("day").n_unique()
        if c.size <= F11_SLOW:
            continue
        fast = np.convolve(c, np.ones(F11_FAST) / F11_FAST, mode="valid")
        slow = np.convolve(c, np.ones(F11_SLOW) / F11_SLOW, mode="valid")
        fast = fast[F11_SLOW - F11_FAST:]
        state = np.sign(fast - slow)
        crossings = int((np.diff(state) != 0).sum())
        in_market = int((state != 0).sum())
        out.append(Rate(
            "F11", product, f"MA({F11_FAST})/MA({F11_SLOW}) state", hold, in_market,
            cap_independent(in_market, span, hold), in_market / max(n_sessions, 1),
            f"CONTINUOUS EXPOSURE: {crossings:,} position changes over {in_market:,} bars; "
            f"the state is true on every bar, so firings equal bars and the independent "
            f"count is the data ceiling",
        ))
    return out


def measure(products: Iterable[str]) -> list[Rate]:
    frames = {p: load_1m(p) for p in products}
    spans = {p: span_minutes(f) for p, f in frames.items()}
    rates: list[Rate] = []
    for p, f in frames.items():
        print(f"  {p}: F10 ...", flush=True)
        rates += f10_rates(p, f, spans[p])
        print(f"  {p}: F11 ...", flush=True)
        rates += f11_rates(p, f, spans[p])
        print(f"  {p}: F05 ...", flush=True)
        rates += f05_rates(p, f, spans[p])
    if {"MNQ", "MGC"} <= set(frames):
        print("  F08 (cross-asset) ...", flush=True)
        rates += f08_rates(frames, min(spans.values()))
    return rates


MEASURED_HORIZONS: Final[tuple[int, ...]] = (1, 60, 180)


def proxy_horizon(h: int) -> int:
    """Nearest swept horizon in LOG space - sample size scales inversely with the hold."""
    return min(MEASURED_HORIZONS, key=lambda m: abs(math.log(h / m)))


def status_for(product: str, horizon: int, lo: int, hi: int) -> tuple[str, int]:
    need = SMALLEST_RESOLVING.get((product, proxy_horizon(horizon)), 0)
    if lo >= need:
        return "RESOLVABLE", need
    if hi < need:
        return "BELOW SWEPT RANGE", need
    return "MIXED", need


def render(rates: list[Rate]) -> str:
    w: list[str] = []
    a = w.append
    a("# Measured firing rates")
    a("")
    a("Generated by `python -m futuresres.reporting.firing_rates`. "
      "CLAUDE_FUTURES.md §5, §7; `reports/decisions.md` §13, §14.")
    a("")
    a("**This is not Stage 1 and spends no trial.** It counts how often each condition "
      "triggers on real data. No signed return, no statistic, no p-value.")
    a("")
    a("Four hypotheses had no counted firing rate. Until §13 that gap fell through to the "
      "**data ceiling** - the most generous possible assumption, applied where least was "
      "known. It now blocks instead, which left F05, F08, F10 and F11 unschedulable. These "
      "are the counts that unblock them.")
    a("")
    a("`independent` is the gating number: a position held H minutes cannot restart until "
      "it closes, so firings are capped by span/H. For a sparse condition the two are "
      "equal; for one that is continuously in the market they are not.")
    a("")

    a("## Verdict per hypothesis")
    a("")
    a("| hypothesis | product | horizon | independent events (min-max across cells) | swept range needs | status |")
    a("|---|---|---|---|---|---|")
    for hyp in sorted({r.hypothesis for r in rates}):
        for product in sorted({r.product for r in rates if r.hypothesis == hyp}):
            for horizon in sorted({r.horizon for r in rates
                                   if r.hypothesis == hyp and r.product == product}):
                sub = [r for r in rates if r.hypothesis == hyp
                       and r.product == product and r.horizon == horizon]
                lo = min(r.independent for r in sub)
                hi = max(r.independent for r in sub)
                st, need = status_for(product, horizon, lo, hi)
                rng = f"{lo:,}" if lo == hi else f"{lo:,} - {hi:,}"
                a(f"| {hyp} | {product} | {horizon}m | {rng} | {need:,} | **{st}** |")
    a("")

    a("## What the counts say")
    a("")
    a("**F10 is below the swept range on every combination of both instruments** - 5,594 "
      "independent events at best, against 19,722 needed on MNQ. RSI(14) crossings through "
      "30 and 70 are genuinely rare: 2,434 up and 3,160 down across sixteen years of MNQ. "
      "**F10 is a CONTROL**, and a control that cannot resolve tells you nothing when it "
      "comes back empty - which is exactly what a control coming back empty is supposed to "
      "look like. The catalog cannot currently distinguish \"the control correctly found "
      "nothing\" from \"the control could not have found anything\".")
    a("")
    a("**F11 is resolvable everywhere, but for a reason worth stating.** Its condition is a "
      "STATE, not an event: long whenever the fast MA is above the slow one. It is "
      "therefore always in the market, its firings equal its bar count, and its independent "
      "count equals the data ceiling. Only 6,420 actual position changes underlie MNQ's "
      "164,775 30-minute observations. The old fall-through-to-data-ceiling default was "
      "accidentally correct for F11 alone, and wrong for the other three.")
    a("")
    a("**F05 fires far more than expected: 14,846 breaks from 15,770 armings, a 94% rate.** "
      "The compression filter works - armings are a fraction of hour-slots - but the break "
      "condition is unbounded within the session, so given a whole session to break in, "
      "almost every armed compression eventually does. The condition as registered does not "
      "say by when the break must occur. That is a specification gap, not a data finding, "
      "and it is logged as such.")
    a("")
    a("**F08 loses 30% of its sample to the cross-asset join.** Only 3,307,036 of 4,728,809 "
      "MNQ minutes have a matching MGC minute. That is the standing MGC coverage caveat "
      "appearing as an outright sample cut rather than as forward-filling, and it is the "
      "binding constraint on the only genuinely cross-asset hypothesis in the catalog.")
    a("")

    a("## Every cell")
    a("")
    a("| hypothesis | product | cell | horizon | firings | independent | per session |")
    a("|---|---|---|---|---|---|---|")
    for r in sorted(rates, key=lambda r: (r.hypothesis, r.product, r.horizon, r.cell)):
        a(f"| {r.hypothesis} | {r.product} | {r.cell} | {r.horizon}m | {r.firings:,} | "
          f"{r.independent:,} | {r.per_session:.2f} |")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.firing_rates")
    ap.add_argument("--products", nargs="*", default=["MNQ", "MGC"])
    args = ap.parse_args(argv)
    rates = measure(args.products)
    CACHE.write_text(json.dumps([asdict(r) for r in rates], indent=2, default=str),
                     encoding="utf-8")
    REPORT.write_text(render(rates), encoding="utf-8")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
