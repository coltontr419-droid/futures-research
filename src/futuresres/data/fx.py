"""Free USD/JPY spot 1-minute bars from HistData.com (ASCII M1; timestamps EST without DST, UTC-5), downloaded to
data/fx_histdata/usdjpy_{YYYY|YYYYMM}.zip (gitignored). decisions.md 122.

Only the minutes a gotobi test needs are kept (one file at a time - the 2.7 GB machine): the close of the bar ending
at 03:00 and at 09:55 JST, and the OPEN of the first bar at 18:00 New York time (the CME Globex reopen).
"""

from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
FX_DIR = ROOT / "data" / "fx_histdata"
CACHE = ROOT / "data" / "cache" / "usdjpy_gotobi_points.parquet"


def key_points() -> pl.DataFrame:
    """One row per JST date: p300 (03:00 JST), p955 (09:55 JST fix), p_reopen (18:00 ET open before it), weekday."""
    if CACHE.exists():
        return pl.read_parquet(CACHE)
    frames = []
    for f in sorted(FX_DIR.glob("usdjpy_*.zip")):
        z = zipfile.ZipFile(f)
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        d = pl.read_csv(z.read(name), separator=";", has_header=False, new_columns=["ts", "o", "c"], columns=[0, 1, 4])
        d = d.with_columns(pl.col("ts").str.strptime(pl.Datetime, "%Y%m%d %H%M%S").dt.replace_time_zone("Etc/GMT+5")
                           .dt.convert_time_zone("UTC").alias("utc")).drop("ts")
        d = d.with_columns(pl.col("utc").dt.convert_time_zone("Asia/Tokyo").alias("jst"),
                           pl.col("utc").dt.convert_time_zone("America/New_York").alias("et"))
        d = d.with_columns(pl.col("jst").dt.date().alias("jd"),
                           (pl.col("jst").dt.hour().cast(pl.Int32) * 60 + pl.col("jst").dt.minute().cast(pl.Int32)).alias("jm"),
                           (pl.col("et").dt.hour().cast(pl.Int32) * 60 + pl.col("et").dt.minute().cast(pl.Int32)).alias("em"))
        frames.append(d.filter(pl.col("jm").is_in([179, 594]) | (pl.col("em") == 18 * 60)).select("jd", "jm", "em", "o", "c"))
        del d
    df = pl.concat(frames)
    p955 = df.filter(pl.col("jm") == 594).group_by("jd").agg(pl.col("c").last().alias("p955"))
    p300 = df.filter(pl.col("jm") == 179).group_by("jd").agg(pl.col("c").last().alias("p300"))
    reo = df.filter(pl.col("em") == 18 * 60).group_by("jd").agg(pl.col("o").first().alias("p_reopen"))
    out = p955.join(p300, on="jd", how="left").join(reo, on="jd", how="left").sort("jd")
    out = out.with_columns(pl.col("jd").dt.weekday().alias("wd"))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(CACHE)
    return out


def is_gotobi(d: dt.date) -> bool:
    """A business day that is a gotobi day (5, 10, 15, 20, 25, 30), or the last business day before a weekend one
    (the paper's rule; Japanese public holidays are not modelled)."""
    for k in range(0, 3):
        g = d + dt.timedelta(days=k)
        if g.day in (5, 10, 15, 20, 25, 30):
            if k == 0:
                return d.weekday() < 5
            return all((d + dt.timedelta(days=j)).weekday() >= 5 for j in range(1, k + 1))
    return False
