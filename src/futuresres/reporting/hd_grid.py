"""A day x 1440-minute close grid (New York time) from HistData M1 bars on the corrected clock (decisions.md 140): bars are stamped
at their open in New York local time, so a minute m's value is the close of the bar stamped m. Cached per symbol.

    python -m futuresres.reporting.hd_grid --build bcousd
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
FX = ROOT / "data" / "fx_histdata"
CACHE = ROOT / "data" / "cache"


def build(sym: str) -> None:
    rows = {}
    for f in sorted(FX.glob(f"{sym}_*.zip")):
        z = zipfile.ZipFile(f); n = [x for x in z.namelist() if x.lower().endswith(".csv")][0]
        d = pl.read_csv(z.read(n), separator=";", has_header=False, new_columns=["ts", "o", "h", "l", "c", "v"], columns=[0, 1, 2, 3, 4, 5])
        d = d.with_columns(pl.col("ts").str.strptime(pl.Datetime, "%Y%m%d %H%M%S").alias("t"))
        d = d.with_columns(pl.col("t").dt.date().alias("date"), (pl.col("t").dt.hour().cast(pl.Int32) * 60 + pl.col("t").dt.minute().cast(pl.Int32)).alias("m"))
        for (date,), g in d.group_by(["date"]):
            r = rows.setdefault(date, np.full(1440, np.nan, np.float32))
            r[g["m"].to_numpy()] = g["c"].to_numpy()
        del d
    days = np.array(sorted(rows)); C = np.stack([rows[x] for x in days])
    np.savez(CACHE / f"hd_{sym}.npz", days=days.astype("datetime64[D]"), C=C)
    print(sym, len(days), "days;", f"{np.isfinite(C).mean():.0%} of minutes filled", flush=True)


def load(sym: str):
    z = np.load(CACHE / f"hd_{sym}.npz")
    return z["days"].astype("datetime64[D]").astype(object), z["C"]


def at(C, i: int, minute: int, back: int = 5) -> float:
    """The last close at or before `minute` (within `back` minutes) on row i, NaN if none."""
    for k in range(back + 1):
        if minute - k >= 0 and np.isfinite(C[i, minute - k]):
            return float(C[i, minute - k])
    return float("nan")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--build")
    a = ap.parse_args(argv)
    if a.build:
        build(a.build)
    return 0


if __name__ == "__main__":
    sys.exit(main())
