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
    """Build the (sessions x 1375) grid for one product.

    MEMORY IS THE CONSTRAINT HERE, NOT SPEED. An earlier version read every column and kept
    the whole DataFrame alive while allocating four full grids plus their transients. On the
    spliced NQ+MNQ series - 4.73M bars over 4,125 sessions - that peaked near 875 MB and was
    OOM-killed on a 2.7 GB machine, four times. Two changes fix it and neither touches what
    the grid CONTAINS:

      * READ ONLY THE FIVE COLUMNS USED. `symbol`, `contract`, `source` and `open` are never
        read by any level definition, and three of them are strings on 4.7M rows.
      * DROP THE FRAME BEFORE BUILDING THE GRIDS, and release each column as it is consumed,
        so the DataFrame peak and the grid peak do not overlap.

    Prices stay float64. float32 would halve the grids again and carries ~7 significant
    digits, which is not enough for an index at 20,000.00 where levels are compared to the
    tick.
    """
    bars = (
        pl.scan_parquet(root / "data" / "continuous" / f"{SERIES[product]}.parquet")
        .select("ts_event", "high", "low", "close", "volume")
        .collect(engine="streaming")
    )
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
    del bars

    rows = f.get_column("row").to_numpy()
    mins = f.get_column("m").to_numpy().astype(np.int64)
    days = np.unique(rows)
    pos = np.searchsorted(days, rows) * ROW_MINUTES + mins
    del rows, mins

    # Materialise the four value columns, then release the frame. This is the whole point:
    # ~500 MB of DataFrame is gone before the first 45 MB grid is allocated.
    values = {c: f.get_column(c).to_numpy().astype(float)
              for c in ("close", "high", "low", "volume")}
    del f

    traded_cells = {"n": 0}

    def grid_of(col: str, fill: float) -> np.ndarray:
        flat = np.full(days.size * ROW_MINUTES, np.nan)
        flat[pos] = values.pop(col)          # pop, so the column is freed as it is consumed
        # Count BEFORE filling. Counting after would read 100% for every product, which is
        # exactly what an earlier draft of this loader did.
        traded_cells["n"] = max(traded_cells["n"], int(np.isfinite(flat).sum()))
        g = flat.reshape(days.size, ROW_MINUTES)
        ok = np.isfinite(g)
        # int32 indices: ROW_MINUTES is 1,375, so the range is nowhere near int32's limit
        # and this halves the largest transient in the function.
        idx = np.where(ok, np.arange(ROW_MINUTES, dtype=np.int32)[None, :],
                       np.int32(0))
        np.maximum.accumulate(idx, axis=1, out=idx)
        out = np.take_along_axis(g, idx, axis=1)
        del idx
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


