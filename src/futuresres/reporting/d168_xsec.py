"""D-series family 168 - cross-sectional relative strength among the six plan markets, current regime (decisions.md 590)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d168_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
SYM = {"MNQ": "NQ=F", "MGC": "GC=F", "NKD": "NKD=F", "DAX": "^GDAXI", "CL": "CL=F", "ZS": "ZS=F"}
TARGETS = d111.TARGETS
_C: dict = {}


def scaled() -> dict:
    if "s" not in _C:
        out = {}
        for k, s in SYM.items():
            P = d111.predictor(s); m = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
            out[k] = {d: v / m for d, v in P.items() if d.weekday() < 5}
        _C["s"] = out
    return _C["s"]


def series(p: str, h: int) -> dict:
    """p = the market itself (its relative strength)."""
    key = (p, h)
    if key not in _C:
        S = scaled(); ds = sorted(set.intersection(*(set(v) for v in S.values())))
        rel = np.array([S[p][d] - np.mean([S[k][d] for k in S]) for d in ds])
        _C[key] = {ds[i]: float(rel[i - h + 1:i + 1].sum()) for i in range(h - 1, len(ds))}
    return _C[key]


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    P = series(p, h); Y = d111.target(tg)
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
    for tg, cost in TARGETS.items():
        for h in (1, 5, 20):
            for form in ("all", "strong"):
                D, S, Y, med = rows(tg, h, tg, form, *DISC)
                g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                _, Sc, Yc, _ = rows(tg, h, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                r = {"target": tg, "predictor": tg, "h": h, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()), "context_t": _t(cc)}
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
                print(f"  {tg:3} rel-strength {h:2}d {form:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 {r['context_net']:+6.2f} "
                      f"t {r['context_t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    carried = [r for r in res if r["carried"]]
    OUT.write_text(json.dumps({"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}, indent=1) + "\n")
    return res


if __name__ == "__main__":
    scan()
