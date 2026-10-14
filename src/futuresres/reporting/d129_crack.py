"""D-series family 129 - refining spreads as every-day crude direction, current regime (decisions.md 475)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
_C: dict = {}


def spreads() -> dict:
    if _C:
        return _C
    def cl(s):
        z = a22.load(s, "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5).unique("date", keep="last")
        return dict(zip(z["date"].to_list(), z["c"].to_list()))
    C, H, R = cl("CL=F"), cl("HO=F"), cl("RB=F"); ds = sorted(set(C) & set(H) & set(R))
    P = np.array([[C[d], H[d], R[d]] for d in ds], float); ok = np.all(P > 0, 1); ds = [d for d, k in zip(ds, ok) if k]; P = P[ok]
    ret = np.vstack([np.zeros(3), np.diff(np.log(P), axis=0)]); mad = np.median(np.abs(ret), 0); clean = np.all(np.abs(ret) <= 6 * mad * 1.4826, 1)
    crack = (2 * P[:, 2] * 42 + P[:, 1] * 42 - 3 * P[:, 0]) / 3
    series = {"crack": np.r_[0, np.diff(crack)], "rb_cl": ret[:, 2] - ret[:, 0], "ho_cl": ret[:, 1] - ret[:, 0]}
    for nm, x in series.items():
        for h in (1, 5):
            _C[f"{nm}_{h}d"] = {ds[i]: float(x[i - h + 1:i + 1].sum()) for i in range(h, len(ds)) if clean[i - h + 1:i + 1].all()}
    return _C


def rows(pred: str, form: str, lo, hi, med: float):
    S = spreads()[pred]; Y = d111.target("CL"); D, X, YY = [], [], []
    for d, y in Y.items():
        x = S.get(d3.prev_weekday(d))
        if lo <= d <= hi and x and (form == "all" or abs(x) > med):
            D.append(d); X.append(np.sign(x)); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(X)[o], np.array(YY)[o]
