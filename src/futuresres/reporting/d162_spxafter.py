"""D-series family 162 - the US index's move after the cash close, just before the NKD, DAX and gold entries (decisions.md 564)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.hd_grid as hd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d162_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
CELLS = (("NKD", "eve"), ("DAX", "post_close"), ("DAX", "asia"), ("MGC", "post_close"), ("MGC", "asia"))
TARGETS = {"NKD": 0.2, "DAX": 0.3, "MGC": 0.8}
_C: dict = {}


def _grid():
    if "g" not in _C:
        D, C = hd.load("spxusd"); _C["g"] = (D, C, {d: i for i, d in enumerate(D)})
    return _C["g"]


def _px(d, minute):
    D, C, idx = _grid()
    return hd.at(C, idx[d], minute) if d in idx else float("nan")


def series(kind: str) -> dict:
    """target date -> bps move."""
    if kind not in _C:
        D, C, idx = _grid(); out = {}
        for d in D:
            if d.weekday() >= 5:
                continue
            if kind == "eve":                     # NKD Tokyo date d: 16:00 -> 19:55 on the calendar day before (Sunday: from Friday 16:00)
                e = d - dt.timedelta(days=1); s = d3.prev_weekday(d) if e.weekday() >= 5 else e
                a, b = _px(s, 960), _px(e, 1195)
            else:                                 # DAX / gold date d: from the previous weekday's 16:00 (or 20:00 ET of the evening before d) to 02:55 on d
                p = d3.prev_weekday(d)
                a = _px(p, 960) if kind == "post_close" else _px(d - dt.timedelta(days=1), 1200)
                b = _px(d, 175)
            if np.isfinite(a) and np.isfinite(b) and a > 0:
                out[d] = float((b / a - 1) * 1e4)
        ds = list(out); _C[kind] = d111._clean(ds, np.array([out[x] for x in ds]))
    return _C[kind]


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    P = series(p); Y = d111.target(tg)
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
    for tg, p in CELLS:
        for form in ("all", "strong"):
            D, S, Y, med = rows(p, 1, tg, form, *DISC); cost = TARGETS[tg]
            g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            _, Sc, Yc, _ = rows(p, 1, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
            r = {"target": tg, "predictor": p, "h": 1, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                 "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()), "context_t": _t(cc)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
            print(f"  {tg:3} <- spx {p:10} {form:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 {r['context_net']:+6.2f} t {r['context_t']:+5.2f}"
                  f"{'  CARRIED' if r['carried'] else ''}", flush=True)
    carried = [r for r in res if r["carried"]]
    OUT.write_text(json.dumps({"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}, indent=1) + "\n")
    return res


if __name__ == "__main__":
    scan()
