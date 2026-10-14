"""D-series family 122 - Asia overnight into the European and US windows, current regime (decisions.md 458)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.hd_grid as hg

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d122_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
TARGETS = {"MGC": 0.8, "DAX": 0.3, "MNQ": 0.5}
PRED = ("NKD window", "HSI morning", "usdjpy", "audusd", "eurusd")
_C: dict = {}


def predictor(p: str) -> dict:
    if p in _C:
        return _C[p]
    if p == "NKD window":
        out = d111.target("NKD")
    elif p == "HSI morning":
        f = d3.histdata("hkxhkd", {"a": ("Asia/Hong_Kong", 9, 30), "b": ("Asia/Hong_Kong", 12, 0)}).drop_nulls()
        out = {d: float((b / a - 1) * 1e4) for d, a, b in zip(f["date"].to_list(), f["a"].to_numpy(), f["b"].to_numpy()) if a and b}
    else:
        D, C = hg.load(p); idx = {d: i for i, d in enumerate(D)}; out = {}
        for i, d in enumerate(D):
            if d.weekday() > 4:
                continue
            prev = d - dt.timedelta(days=3 if d.weekday() == 0 else 1)
            j = idx.get(prev)
            if j is None:
                continue
            a = hg.at(C, j, 1080, back=10); b = hg.at(C, i, 175)
            if np.isfinite(a) and np.isfinite(b):
                out[d] = float((b / a - 1) * 1e4)
    vals = np.array(list(out.values())); md = np.median(vals); rs = 1.4826 * np.median(np.abs(vals - md))
    out = {d: v for d, v in out.items() if abs(v - md) <= 15 * rs}
    _C[p] = out
    return out


def rows(p: str, tg: str, form: str, lo, hi, med=None):
    P = predictor(p); Y = d111.target(tg)
    if med is None:
        med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in Y.items():
        x = P.get(d)
        if not (lo <= d <= hi) or x is None or x == 0 or (form == "strong" and abs(x) <= med):
            continue
        D.append(d); S.append(np.sign(x)); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for p in PRED:
        for tg, cost in TARGETS.items():
            for form in ("all", "strong"):
                D, S, Y, med = rows(p, tg, form, *DISC)
                if len(Y) < 100:
                    continue
                g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                _, Sc, Yc, _ = rows(p, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                r = {"predictor": p, "target": tg, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
                print(f"{tg} <- {p:11} {form:6}: n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f}{'  CARRIED' if r['carried'] else ''} | 2010-20 "
                      f"{(r['context_net'] or float('nan')):+6.2f} t {(r['context_t'] or float('nan')):+5.2f}", flush=True)
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


if __name__ == "__main__":
    scan()
