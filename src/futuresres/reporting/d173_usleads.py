"""D-series family 173 - US index futures lead the foreign afternoon, within the session (decisions.md 602)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

import futuresres.reporting.d8_intraday as d8
import futuresres.reporting.hd_grid as hd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d173_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
ET = ZoneInfo("America/New_York")
#: cell -> (target instrument, tz, target start, target end, predictor pair, predictor start, predictor end)  (local hh, mm)
CELLS = {"NKD<-NQ_tokyo_am": ("jpxjpy", "Asia/Tokyo", (12, 30), (15, 0), "NQ", (9, 0), (11, 30)),
         "DAX<-NQ_frankfurt_am": ("grxeur", "Europe/Berlin", (13, 0), (17, 30), "NQ", (9, 0), (13, 0)),
         "NKD<-gold_tokyo_am": ("jpxjpy", "Asia/Tokyo", (12, 30), (15, 0), "GOLD", (9, 0), (11, 30)),
         "MGC<-NQ_frankfurt_am": ("MGC", "America/New_York", (8, 30), (11, 30), "NQ", (3, 0), (7, 0))}
COST = {"DAX": 0.3, "MGC": 0.8, "NKD": 0.2}
TARGETS = COST
_G: dict = {}


def _g(sym):
    if sym not in _G:
        D, C = hd.load(sym); _G[sym] = (C, {d: i for i, d in enumerate(D)})
    return _G[sym]


def owned_px(kind: str, t: dt.datetime) -> float:
    """NQ from the owned night grid (18:00 -> 09:30 ET, dated by its morning) or the day grid; gold from the owned Asia/London grids."""
    n = t.astimezone(ET); m = n.hour * 60 + n.minute
    if kind == "NQ":
        sess, start, date = ("night", 1080, n.date() if m < 570 else n.date() + dt.timedelta(days=1)) if (m >= 1080 or m < 570) else ("day", 570, n.date())
        D, C, _, K = _own("MNQ", sess)
    else:
        sess, start, date = ("asia", 1080, n.date() if m < 180 else n.date() + dt.timedelta(days=1)) if (m >= 1080 or m < 180) else ("london", 180, n.date())
        D, C, _, K = _own("MGC", sess)
    idx = _G.setdefault(("idx", kind, sess), {d: i for i, d in enumerate(D)})
    while date.weekday() >= 5:
        date += dt.timedelta(days=1)
    i = idx.get(date); j = (m - start) % 1440
    return float(C[i, j]) if i is not None and j < C.shape[1] and np.isfinite(C[i, j]) else float("nan")


def _own(mkt, sess):
    k = ("own", mkt, sess)
    if k not in _G:
        _G[k] = d8.load(mkt, sess)
    return _G[k]


def px(sym: str, t: dt.datetime) -> float:
    if sym in ("NQ", "GOLD"):
        return owned_px(sym, t)
    n = t.astimezone(ET); C, idx = _g(sym); i = idx.get(n.date())
    return hd.at(C, i, n.hour * 60 + n.minute) if i is not None else float("nan")


def mgc_px(t: dt.datetime) -> float:
    if "MGC" not in _G:
        D, C, _, K = d8.load("MGC", "london"); _G["MGC"] = (C, K, {d: i for i, d in enumerate(D)})
    C, K, idx = _G["MGC"]; n = t.astimezone(ET); i = idx.get(n.date())
    if i is None:
        return float("nan")
    j = (n.hour * 60 + n.minute) - 180
    return float(C[i, j]) if 0 <= j < C.shape[1] else float("nan")


def series(cell: str) -> dict:
    """local date -> (predictor bps, target bps)."""
    if cell not in _G:
        tsym, tz, (ts, tm), (te, tn), psym, (ps, pm), (pe, pn) = CELLS[cell]; Z = ZoneInfo(tz); out = {}
        d = dt.date(2010, 1, 4)
        while d <= dt.date(2026, 8, 31):
            if d.weekday() < 5:
                at = lambda h, m: dt.datetime.combine(d, dt.time(h, m), Z)
                a, b = px(psym, at(ps, pm)), px(psym, at(pe, pn))
                if tsym == "MGC":
                    c0, c1 = mgc_px(at(ts, tm)), mgc_px(at(te, tn) - dt.timedelta(minutes=1))
                else:
                    c0, c1 = px(tsym, at(ts, tm)), px(tsym, at(te, tn))
                if all(np.isfinite(v) and v > 0 for v in (a, b, c0, c1)):
                    out[d] = ((b / a - 1) * 1e4, (c1 / c0 - 1) * 1e4)
            d += dt.timedelta(days=1)
        v = np.array([x[1] for x in out.values()]); md = np.median(v); rs = 1.4826 * np.median(np.abs(v - md))
        _G[cell] = {d: x for d, x in out.items() if abs(x[1] - md) <= 15 * rs}
    return _G[cell]


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    S = series(p)
    if med is None:
        med = float(np.median([abs(x[0]) for d, x in S.items() if DISC[0] <= d <= DISC[1]]))
    D, SS, Y = [], [], []
    for d, (x, y) in sorted(S.items()):
        if lo <= d <= hi and x and (form == "all" or abs(x) > med):
            D.append(d); SS.append(np.sign(x)); Y.append(y)
    return np.array(D), np.array(SS), np.array(Y), med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for cell in CELLS:
        tg = cell.split("<-")[0]
        for form in ("all", "strong"):
            D, S, Y, med = rows(cell, 1, tg, form, *DISC); cost = COST[tg]
            g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            _, Sc, Yc, _ = rows(cell, 1, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
            r = {"target": tg, "predictor": cell, "h": 1, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                 "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()), "context_t": _t(cc)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
            print(f"  {cell:12} {form:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 {r['context_net']:+6.2f} t {r['context_t']:+5.2f}"
                  f"{'  CARRIED' if r['carried'] else ''}", flush=True)
    carried = [r for r in res if r["carried"]]
    OUT.write_text(json.dumps({"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}, indent=1) + "\n")
    return res


if __name__ == "__main__":
    scan()
