"""D-series family 108 - 2-year Treasury shocks into currencies (decisions.md 407)."""

from __future__ import annotations

import datetime as dt

import numpy as np

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d24_shock as d24
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d57_newshock as d57
import futuresres.reporting.d83_fx as d83

DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
COST = {"6E": 0.3, "6J": 0.5, "6B": 0.5, "6A": 0.5}
_C: dict = {}


def _data():
    if not _C:
        _C["sh"] = d24.shocks(d57.predictors(), "ZT"); S = d10.series(); _, T83 = d83.data()
        _C["T"] = {"6E": S["6E"], "6J": S["6J"], "6B": T83["6B"], "6A": T83["6A"]}
    return _C["sh"], _C["T"]


def rows(tg: str, lo: dt.date, hi: dt.date, shock: bool = True):
    sh, T = _data(); D, Y, X = [], [], []
    for d, y in T[tg].items():
        if not (lo <= d <= hi):
            continue
        q = sh.get(d3.prev_weekday(d))
        if q is None or q[1] != shock:
            continue
        D.append(d); Y.append(y); X.append(q[0])
    o = np.argsort(D)
    return np.array(D)[o], np.array(Y)[o], np.array(X)[o]
