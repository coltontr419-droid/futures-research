"""Level constructors and trigger counters for the L-series. No statistics, no trials.

Each function returns the LEVELS a hypothesis references and the TRIGGERS its condition
produces, with every threshold applied. That is what the gate needs and it is all this module
computes: no return series, no p-value, no Stage 1.

THE SESSION GRID IS THE CME TRADING DAY, 18:00 ET to 16:55 ET, 1,375 minutes, matching F05.
Level hypotheses reference both overnight and RTH structure, so a row must span both, and the
17:00-18:00 maintenance break falls outside the row rather than inside it.

TRIGGER TIMESTAMPS ARE RETAINED, not just counted. Disjointness - whether two cells of the
same hypothesis fire on the same minute - decides whether an aggregate verdict route exists,
and the F07 finding was that assuming disjointness where cells overlap silently inflates the
sample. The counts alone cannot answer that question, so the minutes are kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final, Iterator

import numpy as np
import polars as pl

from futuresres.session.calendar import ET

ROW_START_MOD: Final[int] = 18 * 60
ROW_MINUTES: Final[int] = 1375
#: Minute-of-row for 09:30 ET and 16:00 ET, the RTH bounds inside the trading day.
RTH_OPEN: Final[int] = (9 * 60 + 30 - ROW_START_MOD) % 1440      # 930
RTH_CLOSE: Final[int] = (16 * 60 - ROW_START_MOD) % 1440         # 1320
RTH_EXIT: Final[int] = (15 * 60 + 55 - ROW_START_MOD) % 1440     # 1315

#: Session windows in minute-of-row, from the DST-aware mapper's definitions.
SESSION_BOUNDS: Final[dict[str, tuple[int, int]]] = {
    "Asia": ((19 * 60 - ROW_START_MOD) % 1440, (3 * 60 - ROW_START_MOD) % 1440),
    "London": ((3 * 60 - ROW_START_MOD) % 1440, (11 * 60 + 30 - ROW_START_MOD) % 1440),
    "US": (RTH_OPEN, RTH_CLOSE),
}

TICK: Final[dict[str, float]] = {"MNQ": 0.25, "MGC": 0.1}
SERIES: Final[dict[str, str]] = {"MNQ": "NQ_MNQ_spliced", "MGC": "MGC"}
LOOKBACK: Final[int] = 20


@dataclass(slots=True)
class Grid:
    """Complete trading-day grid: one row per day, 1,375 minutes."""

    days: np.ndarray          # date per row
    close: np.ndarray         # (n, 1375)
    high: np.ndarray
    low: np.ndarray
    volume: np.ndarray
    fill_fraction: float

    @property
    def n(self) -> int:
        return self.days.size

    def atr(self) -> np.ndarray:
        """ATR(20) per row from DAILY true range, strictly prior sessions.

        This is the scale the `>= d ATR away` preconditions of L01, L06 and L08 use, and it
        stays daily because WHICH ATR those conditions mean is an OPEN SPECIFICATION
        QUESTION - see reports/CHECKPOINT.md and decisions.md 36. Changing it would change
        those hypotheses' firing rates, which is choosing a parameter to get a result.
        `intraday_atr` exists for the placebo scale, where the criterion is external.
        """
        hi = self.high.max(axis=1)
        lo = self.low.min(axis=1)
        cl = self.close[:, -1]
        prev = np.concatenate([[np.nan], cl[:-1]])
        tr = np.maximum(hi, prev) - np.minimum(lo, prev)
        out = np.full(self.n, np.nan)
        for i in range(LOOKBACK, self.n):
            out[i] = np.nanmean(tr[i - LOOKBACK:i])
        return out

    def intraday_atr(self, horizon: int) -> np.ndarray:
        """Typical `horizon`-minute high-low range per row, over the prior LOOKBACK sessions.

        Strictly prior, exactly like `atr()`. The row is split into consecutive
        non-overlapping blocks of `horizon` minutes, each block's range is taken, and the
        session's mean block range is averaged across the previous twenty sessions.

        At `horizon = ROW_MINUTES` this degenerates to the session's own high-low range,
        which is daily true range minus the gap term - so the two scales agree at the top
        end and diverge, correctly, as the horizon shortens.
        """
        t = int(min(max(horizon, 1), ROW_MINUTES))
        n_blocks = max(ROW_MINUTES // t, 1)
        use = n_blocks * t
        hi = self.high[:, :use].reshape(self.n, n_blocks, t).max(axis=2)
        lo = self.low[:, :use].reshape(self.n, n_blocks, t).min(axis=2)
        per_row = np.nanmean(hi - lo, axis=1)
        out = np.full(self.n, np.nan)
        for i in range(LOOKBACK, self.n):
            out[i] = np.nanmean(per_row[i - LOOKBACK:i])
        return out


def load(product: str, root) -> Grid:
    bars = pl.read_parquet(root / "data" / "continuous" / f"{SERIES[product]}.parquet")
    local = pl.col("ts_event").dt.convert_time_zone(str(ET))
    f = bars.with_columns(
        (local.dt.hour().cast(pl.Int32) * 60
         + local.dt.minute().cast(pl.Int32)).alias("mod"),
        local.dt.date().alias("d"),
    ).with_columns(
        ((pl.col("mod") - ROW_START_MOD) % 1440).alias("m"),
    ).filter(pl.col("m") < ROW_MINUTES).with_columns(
        pl.when(pl.col("mod") >= ROW_START_MOD)
          .then(pl.col("d") + pl.duration(days=1))
          .otherwise(pl.col("d")).alias("row"),
    )
    rows = f.get_column("row").to_numpy()
    mins = f.get_column("m").to_numpy().astype(np.int64)
    days = np.unique(rows)
    pos = np.searchsorted(days, rows) * ROW_MINUTES + mins

    traded_cells = {"n": 0}

    def grid_of(col: str, fill: float) -> np.ndarray:
        flat = np.full(days.size * ROW_MINUTES, np.nan)
        flat[pos] = f.get_column(col).to_numpy().astype(float)
        # Count BEFORE filling. Counting after would read 100% for every product, which is
        # exactly what an earlier draft of this loader did.
        traded_cells["n"] = max(traded_cells["n"], int(np.isfinite(flat).sum()))
        g = flat.reshape(days.size, ROW_MINUTES)
        ok = np.isfinite(g)
        idx = np.where(ok, np.arange(ROW_MINUTES)[None, :], 0)
        np.maximum.accumulate(idx, axis=1, out=idx)
        out = np.take_along_axis(g, idx, axis=1)
        first = np.argmax(ok, axis=1)
        for i in np.flatnonzero(ok.any(axis=1) & ~np.isfinite(out[:, 0])):
            out[i, : first[i]] = g[i, first[i]]
        return out

    close = grid_of("close", np.nan)
    traded = traded_cells["n"]
    high, low = grid_of("high", np.nan), grid_of("low", np.nan)
    vol = np.nan_to_num(grid_of("volume", 0.0))
    keep = np.isfinite(close).all(axis=1) & np.isfinite(high).all(axis=1) \
        & np.isfinite(low).all(axis=1)
    return Grid(days[keep], close[keep], high[keep], low[keep], vol[keep],
                float(traded) / max(close.size, 1))


# --------------------------------------------------------------------- levels
@dataclass(slots=True)
class LevelSet:
    """Levels of one type, one per (row, index), with the minute they become valid."""

    kind: str
    price: np.ndarray         # (n_levels,)
    row: np.ndarray           # row index
    valid_from: np.ndarray    # minute-of-row from which the level can be touched
    ref_price: np.ndarray     # price at creation, for the distance metric


def _stack(kind, price, row, valid, ref) -> LevelSet:
    return LevelSet(kind, np.asarray(price, float), np.asarray(row, int),
                    np.asarray(valid, int), np.asarray(ref, float))


#: Horizons at which intraday range is measured before interpolating. Roughly factor-two
#: spacing from one minute to the whole trading day; the interpolation below is what makes
#: the spacing non-critical.
ATR_HORIZONS: Final[tuple[int, ...]] = (1, 2, 5, 15, 30, 60, 120, 240, 480, ROW_MINUTES)


def window_scale(g: Grid, levels: LevelSet) -> np.ndarray:
    """The offset scale for a placebo: intraday range over each level's OWN live window.

    THIS IS THE FIX FOR THE PLACEBO MISMATCH THAT FAILED 53 OF 55 LEVEL TYPES. The scale
    used to be daily ATR(20) for every level type at once, which put placebos 3x to 63x
    further from price than the real levels they stood in for. Real levels are touched
    30-96% of the time and those placebos 6-17%, so every real-minus-placebo difference
    would have been a difference in EXPOSURE rather than in reaction.

    THE TIMESCALE A LEVEL OPERATES ON IS ITS VALIDITY WINDOW, not its construction period.
    `touches` tests every level against the remainder of ITS OWN ROW, from `valid_from` to
    the close - a prior-month level and a one-minute fair-value gap are both live for the
    rest of a single trading day and no longer. So the question a placebo has to match is
    "how far does price travel in the time this level is reachable", and that is the range
    over ROW_MINUTES - valid_from minutes.

    That also explains why prior_week and prior_month were the only two types that passed
    under the old daily scale: they are the two whose real distance from price is already
    of daily-ATR order, so the wrong scale happened to be the right size for them alone.

    Interpolation is linear in log(range) against log(horizon), which is exact for a random
    walk (range ~ sqrt(T)) and stays close under the real U-shaped intraday profile.
    """
    live = np.clip(ROW_MINUTES - levels.valid_from, 1, ROW_MINUTES)
    table = np.vstack([g.intraday_atr(h) for h in ATR_HORIZONS])   # (h, rows)
    xs = np.log(np.asarray(ATR_HORIZONS, dtype=float))
    out = np.full(levels.price.size, np.nan)
    for i, (r, w) in enumerate(zip(levels.row, live)):
        col = table[:, r]
        good = np.isfinite(col) & (col > 0)
        if good.sum() < 2:
            continue
        out[i] = float(np.exp(np.interp(np.log(w), xs[good], np.log(col[good]))))
    return out


def vwap_levels(g: Grid, anchor: str) -> LevelSet:
    """Session VWAP, sampled once per row at 10:30 ET so it is a level rather than a curve."""
    tp = (g.high + g.low + g.close) / 3.0
    if anchor == "RTH":
        start = RTH_OPEN
    elif anchor == "CME":
        start = 0
    else:                                    # rolling 24h == the whole row
        start = 0
    num = np.cumsum(tp[:, start:] * g.volume[:, start:], axis=1)
    den = np.cumsum(g.volume[:, start:], axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        vwap = np.where(den > 0, num / den, np.nan)
    sample = RTH_OPEN + 60 - start           # 10:30 ET
    if sample >= vwap.shape[1]:
        sample = vwap.shape[1] - 1
    price = vwap[:, sample]
    valid = np.full(g.n, start + sample + 1)
    return _stack(f"vwap_{anchor}", price, np.arange(g.n), valid,
                  g.close[np.arange(g.n), np.minimum(valid, ROW_MINUTES - 1)])


def opening_range(g: Grid, W: int) -> LevelSet:
    hi = g.high[:, RTH_OPEN:RTH_OPEN + W].max(axis=1)
    lo = g.low[:, RTH_OPEN:RTH_OPEN + W].min(axis=1)
    n = g.n
    valid = np.full(n, RTH_OPEN + W)
    ref = g.close[:, RTH_OPEN + W]
    return _stack(f"or{W}", np.concatenate([hi, lo]),
                  np.concatenate([np.arange(n)] * 2),
                  np.concatenate([valid] * 2), np.concatenate([ref] * 2))


def prior_day_levels(g: Grid, kind: str) -> LevelSet:
    if kind == "prior_rth":
        hi = g.high[:, RTH_OPEN:RTH_CLOSE].max(axis=1)
        lo = g.low[:, RTH_OPEN:RTH_CLOSE].min(axis=1)
    else:
        hi, lo = g.high.max(axis=1), g.low.min(axis=1)
    n = g.n
    rows = np.arange(1, n)
    price = np.concatenate([hi[:-1], lo[:-1]])
    row = np.concatenate([rows, rows])
    valid = np.zeros(row.size, int)
    ref = g.close[row, 0]
    return _stack(kind, price, row, valid, ref)


def session_extremes(g: Grid, session: str) -> LevelSet:
    lo_m, hi_m = SESSION_BOUNDS[session]
    if hi_m <= lo_m:
        hi_m = ROW_MINUTES
    hi = g.high[:, lo_m:hi_m].max(axis=1)
    lo = g.low[:, lo_m:hi_m].min(axis=1)
    n = g.n
    valid = np.full(n, min(hi_m, ROW_MINUTES - 1))
    return _stack(f"sess_{session}", np.concatenate([hi, lo]),
                  np.concatenate([np.arange(n)] * 2), np.concatenate([valid] * 2),
                  np.concatenate([g.close[np.arange(n), valid]] * 2))


def overnight_range(g: Grid) -> LevelSet:
    hi = g.high[:, :RTH_OPEN].max(axis=1)
    lo = g.low[:, :RTH_OPEN].min(axis=1)
    n = g.n
    valid = np.full(n, RTH_OPEN)
    return _stack("on_range", np.concatenate([hi, lo]),
                  np.concatenate([np.arange(n)] * 2), np.concatenate([valid] * 2),
                  np.concatenate([g.close[:, RTH_OPEN]] * 2))


def session_open(g: Grid, kind: str) -> LevelSet:
    m = RTH_OPEN if kind == "RTH" else 0
    price = g.close[:, m]
    return _stack(f"open_{kind}", price, np.arange(g.n),
                  np.full(g.n, m + 1), price)


def weekly_monthly(g: Grid, kind: str) -> LevelSet:
    """Prior week / prior month extremes. Levels created at each period boundary."""
    import datetime as _dt

    # g.days arrives as numpy.datetime64; datetime64 has no calendar methods, so coerce
    # once here rather than discovering it mid-batch. Same class of bug as F04's
    # datetime.combine() rejecting a datetime64.
    def _as_date(d):
        if isinstance(d, np.datetime64):
            return d.astype("datetime64[D]").astype(_dt.date)
        return d

    keys = [(_as_date(d).isocalendar()[:2] if kind == "week"
             else (_as_date(d).year, _as_date(d).month))
            for d in g.days]
    price, row, valid, ref = [], [], [], []
    start = 0
    for i in range(1, g.n + 1):
        if i == g.n or keys[i] != keys[start]:
            hi = g.high[start:i].max()
            lo = g.low[start:i].min()
            if i < g.n:
                price += [hi, lo]
                row += [i, i]
                valid += [0, 0]
                ref += [g.close[i, 0]] * 2
            start = i
    return _stack(f"prior_{kind}", price, row, valid, ref)


def ema_levels(g: Grid, period: int, tf: int) -> LevelSet:
    """EMA sampled once per row at 10:30 ET, so it is a level rather than a curve."""
    step = tf
    sampled = g.close[:, ::step]
    alpha = 2.0 / (period + 1)
    flat = sampled.ravel()
    ema = np.empty_like(flat)
    ema[0] = flat[0]
    for i in range(1, flat.size):
        ema[i] = alpha * flat[i] + (1 - alpha) * ema[i - 1]
    ema = ema.reshape(sampled.shape)
    col = min((RTH_OPEN + 60) // step, ema.shape[1] - 1)
    price = ema[:, col]
    valid = np.full(g.n, RTH_OPEN + 60 + 1)
    return _stack(f"ema{period}_{tf}m", price, np.arange(g.n), valid,
                  g.close[:, min(RTH_OPEN + 60, ROW_MINUTES - 1)])


def fvg_zones(g: Grid, w_ticks: int, tf: int, product: str) -> LevelSet:
    """Three-bar imbalance midpoints, on `tf`-minute bars, at least w ticks wide."""
    step = tf
    hi = np.maximum.reduceat(g.high, np.arange(0, ROW_MINUTES, step), axis=1)
    lo = np.minimum.reduceat(g.low, np.arange(0, ROW_MINUTES, step), axis=1)
    tick = TICK[product] * w_ticks
    bull = lo[:, 2:] - hi[:, :-2]
    bear = lo[:, :-2] - hi[:, 2:]
    price, row, valid, ref = [], [], [], []
    for r in range(g.n):
        for j in np.flatnonzero(bull[r] >= tick):
            price.append((hi[r, j] + lo[r, j + 2]) / 2)
            row.append(r); valid.append(min((j + 3) * step, ROW_MINUTES - 1))
            ref.append(g.close[r, min((j + 3) * step, ROW_MINUTES - 1)])
        for j in np.flatnonzero(bear[r] >= tick):
            price.append((hi[r, j + 2] + lo[r, j]) / 2)
            row.append(r); valid.append(min((j + 3) * step, ROW_MINUTES - 1))
            ref.append(g.close[r, min((j + 3) * step, ROW_MINUTES - 1)])
    return _stack(f"fvg_w{w_ticks}_{tf}m", price, row, valid, ref)


# --------------------------------------------------------------------- triggers
def touches(g: Grid, levels: LevelSet, tol_ticks: float, product: str,
            require_away: float = 0.0, atr: np.ndarray | None = None,
            away_minutes: int = 15) -> tuple[np.ndarray, np.ndarray]:
    """First minute price comes within `tol_ticks` of each level after it is valid.

    Returns (touched_mask, minute_of_touch). `require_away` in ATR units imposes the
    "after being >= d ATR away for >= away_minutes" precondition used by L01, L06 and L08.
    """
    tol = TICK[product] * tol_ticks
    touched = np.zeros(levels.price.size, bool)
    minute = np.full(levels.price.size, -1, int)
    for i, (px, r, v) in enumerate(zip(levels.price, levels.row, levels.valid_from)):
        if not np.isfinite(px) or v >= ROW_MINUTES - 1:
            continue
        path = g.close[r, v:]
        near = np.abs(path - px) <= tol
        if require_away > 0.0 and atr is not None and np.isfinite(atr[r]) and atr[r] > 0:
            far = np.abs(path - px) >= require_away * atr[r]
            # The condition is "price was >= d ATR away for >= away_minutes, THEN touched".
            # Once a qualifying run of far bars has completed, the qualification is EARNED
            # and survives price moving back through the middle zone - which it must do to
            # reach the level at all. An earlier draft reset on any non-far bar, so the
            # precondition almost never fired: 6 touches in sixteen years.
            run = 0
            qualified = False
            first = -1
            for j in range(path.size):
                if far[j]:
                    run += 1
                    if run >= away_minutes:
                        qualified = True
                else:
                    run = 0
                if qualified and near[j]:
                    first = j
                    break
            if first < 0:
                continue
            touched[i] = True
            minute[i] = v + first
            continue
        idx = np.flatnonzero(near)
        if idx.size:
            touched[i] = True
            minute[i] = v + int(idx[0])
    return touched, minute


def sweep_reclaim(g: Grid, levels: LevelSet, m_ticks: int, k_bars: int,
                  product: str) -> tuple[np.ndarray, np.ndarray]:
    """Price exceeds a level by >= m ticks, then closes back inside within k bars."""
    m = TICK[product] * m_ticks
    fired = np.zeros(levels.price.size, bool)
    minute = np.full(levels.price.size, -1, int)
    for i, (px, r, v) in enumerate(zip(levels.price, levels.row, levels.valid_from)):
        if not np.isfinite(px) or v >= ROW_MINUTES - k_bars - 1:
            continue
        path = g.close[r, v:]
        beyond_up = path > px + m
        beyond_dn = path < px - m
        for j in np.flatnonzero(beyond_up | beyond_dn):
            if j + k_bars >= path.size:
                break
            window = path[j + 1: j + 1 + k_bars]
            back = (window <= px) if beyond_up[j] else (window >= px)
            if back.any():
                fired[i] = True
                minute[i] = v + j + 1 + int(np.argmax(back))
                break
    return fired, minute


def confirmed_break(g: Grid, levels: LevelSet, k_bars: int, product: str,
                    rth_only: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """First run of k consecutive closes beyond a level."""
    fired = np.zeros(levels.price.size, bool)
    minute = np.full(levels.price.size, -1, int)
    for i, (px, r, v) in enumerate(zip(levels.price, levels.row, levels.valid_from)):
        if not np.isfinite(px):
            continue
        lo = max(v, RTH_OPEN) if rth_only else v
        if lo >= ROW_MINUTES - k_bars - 1:
            continue
        path = g.close[r, lo:RTH_EXIT] if rth_only else g.close[r, lo:]
        up = path > px
        dn = path < px
        run_u = run_d = 0
        for j in range(path.size):
            run_u = run_u + 1 if up[j] else 0
            run_d = run_d + 1 if dn[j] else 0
            if run_u >= k_bars or run_d >= k_bars:
                fired[i] = True
                minute[i] = lo + j
                break
    return fired, minute


# --------------------------------------------------------------------- curves
def vwap_curve(g: Grid, anchor: str) -> np.ndarray:
    """Running session VWAP, (n, ROW_MINUTES). NaN before the anchor."""
    tp = (g.high + g.low + g.close) / 3.0
    start = RTH_OPEN if anchor == "RTH" else 0
    out = np.full_like(g.close, np.nan)
    num = np.cumsum(tp[:, start:] * g.volume[:, start:], axis=1)
    den = np.cumsum(g.volume[:, start:], axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out[:, start:] = np.where(den > 0, num / den, np.nan)
    return out


def ema_curve(g: Grid, period: int, tf: int) -> np.ndarray:
    """Running EMA on tf-minute bars, expanded back to minute resolution."""
    sampled = g.close[:, ::tf]
    alpha = 2.0 / (period + 1)
    flat = sampled.ravel()
    ema = np.empty_like(flat)
    ema[0] = flat[0]
    for i in range(1, flat.size):
        ema[i] = alpha * flat[i] + (1 - alpha) * ema[i - 1]
    ema = ema.reshape(sampled.shape)
    return np.repeat(ema, tf, axis=1)[:, :ROW_MINUTES]


def curve_touches(g: Grid, curve: np.ndarray, tol_ticks: float, product: str,
                  require_away: float, atr: np.ndarray,
                  away_minutes: int) -> tuple[np.ndarray, np.ndarray]:
    """Touches of a MOVING reference, one per row.

    VWAP and a moving average are CURVES, not levels: the condition says price trades within
    t ticks of VWAP, meaning VWAP at that minute. Sampling the curve once and treating the
    snapshot as a static level understates the firing rate by orders of magnitude - an
    earlier draft of this module measured 0.2-2.3% of sessions where the real rate is many
    touches a session, which would have misrouted the whole scheduling decision.

    Returns (fired per row, first qualifying minute per row).
    """
    tol = TICK[product] * tol_ticks
    n = g.n
    fired = np.zeros(n, bool)
    minute = np.full(n, -1, int)
    dist = np.abs(g.close - curve)
    for r in range(n):
        a = atr[r]
        if not np.isfinite(a) or a <= 0:
            continue
        d = dist[r]
        far = d >= require_away * a
        near = d <= tol
        run = 0
        qualified = False
        for j in range(d.size):
            if not np.isfinite(d[j]):
                run = 0
                continue
            if far[j]:
                run += 1
                if run >= away_minutes:
                    qualified = True
            else:
                run = 0
            if qualified and near[j]:
                fired[r] = True
                minute[r] = j
                break
    return fired, minute
