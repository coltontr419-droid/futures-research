"""D-series family 149 - currency moves just before NKD's entry, current regime (decisions.md 532)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.hd_grid as hd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d149_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
PAIRS = ("eurusd", "usdjpy", "audusd")
TARGETS = {"NKD": 0.2}
_C: dict = {}


def series(pair: str, kind: str) -> dict:
    """Tokyo date d -> bps move of the pair (evening or 24h) ending 19:55 ET on the calendar day before d."""
    key = (pair, kind)
    if key not in _C:
        D, C = hd.load(pair); idx = {d: i for i, d in enumerate(D)}; out = {}
        for d in D:
            if d.weekday() >= 5:
                continue
            e = d - dt.timedelta(days=1)
            if e not in idx:
                continue
            end = hd.at(C, idx[e], 19 * 60 + 55)
            if kind == "evening" and e.weekday() != 6:
                start = hd.at(C, idx[e], 16 * 60 + 55)
            else:
                p = e - dt.timedelta(days=1)
                while p.weekday() >= 5 or p not in idx:
                    p -= dt.timedelta(days=1)
                    if (e - p).days > 5:
                        break
                if p not in idx:
                    continue
                start = hd.at(C, idx[p], 16 * 60 + 55) if (e.weekday() == 6 or (kind == "24h" and e.weekday() == 6)) else hd.at(C, idx[p], 19 * 60 + 55)
            if np.isfinite(start) and np.isfinite(end) and start > 0:
                out[d] = float((end / start - 1) * 1e4)
        _C[key] = out
    return _C[key]


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    kind = "evening" if h == 0 else "24h"
    P = series(p, kind); Y = d111.target(tg)
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
    for p in PAIRS:
        for h in (0, 1):                       # 0 = evening, 1 = 24 hours
            for form in ("all", "strong"):
                D, S, Y, med = rows(p, h, "NKD", form, *DISC)
                g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - 0.2
                _, Sc, Yc, _ = rows(p, h, "NKD", form, *CONTEXT, med=med); cc = dirn * Sc * Yc - 0.2
                r = {"target": "NKD", "predictor": p, "h": h, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()), "context_t": _t(cc)}
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
                print(f"  NKD <- {p} {'evening' if h == 0 else '24h':7} {form:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 "
                      f"{r['context_net']:+6.2f} t {r['context_t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_carries": round(0.025 * len(res), 1), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


if __name__ == "__main__":
    scan()
