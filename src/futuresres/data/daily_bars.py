"""Daily (ohlcv-1d) bars for W04's six markets: per-market held return, carry, front price.

Data only - no signal, no score. decisions.md 73-74 fix every rule here; each is restated where it
is applied.

  BARS. GLBX.MDP3 ohlcv-1d, parent symbology, one file (job GLBX-20261003-SDXCG4PTPA). A bar closes at
       00:00 UTC; measured to track the 18:00-to-16:55 held session at 0.97 daily, 0.98-0.99 over 21
       days (decisions.md 74).
  OUTRIGHTS ONLY. Spreads and strips (symbols with '-' or ':' or spaces) are discarded by grammar.
  SUNDAY BARS DROPPED. The Sunday-evening reopen falls on a Sunday UTC date; dropping it makes Monday's
       return run from Friday's close, Sunday evening included.
  DECADE. The vendor writes one year digit (`CLZ6`). Resolved per instrument_id from its FIRST bar's
       year: the smallest year >= that year ending in the digit. Resolving per bar would make a contract
       listed ten years out (CL lists ~9) collide with the expiring one of the same digit.
  FRONT. Volume crossover, monotonic - `roll.build_calendar`, the repo's rule. The crossover session's
       return is dropped (set to zero, flagged), as `roll.continuous_series` drops it intraday.
  HELD RETURN. Simple return of the contract that was front at the PREVIOUS bar, close to close, same
       contract only. A held contract with no bar today contributes zero and carries its close forward.
  CARRY. C = (F1 - F2) / F2 / years, F1 the front, F2 the highest-volume outright on the same bar among
       contracts expiring after F1; years from contract months (expiry offsets cancel for one product).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

from futuresres.data.parse import MONTH_NUMBER
from futuresres.data.roll import build_calendar

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DAILY_FILE: Final[Path] = ROOT / "data" / "raw_daily" / "glbx-mdp3-20100606-20260912.ohlcv-1d.csv.zst"

#: W04's universe, fixed before the data existed (hypotheses.yaml W04). ES/MES are NOT in it.
MARKETS: Final[tuple[str, ...]] = ("NQ", "GC", "HG", "CL", "ZN", "6E")
MONTHS: Final[str] = "FGHJKMNQUVXZ"


@dataclass(frozen=True)
class MarketDaily:
    root: str
    dates: np.ndarray          # datetime64[D], this market's bar dates (Sundays dropped)
    ret: np.ndarray            # held simple return on each date (0 on the first and on crossover dates)
    carry: np.ndarray          # C on each date (NaN when no F2 traded)
    front_close: np.ndarray    # front contract close (for notional)
    crossover: np.ndarray      # bool, the roll session


def resolve_decade(frame: pl.DataFrame) -> pl.DataFrame:
    """Vendor one-digit-year symbols -> canonical `ROOTMYYYY`, per instrument_id from its first bar."""
    first = (frame.group_by("instrument_id")
                  .agg(pl.col("date").min().dt.year().alias("y0"), pl.col("symbol").first().alias("sym")))
    digit = pl.col("sym").str.slice(-1).cast(pl.Int32)
    first = first.with_columns((pl.col("y0") + ((digit - pl.col("y0") % 10) % 10)).alias("year"))
    first = first.with_columns((pl.col("sym").str.slice(0, pl.col("sym").str.len_chars() - 1)
                                + pl.col("year").cast(pl.Utf8)).alias("contract"))
    return frame.join(first.select("instrument_id", "contract", "year"), on="instrument_id", how="left")


def load_root(root: str, path: Path = DAILY_FILE) -> pl.DataFrame:
    """Outright daily bars for one root: date, contract, close, volume. Sundays dropped."""
    pat = f"^{root}[{MONTHS}][0-9]$"
    f = (pl.scan_csv(path, schema_overrides={"instrument_id": pl.Int64})
           .select("ts_event", "instrument_id", "close", "volume", "symbol")
           .filter(pl.col("symbol").str.contains(pat))
           .with_columns(pl.col("ts_event").str.slice(0, 10).str.to_date().alias("date"))
           .filter(pl.col("date").dt.weekday() != 7)
           .collect())
    return resolve_decade(f).select("date", "contract", "close", "volume")


def _months(contract: str) -> int:
    return int(contract[-4:]) * 12 + MONTH_NUMBER[contract[-5]]


def build_market(root: str, bars: pl.DataFrame) -> MarketDaily:
    vols = (bars.rename({"date": "session"}).select("session", "contract", "volume")
                .sort(["session", "volume"], descending=[False, True]))
    cal = build_calendar(root, vols)
    crossover_dates = cal.dropped_sessions
    dates = sorted(cal.front_by_session)
    closes = {(d, c): px for d, c, px in bars.select("date", "contract", "close").iter_rows()}
    by_date: dict = {}
    for d, c, px, v in bars.select("date", "contract", "close", "volume").iter_rows():
        by_date.setdefault(d, []).append((c, px, v))

    n = len(dates)
    ret = np.zeros(n); carry = np.full(n, np.nan); front_close = np.full(n, np.nan)
    cross = np.zeros(n, bool)
    last_close: dict[str, float] = {}
    prev_front: str | None = None
    for i, d in enumerate(dates):
        front = cal.front_by_session[d]
        if prev_front is not None and prev_front in last_close and (d, prev_front) in closes:
            ret[i] = closes[(d, prev_front)] / last_close[prev_front] - 1.0
        if d in crossover_dates:
            ret[i] = 0.0
            cross[i] = True
        for c, px, _ in by_date[d]:
            last_close[c] = px
        f1 = closes.get((d, front))
        front_close[i] = f1 if f1 is not None else np.nan
        later = [(v, c, px) for c, px, v in by_date[d] if _months(c) > _months(front) and v > 0]
        if f1 is not None and later:
            _, c2, f2 = max(later)
            yrs = (_months(c2) - _months(front)) / 12.0
            carry[i] = (f1 - f2) / f2 / yrs
        prev_front = front
    return MarketDaily(root=root, dates=np.array(dates, dtype="datetime64[D]"), ret=ret, carry=carry,
                       front_close=front_close, crossover=cross)


def load_market(root: str, path: Path = DAILY_FILE) -> MarketDaily:
    return build_market(root, load_root(root, path))


def align(markets: list[MarketDaily]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Union calendar; a market with no bar on a date gets return 0, carry and price carried forward."""
    dates = np.unique(np.concatenate([m.dates for m in markets]))
    out: dict[str, np.ndarray] = {}
    for m in markets:
        idx = np.searchsorted(dates, m.dates)
        r = np.zeros(len(dates)); r[idx] = m.ret
        c = np.full(len(dates), np.nan); c[idx] = m.carry
        p = np.full(len(dates), np.nan); p[idx] = m.front_close
        c = _ffill(c); p = _ffill(p)
        out[f"{m.root}:ret"] = r; out[f"{m.root}:carry"] = c; out[f"{m.root}:price"] = p
    return dates, out


def _ffill(x: np.ndarray) -> np.ndarray:
    """Forward-fill NaNs; leading NaNs stay NaN."""
    ok = np.isfinite(x)
    idx = np.where(ok, np.arange(len(x)), -1)
    np.maximum.accumulate(idx, out=idx)
    y = np.where(idx >= 0, x[np.maximum(idx, 0)], np.nan)
    return y
