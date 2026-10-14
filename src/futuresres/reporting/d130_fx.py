"""D-series family 130 - currency windows as candidate new markets, current regime (decisions.md 477)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d83_fx as d83

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d130_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
PAIRS = {"6E": ("eurusd", 1), "6J": ("usdjpy", -1), "6B": ("gbpusd", 1), "6A": ("audusd", 1), "6C": ("usdcad", -1), "6S": ("usdchf", -1)}
COST = 0.5
_C: dict = {}


def window(fut: str) -> dict:
    if fut not in _C:
        sym, sg = PAIRS[fut]
        f = d3.histdata(sym, {"a": ("Europe/London", 8, 0), "b": ("Europe/London", 16, 0)}).filter(pl.col("date").dt.weekday() <= 5).drop_nulls()
        r = sg * ((f["b"] / f["a"] - 1) * 1e4).to_numpy(); md = np.median(r); rs = 1.4826 * np.median(np.abs(r - md))
        _C[fut] = {d: float(x) for d, x in zip(f["date"].to_list(), r) if abs(x - md) <= 15 * rs}
    return _C[fut]


def _sum(S: dict, h: int) -> dict:
    ds = sorted(S); r = np.array([S[d] for d in ds])
    return {ds[i]: float(r[i - h + 1:i + 1].sum()) for i in range(h - 1, len(ds))}


def predictor(name: str, fut: str) -> dict:
    key = (name, fut if name.startswith("own") else "")
    if key in _C:
        return _C[key]
    if name.startswith("own"):
        base = d10.series()[fut] if fut in ("6E", "6J") else d83.data()[1][fut]
    else:
        base = d111.predictor({"dxy": "DX-Y.NYB", "es": "ES=F", "zn": "ZN=F", "gc": "GC=F"}[name.split("_")[0]])
    out = _sum(base, 5 if name.endswith("5d") else 1)
    _C[key] = out
    return out


PRED = ("own_1d", "own_5d", "dxy_1d", "dxy_5d", "es_1d", "es_5d", "zn_1d", "zn_5d", "gc_1d")


def rows(p: str, fut: str, form: str, lo, hi, med=None):
    P = predictor(p, fut); Y = window(fut)
    if med is None:
        med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in Y.items():
        x = P.get(d3.prev_weekday(d))
        if lo <= d <= hi and x and (form == "all" or abs(x) > med):
            D.append(d); S.append(np.sign(x)); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for fut in PAIRS:
        for p in PRED:
            for form in ("all", "strong"):
                D, S, Y, med = rows(p, fut, form, *DISC)
                if len(Y) < 100:
                    continue
                g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - COST
                _, Sc, Yc, _ = rows(p, fut, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - COST
                r = {"target": fut, "predictor": p, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res[:12]:
        print(f"  {r['target']} <- {r['predictor']:7} {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 "
              f"{(r['context_net'] or float('nan')):+6.2f} t {(r['context_t'] or float('nan')):+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


if __name__ == "__main__":
    scan()
