"""D-series family 127 - slow regime states as every-day direction, current regime (decisions.md 471)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d127_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
TARGETS = d111.TARGETS
OWN = {"MNQ": "NQ=F", "MGC": "GC=F", "NKD": "NKD=F", "DAX": "^GDAXI", "CL": "CL=F", "ZS": "ZS=F"}
STATES = ("vix_high", "vix_inverted", "own_trend", "dollar_trend", "rates_rising")
_C: dict = {}


def closes(sym: str) -> tuple:
    if sym not in _C:
        z = a22.load(sym, "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5).unique("date", keep="last").sort("date")
        _C[sym] = (z["date"].to_list(), z["c"].to_numpy())
    return _C[sym]


def state(name: str, tg: str) -> dict:
    key = (name, tg if name == "own_trend" else "")
    if key in _C:
        return _C[key]
    out = {}
    if name == "vix_high":
        ds, c = closes("^VIX")
        for i in range(250, len(ds)):
            out[ds[i]] = 1 if c[i] > np.nanmedian(c[i - 250:i]) else -1
    elif name == "vix_inverted":
        a = dict(zip(*closes("^VIX"))); b = dict(zip(*closes("^VIX3M")))
        out = {d: (1 if a[d] > b[d] else -1) for d in a if d in b and a[d] == a[d] and b[d] == b[d]}
    else:
        sym, n, inv = {"own_trend": (OWN[tg], 200, 1), "dollar_trend": ("DX-Y.NYB", 50, 1), "rates_rising": ("ZN=F", 20, -1)}[name]
        ds, c = closes(sym)
        for i in range(n, len(ds)):
            if np.isfinite(c[i]):
                out[ds[i]] = inv * (1 if c[i] > np.nanmean(c[i - n:i]) else -1)
    _C[key] = out
    return out


def rows(name: str, tg: str, lo, hi, shift: int = 0, mu: float | None = None):
    S = state(name, tg); Y = d111.target(tg)
    if shift:
        ks = sorted(S); vals = np.roll(np.array([S[k] for k in ks]), shift); S = dict(zip(ks, vals))
    if mu is None:
        mu = float(np.mean([y for d, y in Y.items() if DISC[0] <= d <= DISC[1]]))
    D, X = [], []
    for d, y in Y.items():
        s = S.get(d3.prev_weekday(d))
        if lo <= d <= hi and s:
            D.append(d); X.append(s * (y - mu))
    o = np.argsort(D)
    return np.array(D)[o], np.array(X)[o], mu


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for tg, cost in TARGETS.items():
        for st in STATES:
            D, g, mu = rows(st, tg, *DISC); dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            _, gc, _ = rows(st, tg, *CONTEXT, mu=mu); cc = dirn * gc - cost
            r = {"target": tg, "state": st, "mu": mu, "n": int(len(g)), "dir": "long in state" if dirn == 1 else "short in state", "net_bps": float(net.mean()), "t": _t(net),
                 "context_net": float(cc.mean()), "context_t": _t(cc)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
            print(f"{tg:3} {st:13}: n {r['n']:4} {r['dir']:14} net {r['net_bps']:+6.2f} t {r['t']:+5.2f}{'  CARRIED' if r['carried'] else ''} | 2010-20 {r['context_net']:+6.2f} t {r['context_t']:+5.2f}", flush=True)
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


if __name__ == "__main__":
    scan()
