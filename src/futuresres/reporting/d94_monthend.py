"""D-series family 94 - the month-end London fix and equity-hedge rebalancing (decisions.md 373): on the last London business day,
6E/6B/6J (pooled per day) 15:30 -> 16:00 ('pre') or 16:00 -> 16:30 ('post') London, signed by the S&P's month so far.
"""

from __future__ import annotations

import collections
import datetime as dt

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d41_fix as d41

DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
FUTS = ("6E", "6B", "6J")
_C: dict = {}


def _load(lo, hi):
    key = (lo, hi)
    if key not in _C:
        z = a22.load("ES=F", "1d").with_columns(pl.col("ts").dt.date().alias("date")).unique("date", keep="last").sort("date")
        es = dict(zip(z["date"].to_list(), z["c"].to_list()))
        data = {}
        for f in FUTS:
            for w, (pre, tgt) in (("pre", ((930, 960), (930, 960))), ("post", ((930, 960), (960, 990)))):
                D, X, Y = d41.rows(f, lo, hi, pre=pre, tgt=tgt); data[(f, w)] = dict(zip(D, Y))
        _C[key] = (es, data)
    return _C[key]


def rows(window: str, lo: dt.date, hi: dt.date, which: int = -1):
    """(month-end dates, foreign-currency move signed by the S&P month: + = dollar weaker after equity gains). which=-1 the last
    business day; -2 the second-last (the placebo)."""
    es, data = _load(lo, hi); esd = sorted(es)
    alld = sorted(set(data[("6E", window)]))
    bym = collections.defaultdict(list)
    for d in alld:
        bym[(d.year, d.month)].append(d)
    days = sorted(v[which] for v in bym.values() if len(v) >= 2)
    D, out = [], []
    for d in days:
        prev = [x for x in esd if x < dt.date(d.year, d.month, 1)]; cur = [x for x in esd if x < d]
        if not prev or not cur:
            continue
        s = np.sign(es[cur[-1]] / es[prev[-1]] - 1)
        v = [data[(f, window)][d] for f in FUTS if d in data[(f, window)]]
        if s != 0 and v:
            D.append(d); out.append(s * np.mean(v))
    return np.array(D), np.array(out)
