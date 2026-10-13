"""D-series family 28 - yield-curve shocks (decisions.md 221-222): a day whose ZT - ZB session spread is beyond 2 sigma; the next
session of ES, NQ, GC, 6E, 6J, HG. Yahoo daily sessions. Recent-period design."""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12
import futuresres.reporting.d3_relay as d3

DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))


def _ser(sym):
    z = a22.load(sym, "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5)
    r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy(); ds = z["date"].to_list(); med = np.median(r); rsd = 1.4826 * np.median(np.abs(r - med))
    return {d: float(x) for d, x in zip(ds, r) if np.isfinite(x) and abs(x - med) <= 15 * rsd}


def shocks():
    ZT, ZB = _ser("ZT=F"), _ser("ZB=F"); ds = sorted(set(ZT) & set(ZB)); cv = np.array([ZT[d] - ZB[d] for d in ds]); out = {}
    for i in range(60, len(ds)):
        sd = cv[i - 60:i].std(ddof=1); out[ds[i]] = (cv[i], abs(cv[i]) > 2 * sd)
    return out


def rows(target, lo, hi, shock=True):
    sh = shocks(); Y = d10.series(); D, R, X = [], [], []
    for d, r in Y[target].items():
        if not (lo <= d <= hi):
            continue
        q = sh.get(d3.prev_weekday(d))
        if q and q[1] == shock:
            D.append(d); R.append(r); X.append(q[0])
    o = np.argsort(D)
    return np.array(D)[o], np.array(R)[o], np.array(X)[o]


def net(c, R, X):
    return (1 if c["rule"] == "follow" else -1) * np.sign(X) * R - d12.COST[c["target"]]
