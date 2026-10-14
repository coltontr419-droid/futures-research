"""D-series family 103 - an emerging-currency stress composite into the plan's commodities (decisions.md 396)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12

DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 30))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
CURRENCIES = ("BRL=X", "MXN=X", "ZAR=X", "CLP=X", "COP=X", "INR=X", "KRW=X")
TARGETS = ("ZS", "CL", "GC")
COST = d12.COST
_C: dict = {}


def _nxt(d):
    return d + dt.timedelta(days=1 if d.weekday() < 4 else 3)


def composite() -> dict:
    if "comp" in _C:
        return _C["comp"]
    Z = {}
    for cur in CURRENCIES:
        z = a22.load(cur, "1d").with_columns(pl.col("ts").dt.convert_time_zone("UTC").dt.date().alias("date")).unique("date", keep="last").sort("date")
        ds = z["date"].to_list(); c = z["c"].to_numpy(); ch = np.r_[np.nan, np.diff(np.log(c))]
        for i in range(61, len(ds)):
            sd = np.nanstd(ch[i - 60:i], ddof=1)
            if np.isfinite(ch[i]) and sd > 0 and ds[i].weekday() < 5:
                Z.setdefault(ds[i], []).append(ch[i] / sd)
    days = sorted(d for d, v in Z.items() if len(v) >= 5); comp = np.array([np.mean(Z[d]) for d in days]); out = {}
    for i in range(60, len(days)):
        sd = comp[i - 60:i].std(ddof=1)
        out[days[i]] = (float(comp[i]), bool(abs(comp[i]) > 2 * sd))
    _C["comp"] = out; _C["S"] = d10.series()
    return out


def rows(tg: str, lo: dt.date, hi: dt.date, shock: bool = True):
    sh = composite(); Y = _C["S"][tg]; D, YY, X = [], [], []
    for d, q in sorted(sh.items()):
        if q[1] != shock or not (lo <= d <= hi) or _nxt(d) not in Y:
            continue
        D.append(_nxt(d)); YY.append(Y[_nxt(d)]); X.append(q[0])
    return np.array(D), np.array(YY), np.array(X)
