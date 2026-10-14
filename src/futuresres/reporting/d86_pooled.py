"""D-series family 86 - near-misses that held in both periods, re-read on pooled 2010-2022 (decisions.md 354-355). Each rule's direction
and any 'strong' threshold are fixed by its own 2018-22 discovery; `series(name, lo, hi, placebo=False)` returns (dates, net bps) for
the rule or for its fixed placebo. Validation of D115-D120 uses the same functions on sealed 2023-01 -> 2026-08.
"""

from __future__ import annotations

import collections
import datetime as dt

import numpy as np
import polars as pl

import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d66_gotobi as d66
import futuresres.reporting.d76_etf as d76
import futuresres.reporting.d8_intraday as d8

DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
RULES = ("nkd_morning", "gotobi_pre", "gold_settlement", "ecb_fix_6e", "gold_tlt", "gold_lqd")
_C: dict = {}


def _clean(*vs):
    keep = np.ones(len(vs[0]), bool)
    for v in vs:
        md = np.median(v); rs = 1.4826 * np.median(np.abs(v - md)); keep &= np.abs(v - md) <= 15 * rs
    return keep


def _in(D, lo, hi):
    return np.array([lo <= d <= hi for d in D])


def _nkd(lo, hi, placebo):
    if "nkd" not in _C:
        f = d3.histdata("jpxjpy", {"a": ("Asia/Tokyo", 9, 0), "b": ("Asia/Tokyo", 11, 30), "c": ("Asia/Tokyo", 12, 30), "e": ("Asia/Tokyo", 15, 0)})
        f = f.filter(pl.col("date").dt.weekday() <= 5).drop_nulls()
        x = ((f["b"] / f["a"] - 1) * 1e4).to_numpy(); y = ((f["e"] / f["c"] - 1) * 1e4).to_numpy(); D = f["date"].to_list(); k = _clean(x, y)
        _C["nkd"] = ([d for d, q in zip(D, k) if q], x[k], y[k])
    D, x, y = _C["nkd"]; med = np.median(np.abs(x[_in(D, *DISC)])); sel = _in(D, lo, hi) & (np.abs(x) > med)
    return np.array(D)[sel], np.sign(x[sel]) * y[sel] - 0.2


def _gotobi(lo, hi, placebo):
    D, x = d66.rows("pre", lo, hi, on_gotobi=not placebo)
    return D, -x - 0.5


def _settle(lo, hi, placebo):
    key = "settle_p" if placebo else "settle"
    if key not in _C:
        Dn, Cn, _, Kn = d8.load("MGC", "ny"); idx = [29, 59, 89] if placebo else [89, 119, 149]   # placebo: 12:00 -> 12:30 -> 13:00
        S = []
        for i, d in enumerate(Dn):
            p = Cn[i, idx]; k = Kn[i, idx]
            if np.all(np.isfinite(p)) and len(set(k)) == 1:
                S.append((d, (p[1] / p[0] - 1) * 1e4, (p[2] / p[1] - 1) * 1e4))
        _C[key] = ([s[0] for s in S], np.array([s[1] for s in S]), np.array([s[2] for s in S]))
    D, X, Y = _C[key]; med = np.median(np.abs(X[_in(D, *DISC)])); sel = _in(D, lo, hi) & (np.abs(X) > med)
    return np.array(D)[sel], -np.sign(X[sel]) * Y[sel] - 0.8


def _ecb(lo, hi, placebo):
    key = "ecb_p" if placebo else "ecb"
    if key not in _C:
        TZ = "Europe/Berlin"
        b, c = ((TZ, 15, 15), (TZ, 15, 45)) if placebo else ((TZ, 14, 15), (TZ, 14, 45))
        spec = {"m10": (TZ, 10, 0), "m13": (TZ, 13, 0), "b": b, "c": c}
        f = d3.histdata("eurusd", spec).filter(pl.col("date").dt.weekday() <= 5).drop_nulls()
        y = ((f["c"] / f["b"] - 1) * 1e4 - (f["m13"] / f["m10"] - 1) * 1e4 / 6).to_numpy(); D = f["date"].to_list(); k = _clean(y)
        _C[key] = ([d for d, q in zip(D, k) if q], y[k])
    D, y = _C[key]; sel = _in(D, lo, hi)
    return np.array(D)[sel], y[sel] - 0.3


def _etf(p, lo, hi, placebo):
    D, Y, X = d76.rows(p, "MGC", lo, hi, shock=not placebo)
    return D, np.sign(X) * Y - 0.8


def series(name: str, lo: dt.date, hi: dt.date, placebo: bool = False):
    if name == "nkd_morning":
        return _nkd(lo, hi, placebo)
    if name == "gotobi_pre":
        return _gotobi(lo, hi, placebo)
    if name == "gold_settlement":
        return _settle(lo, hi, placebo)
    if name == "ecb_fix_6e":
        return _ecb(lo, hi, placebo)
    if name == "gold_tlt":
        return _etf("TLT", lo, hi, placebo)
    if name == "gold_lqd":
        return _etf("LQD", lo, hi, placebo)
    raise KeyError(name)


def placebo_kind(name: str) -> str:
    return {"nkd_morning": "morning signs shuffled across the sealed sessions", "gotobi_pre": "the same window on non-gotobi days",
            "gold_settlement": "the same rule one hour earlier (12:00 -> 12:30 predicting 12:30 -> 13:00)",
            "ecb_fix_6e": "the same measure one hour later (15:15 -> 15:45 Frankfurt)",
            "gold_tlt": "the same rule after non-shock days", "gold_lqd": "the same rule after non-shock days"}[name]
