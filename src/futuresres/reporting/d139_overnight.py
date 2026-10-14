"""D-series family 139 - overnight cross-asset moves into MNQ's day, current regime (decisions.md 508)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d8_intraday as d8
import futuresres.reporting.hd_grid as hg

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d139_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
PRED = ("bcousd", "gold", "grxeur", "eurusd", "usdjpy", "audusd")
_C: dict = {}


def predictor(p: str) -> dict:
    if p in _C:
        return _C[p]
    out = {}
    if p == "gold":
        Da, Ca, _, Ka = d8.load("MGC", "asia"); Dl, Cl, _, Kl = d8.load("MGC", "london"); il = {d: i for i, d in enumerate(Dl)}
        for i, d in enumerate(Da):
            j = il.get(d)
            if j is None:
                continue
            fa = np.where(np.isfinite(Ca[i]))[0]
            if not len(fa) or not np.isfinite(Cl[j, 384]) or Ka[i, fa[0]] != Kl[j, 384]:
                continue
            out[d] = float((Cl[j, 384] / Ca[i, fa[0]] - 1) * 1e4)          # 18:00 D-1 -> 09:25 D (London grid offset 384 = 09:24 bar)
    else:
        D, C = hg.load(p); idx = {d: i for i, d in enumerate(D)}
        for i, d in enumerate(D):
            if d.weekday() > 4:
                continue
            if p == "grxeur":
                a = hg.at(C, i, 180, 10)
            else:
                j = idx.get(d3.prev_weekday(d))
                if j is None:
                    continue
                a = hg.at(C, j, 960, 10)
            b = hg.at(C, i, 565, 10)
            if np.isfinite(a) and np.isfinite(b) and a != b:
                out[d] = float((b / a - 1) * 1e4)
    vals = np.array(list(out.values())); md = np.median(vals); rs = 1.4826 * np.median(np.abs(vals - md))
    _C[p] = {d: v for d, v in out.items() if abs(v - md) <= 15 * rs}
    return _C[p]


def rows(p: str, form: str, lo, hi, med=None):
    P = predictor(p); Y = d111.target("MNQ")
    if med is None:
        med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in Y.items():
        x = P.get(d)
        if lo <= d <= hi and x and (form == "all" or abs(x) > med):
            D.append(d); S.append(np.sign(x)); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for p in PRED:
        for form in ("all", "strong"):
            D, S, Y, med = rows(p, form, *DISC)
            g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - 0.5
            _, Sc, Yc, _ = rows(p, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - 0.5
            r = {"predictor": p, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade", "net_bps": float(net.mean()),
                 "t": _t(net), "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
            print(f"MNQ <- {p:7} {form:6}: n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f}{'  CARRIED' if r['carried'] else ''} | 2010-20 "
                  f"{(r['context_net'] or float('nan')):+6.2f} t {(r['context_t'] or float('nan')):+5.2f}", flush=True)
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


if __name__ == "__main__":
    scan()
