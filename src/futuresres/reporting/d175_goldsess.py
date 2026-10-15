"""D-series family 175 - gold's other sessions against its own long trend, current regime (decisions.md 617)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d175_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
SYM = {"MNQ": "NQ=F", "MGC": "GC=F", "NKD": "NKD=F", "DAX": "^GDAXI", "CL": "CL=F", "ZS": "ZS=F"}
TARGETS = {"gold_asia": 0.8, "gold_ny": 0.8}
import futuresres.reporting.d8_intraday as d8
_T: dict = {}


def target(tg: str) -> dict:
    if tg not in _T:
        D, C, _, K = d8.load("MGC", "asia" if tg == "gold_asia" else "ny"); out = {}
        for i, d in enumerate(D):
            c = C[i]; f = np.where(np.isfinite(c))[0]
            if len(f) > 0.8 * C.shape[1] and K[i, f[0]] == K[i, f[-1]]:
                out[d] = float((c[f[-1]] / c[f[0]] - 1) * 1e4)
        _T[tg] = out
    return _T[tg]
_C: dict = {}


def series(p: str, h: int) -> dict:
    """p = the market itself: the sum of its Yahoo session moves over the h weekdays ending each date."""
    key = (p, h)
    if key not in _C:
        P = d111.predictor(SYM[p]); ds = sorted(d for d in P if d.weekday() < 5); v = np.array([P[d] for d in ds])
        cs = np.r_[0.0, np.cumsum(v)]
        _C[key] = {ds[i]: float(cs[i + 1] - cs[i + 1 - h]) for i in range(h - 1, len(ds))}
    return _C[key]


def group(d):
    return (d.year, d.month)


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    P = series(p, h); Y = target(tg)
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
        for h in (60, 120, 250):
            for form in ("all", "strong"):
                D, S, Y, med = rows("MGC", h, tg, form, *DISC)
                g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                _, Sc, Yc, _ = rows("MGC", h, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                r = {"target": tg, "predictor": "MGC", "h": h, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()), "context_t": _t(cc)}
                G = {}
                for d, x in zip(D, net):
                    G.setdefault(group(d), []).append(x)
                r["t_monthly"] = _t(np.array([np.sum(v) for v in G.values()]))
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0 and r["t_monthly"] > 1.96); res.append(r)
                print(f"  {tg:3} trend {h:3}d {form:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} (monthly {r['t_monthly']:+5.2f}) | 2010-20 {r['context_net']:+6.2f} "
                      f"t {r['context_t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    carried = [r for r in res if r["carried"]]
    OUT.write_text(json.dumps({"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}, indent=1) + "\n")
    return res


if __name__ == "__main__":
    scan()