def bollinger_levels(g: Grid, period: int = 20, k: float = 2.0,
                     tf: int = 60) -> tuple[LevelSet, LevelSet]:
    """L11's band boundaries on `tf`-minute bars, sampled once per row at 10:30 ET.

    PERIOD AND k ARE FIXED A PRIORI at the standard 20 and 2.0 and are NOT swept. That is
    the whole point of the registration: the mechanism on offer is that these PARTICULAR
    settings are the ones chart platforms draw by default, so orders cluster near them. A
    period chosen because it scored better would be a different claim carrying no
    self-fulfilling story at all - and it is the same tell L08's condition names, where "if
    47 works and 50 does not" is evidence against the premise rather than for the parameter.

    Sampled once per row rather than followed as a curve, exactly as `ema_levels` does, so
    the band boundary is a LEVEL and the existing placebo construction applies to it
    unchanged. `ema_curve`/`curve_touches` exist for the curve reading and L11 does not use
    them.

    Returns (upper, lower) as SEPARATE LevelSets. A break above the upper band and one below
    the lower band are different events; giving them one level type would let a placebo drawn
    for the upper stand in for the lower, and the distance distributions are not the same.

    Population sigma (ddof=0) over a window that INCLUDES the current bar - both are the
    standard definition and both are what the platform draws, which is the only thing that
    makes the order-clustering story coherent. Warm-up rows are NaN rather than
    back-filled: a band computed from fewer than `period` bars is not the band anyone is
    watching.
    """
    step = int(tf)
    sampled = g.close[:, ::step]
    flat = sampled.ravel().astype(float)
    mean = np.full(flat.size, np.nan)
    sd = np.full(flat.size, np.nan)
    if flat.size >= period:
        win = np.lib.stride_tricks.sliding_window_view(flat, period)
        mean[period - 1:] = win.mean(axis=1)
        sd[period - 1:] = win.std(axis=1)
    upper = (mean + k * sd).reshape(sampled.shape)
    lower = (mean - k * sd).reshape(sampled.shape)

    col = min((RTH_OPEN + 60) // step, sampled.shape[1] - 1)
    rows = np.arange(g.n)
    valid = np.full(g.n, RTH_OPEN + 60 + 1)
    ref = g.close[:, min(RTH_OPEN + 60, ROW_MINUTES - 1)]
    tag = f"bb{period}k{k:g}_{tf}m"
    return (_stack(f"{tag}_upper", upper[:, col], rows, valid, ref),
            _stack(f"{tag}_lower", lower[:, col], rows, valid, ref))


def fvg_zones_directed(g: Grid, w_ticks: int, tf: int,
                       product: str, *, w_bps: float | None = None
                       ) -> tuple[LevelSet, np.ndarray, np.ndarray]:
    """Three-bar imbalances with the two properties `fvg_zones` throws away.

    Returns (levels, half_width, direction) where `direction` is the sign of the move that
    CREATED the gap: +1 for a bullish imbalance, -1 for a bearish one. L07's registered
    entry is "counter to the move that created the gap", so the traded direction is
    -direction, and its zone has a width that a midpoint alone cannot express.

    `fvg_zones` delegates here so the two cannot drift apart - the measurement pipeline's
    committed output depends on the midpoints being identical.
    """
    step = tf
    hi = np.maximum.reduceat(g.high, np.arange(0, ROW_MINUTES, step), axis=1)
    lo = np.minimum.reduceat(g.low, np.arange(0, ROW_MINUTES, step), axis=1)
    # SCALE-INVARIANT OPTION (decisions.md 52). With `w_bps` the minimum gap is a fraction of
    # price at the gap's first bar rather than a fixed number of ticks. The index rose 14x over
    # 2010-2026, so a fixed tick threshold was ~14x tighter in relative terms early in the
    # sample than late. Default (w_bps None) is unchanged, byte for byte.
    if w_bps is None:
        tick = TICK[product] * w_ticks
    else:
        tick = (w_bps * 1e-4) * hi[:, :-2]
    bull = lo[:, 2:] - hi[:, :-2]
    bear = lo[:, :-2] - hi[:, 2:]
    price, row, valid, ref, half, direction = [], [], [], [], [], []
    for r in range(g.n):
        thr = tick if np.ndim(tick) == 0 else tick[r]
        for j in np.flatnonzero(bull[r] >= thr):
            top, bot = lo[r, j + 2], hi[r, j]
            price.append((bot + top) / 2)
            half.append((top - bot) / 2)
            direction.append(1.0)
            row.append(r); valid.append(min((j + 3) * step, ROW_MINUTES - 1))
            ref.append(g.close[r, min((j + 3) * step, ROW_MINUTES - 1)])
        for j in np.flatnonzero(bear[r] >= thr):
            top, bot = lo[r, j], hi[r, j + 2]
            price.append((bot + top) / 2)
            half.append((top - bot) / 2)
            direction.append(-1.0)
            row.append(r); valid.append(min((j + 3) * step, ROW_MINUTES - 1))
            ref.append(g.close[r, min((j + 3) * step, ROW_MINUTES - 1)])
    kind = f"fvg_w{w_ticks}_{tf}m" if w_bps is None else f"fvg_w{w_bps:g}bps_{tf}m"
    return (_stack(kind, price, row, valid, ref),
            np.asarray(half, float), np.asarray(direction, float))


def fvg_zones(g: Grid, w_ticks: int, tf: int, product: str) -> LevelSet:
    """Three-bar imbalance midpoints, on `tf`-minute bars, at least w ticks wide."""
    return fvg_zones_directed(g, w_ticks, tf, product)[0]


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


class DegenerateCondition(ValueError):
    """A firing condition that cannot select events, raised instead of returning them.

    `confirmed_break` silently broke THREE registered hypotheses this way - L02's sweep arm,
    L05, and L11 - by firing on every level at the first bar it examined. Each looked healthy
    in the firing-rate table, because a condition that fires on everything produces a large,
    stable, plausible count. The defect is only visible in the entry-MINUTE distribution, and
    nothing was looking there. decisions.md 41.
    """


#: Share of levels that may already be beyond the level when the scan starts. Above this the
#: "first run of k closes beyond" test is answering a question nobody asked: price was
#: already there, so the run is satisfied immediately and `k` becomes an offset rather than a
#: selection. A quarter is generous - the measured failures ran at 100%.
ALREADY_BEYOND_MAX: Final[float] = 0.25


def swing_pivots(g: Grid, lookback: int = 20, tf: int = 5) -> LevelSet:
    """N04/N05's level type: fractal pivots on `tf`-minute bars.

    A pivot is a bar that is the extreme of its +/- `lookback` neighbours. The level becomes
    live on the bar AFTER the pivot completes, which is the first moment it could be traded -
    using the pivot bar itself would look ahead by `lookback` bars.

    REF_PRICE IS THE CLOSE AT valid_from, NOT THE PIVOT PRICE. That is the whole distance
    metric: `verify` matches a placebo on |level - ref|, so setting ref to the level itself
    makes every distance identically ZERO - which is precisely L06's unfixable case, where
    `open_RTH` and `open_CME` sit exactly at the reference price and no arbitrary region is
    comparable (decisions.md 37). A first draft of this constructor had that defect.

    LOOKBACK IS THE DOMINANT SELECTIVITY KNOB, not the penetration threshold that consumes
    it: at lookback 5 there are 286,257 pivots (69/session) and no value of m reaches a
    3-6/session target, while at 20 there are 157,298 (38/session). decisions.md 45.
    """
    step = int(tf)
    sampled = g.close[:, ::step]
    n_bars = sampled.shape[1]
    px, row, valid = [], [], []
    for r in range(g.n):
        c = sampled[r]
        if not np.isfinite(c).all():
            continue
        for j in range(lookback, n_bars - lookback):
            w = c[j - lookback:j + lookback + 1]
            if c[j] == w.max() or c[j] == w.min():
                px.append(c[j])
                row.append(r)
                valid.append(min((j + 1) * step, ROW_MINUTES - 1))
    row_a = np.asarray(row, int)
    valid_a = np.asarray(valid, int)
    ref = g.close[row_a, valid_a]
    return _stack(f"swing_L{lookback}_{tf}m", np.asarray(px, float), row_a, valid_a, ref)


def sweep_reclaim_directed(g: Grid, levels: LevelSet, m_ticks: int, k_bars: int,
                           product: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`sweep_reclaim`, plus the SIDE that was penetrated.

    Same scan and same firing decision - a test pins the two identical - but it also returns
    `direction`: +1 where price swept ABOVE the level, -1 where it swept below, 0 where the
    level never fired. The registered trade is COUNTER to the penetration, so a runner needs
    this and `sweep_reclaim` alone cannot supply it. Mirrors `fvg_zones_directed`, which
    exists for the same reason.
    """
    m = TICK[product] * m_ticks
    fired = np.zeros(levels.price.size, bool)
    minute = np.full(levels.price.size, -1, int)
    direction = np.zeros(levels.price.size, int)
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
                direction[i] = 1 if beyond_up[j] else -1
                break
    return fired, minute, direction


def confirmed_break(g: Grid, levels: LevelSet, k_bars: int, product: str,
                    rth_only: bool = False, *, direction: str) -> tuple[np.ndarray,
                                                                       np.ndarray]:
    """First run of k consecutive closes beyond a level, in ONE named direction.

    `direction` is REQUIRED and must be "up" or "down". It used to fire on a run beyond the
    level in EITHER direction, which is what made it degenerate: applied to a level price
    already sits strictly inside - an opening range, an overnight range, a Bollinger band -
    one of the two sides is satisfied at the first bar and stays satisfied forever. Every
    level then fires at `valid_from + (k - 1)`, `k` shifts the entry rather than choosing
    events, and the high and low of the same session fire at the SAME minute and collapse to
    one (row, minute) key.

    Measured before the fix, MNQ overnight range: entry-minute standard deviation **0.05
    minutes**, 8,234 of 8,234 levels firing, 99.6% of high/low pairs colliding.

    THE PRECONDITION. Price must not already be beyond the level in the tested direction when
    the scan starts. Levels where it is are still scanned - a genuine break can follow - but
    if more than `ALREADY_BEYOND_MAX` of them start beyond, this RAISES. A caller in that
    position is asking about a level price is not approaching, and the honest answer is a
    refusal rather than a number.
    """
    if direction not in ("up", "down"):
        raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")

    fired = np.zeros(levels.price.size, bool)
    minute = np.full(levels.price.size, -1, int)
    starts, already = 0, 0

    for i, (px, r, v) in enumerate(zip(levels.price, levels.row, levels.valid_from)):
        if not np.isfinite(px):
            continue
        lo = max(v, RTH_OPEN) if rth_only else v
        if lo >= ROW_MINUTES - k_bars - 1:
            continue
        path = g.close[r, lo:RTH_EXIT] if rth_only else g.close[r, lo:]
        if path.size == 0:
            continue
        beyond = path > px if direction == "up" else path < px
        starts += 1
        if beyond[0]:
            already += 1
        run = 0
        for j in range(path.size):
            run = run + 1 if beyond[j] else 0
            if run >= k_bars:
                fired[i] = True
                minute[i] = lo + j
                break

    if starts and already / starts > ALREADY_BEYOND_MAX:
        raise DegenerateCondition(
            f"{levels.kind}: price is already beyond the level {already}/{starts} "
            f"({already / starts:.1%}) of the time when the scan starts, above the "
            f"{ALREADY_BEYOND_MAX:.0%} limit. A 'first run of {k_bars} closes beyond' test "
            f"on a level price already sits past does not select events - every level fires "
            f"at valid_from + (k-1) and k becomes an offset. This is the defect that broke "
            f"L02-sweep, L05 and L11; see decisions.md 41. If a break from a standing "
            f"position is genuinely the claim, it needs its own condition and its own "
            f"registration."
        )
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
