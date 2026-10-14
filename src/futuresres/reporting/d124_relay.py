"""D-series family 124 - the plan windows relay into each other, current regime (decisions.md 464)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d8_intraday as d8

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d124_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
COST = {"MGC": 0.8, "MNQ": 0.5, "CL": 0.7, "ZS": 0.7}
#: target -> list of (predictor, lag) ; lag 0 = same date, 1 = previous weekday
PAIRS = {"MGC": [("NKD", 0), ("MNQ", 1), ("MGC_NY", 1), ("DAX", 1), ("CL", 1), ("ZS", 1)],
         "MNQ": [("NKD", 0), ("MGC", 0), ("MGC_NY", 1), ("DAX", 1), ("CL", 1), ("ZS", 1)],
         "CL": [("MNQ", 1), ("MGC", 1), ("MGC_NY", 1), ("DAX", 1), ("ZS", 1)],
         "ZS": [("MNQ", 1), ("MGC", 1), ("MGC_NY", 1), ("DAX", 1), ("CL", 1)]}
_C: dict = {}


def series(name: str) -> dict:
    if name not in _C:
        if name == "MGC_NY":
            D, C, _, K = d8.load("MGC", "ny"); out = {}
            for i, d in enumerate(D):
                c = C[i]; f = np.where(np.isfinite(c))[0]
                if len(f) > 150 and K[i, f[0]] == K[i, f[-1]]:
                    out[d] = float((c[f[-1]] / c[f[0]] - 1) * 1e4)
            _C[name] = out
        else:
            _C[name] = d111.target(name)
    return _C[name]


def rows(p: str, lag: int, tg: str, form: str, lo, hi, med=None):
    P = series(p); Y = series(tg)
    if med is None:
        med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in Y.items():
        if not (lo <= d <= hi):
            continue
        x = P.get(d if lag == 0 else d3.prev_weekday(d))
        if x is None or x == 0 or (form == "strong" and abs(x) <= med):
            continue
        D.append(d); S.append(np.sign(x)); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for tg, lst in PAIRS.items():
        for p, lag in lst:
            for form in ("all", "strong"):
                D, S, Y, med = rows(p, lag, tg, form, *DISC)
                g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - COST[tg]
                _, Sc, Yc, _ = rows(p, lag, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - COST[tg]
                r = {"predictor": p, "lag": lag, "target": tg, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
                print(f"{tg:3} <- {p:6} lag {lag} {form:6}: n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f}{'  CARRIED' if r['carried'] else ''} | 2010-20 "
                      f"{(r['context_net'] or float('nan')):+6.2f} t {(r['context_t'] or float('nan')):+5.2f}", flush=True)
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


if __name__ == "__main__":
    scan()
