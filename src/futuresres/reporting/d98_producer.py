"""D-series family 98 - producer currencies into their commodities (decisions.md 384): Yahoo close -> close currency shocks (2 sigma,
UTC day) -> the commodity's next-weekday session (family 10). 'Up' = the producer's currency weaker.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12

DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 30))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
PAIRS = {"CLP=X": ("HG", 1), "ZAR=X": ("GC", 1), "RUB=X": ("ZW", 1), "CAD=X": ("CL", 1), "AUDUSD=X": ("GC", -1)}
COST = d12.COST
_C: dict = {}


def _nxt(d):
    return d + dt.timedelta(days=1 if d.weekday() < 4 else 3)


def shocks(cur: str) -> dict:
    if cur not in _C:
        inv = PAIRS[cur][1]
        z = a22.load(cur, "1d").with_columns(pl.col("ts").dt.convert_time_zone("UTC").dt.date().alias("date")).unique("date", keep="last").sort("date")
        ds = z["date"].to_list(); c = z["c"].to_numpy(); ch = inv * np.r_[np.nan, np.diff(np.log(c)) * 1e4]
        _C[cur] = {ds[i]: (float(ch[i]), bool(abs(ch[i]) > 2 * np.nanstd(ch[i - 60:i], ddof=1)))
                   for i in range(61, len(ds)) if np.isfinite(ch[i]) and ds[i].weekday() < 5}
    if "S" not in _C:
        _C["S"] = d10.series()
    return _C[cur]


def rows(cur: str, lo: dt.date, hi: dt.date, shock: bool = True):
    sh = shocks(cur); Y = _C["S"][PAIRS[cur][0]]; D, YY, X = [], [], []
    for d, q in sorted(sh.items()):
        if q[1] != shock or not (lo <= d <= hi) or _nxt(d) not in Y:
            continue
        D.append(_nxt(d)); YY.append(Y[_nxt(d)]); X.append(q[0])
    return np.array(D), np.array(YY), np.array(X)
