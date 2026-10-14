"""D-series family 125 - the dollar rules on other foreign indices (decisions.md 466-467): Yahoo index sessions (open -> close, dated
by local day) against the previous weekday's DX-Y.NYB sign and 6E=F's previous-5-weekday sign. ^AXJO is excluded as an artefact
(stale opens). The discovery scan and the D317-D319 validations were run inline from this module's functions."""

from __future__ import annotations

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d120_week as d120

PREDICTORS = {"dxy_day": lambda: d111.predictor("DX-Y.NYB"), "euro_week": lambda: d120.week("6E=F")}


def index_sessions(sym: str) -> dict:
    z = a22.load(sym, "1d").with_columns((pl.col("ts") + pl.duration(hours=12)).dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5).unique("date", keep="last")
    r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy(); md = np.nanmedian(r); rs = 1.4826 * np.nanmedian(np.abs(r - md))
    return {d: float(x) for d, x in zip(z["date"].to_list(), r) if np.isfinite(x) and abs(x - md) <= 15 * rs}
