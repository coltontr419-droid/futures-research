"""Free HistData 1-minute bars (EUR/USD, GBP/USD; S&P 500, Euro Stoxx 50, FTSE 100 index CFDs) reduced to what the
month-end-fix test needs, one file at a time (the 2.7 GB machine). decisions.md 127.

HistData ASCII M1 timestamps are EST without DST (UTC-5). Kept per pair: the price at 15:00 and 16:00 London time
(close of the bar ending then) on every date; per index: the last price of each New York trading date (a daily close).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
FX_DIR = ROOT / "data" / "fx_histdata"
CACHE = ROOT / "data" / "cache"


def _read(f: Path) -> pl.DataFrame:
    z = zipfile.ZipFile(f)
    name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    d = pl.read_csv(z.read(name), separator=";", has_header=False, new_columns=["ts", "c"], columns=[0, 4])
    return d.with_columns(pl.col("ts").str.strptime(pl.Datetime, "%Y%m%d %H%M%S").dt.replace_time_zone("Etc/GMT+5")
                          .dt.convert_time_zone("UTC").alias("utc")).drop("ts")


def fix_points(pair: str) -> pl.DataFrame:
    """date (London), p1500, p1600 for one FX pair."""
    out = CACHE / f"fixpts_{pair}.parquet"
    if out.exists():
        return pl.read_parquet(out)
    parts = []
    for f in sorted(FX_DIR.glob(f"{pair}_*.zip")):
        d = _read(f).with_columns(pl.col("utc").dt.convert_time_zone("Europe/London").alias("ldn"))
        d = d.with_columns(pl.col("ldn").dt.date().alias("date"),
                           (pl.col("ldn").dt.hour().cast(pl.Int32) * 60 + pl.col("ldn").dt.minute().cast(pl.Int32)).alias("m"))
        parts.append(d.filter(pl.col("m").is_in([899, 959])).select("date", "m", "c"))
        del d
    df = pl.concat(parts)
    res = (df.group_by(["date", "m"]).agg(pl.col("c").last()).pivot(on="m", index="date", values="c")
             .rename({"899": "p1500", "959": "p1600"}).sort("date"))
    CACHE.mkdir(parents=True, exist_ok=True); res.write_parquet(out)
    return res


def daily_close(index: str) -> pl.DataFrame:
    """date (New York), close (the last 1-minute close of the date)."""
    out = CACHE / f"daily_{index}.parquet"
    if out.exists():
        return pl.read_parquet(out)
    parts = []
    for f in sorted(FX_DIR.glob(f"{index}_*.zip")):
        d = _read(f).with_columns(pl.col("utc").dt.convert_time_zone("America/New_York").dt.date().alias("date"))
        parts.append(d.sort("utc").group_by("date").agg(pl.col("c").last().alias("close")))
        del d
    res = pl.concat(parts).group_by("date").agg(pl.col("close").last()).sort("date")
    CACHE.mkdir(parents=True, exist_ok=True); res.write_parquet(out)
    return res


def hourly_utc(pair: str) -> pl.DataFrame:
    """Price at every whole UTC hour (close of the bar ending then): columns utc (datetime, UTC, on the hour), c.
    decisions.md 128."""
    out = CACHE / f"hourly_{pair}.parquet"
    if out.exists():
        return pl.read_parquet(out)
    parts = []
    for f in sorted(FX_DIR.glob(f"{pair}_*.zip")):
        d = _read(f)
        d = d.filter(pl.col("utc").dt.minute() == 59).with_columns((pl.col("utc") + pl.duration(minutes=1)).alias("utc"))
        parts.append(d.select("utc", "c"))
    res = pl.concat(parts).unique("utc", keep="last").sort("utc")
    CACHE.mkdir(parents=True, exist_ok=True); res.write_parquet(out)
    return res
