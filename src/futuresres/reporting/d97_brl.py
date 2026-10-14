"""D-series family 97 - the Brazilian real into soybeans and corn (decisions.md 380): USD/BRL (Yahoo BRL=X, close -> close, UTC day)
beyond 2 sigma -> ZS / ZC next-weekday sessions (family 10). Recent-period design.
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
COST = d12.COST
_C: dict = {}


def shocks() -> dict:
    if "sh" not in _C:
        z = a22.load("BRL=X", "1d").with_columns(pl.col("ts").dt.convert_time_zone("UTC").dt.date().alias("date")).unique("date", keep="last").sort("date")
        ds = z["date"].to_list(); c = z["c"].to_numpy(); ch = np.r_[np.nan, np.diff(np.log(c)) * 1e4]
        _C["sh"] = {ds[i]: (float(ch[i]), bool(abs(ch[i]) > 2 * np.nanstd(ch[i - 60:i], ddof=1)))
                    for i in range(61, len(ds)) if np.isfinite(ch[i]) and ds[i].weekday() < 5}
        _C["S"] = d10.series()
    return _C["sh"]


def _nxt(d):
    return d + dt.timedelta(days=1 if d.weekday() < 4 else 3)


def rows(tg: str, lo: dt.date, hi: dt.date, shock: bool = True):
    """(target dates, target bps, USD/BRL change) for shock (or non-shock) days in [lo, hi] (dated by the BRL day)."""
    sh = shocks(); Y = _C["S"][tg]; D, YY, X = [], [], []
    for d, q in sorted(sh.items()):
        if q[1] != shock or not (lo <= d <= hi) or _nxt(d) not in Y:
            continue
        D.append(_nxt(d)); YY.append(Y[_nxt(d)]); X.append(q[0])
    return np.array(D), np.array(YY), np.array(X)
