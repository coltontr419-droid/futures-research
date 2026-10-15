"""D-series family 154 - the US afternoon after Europe closes into the next European and Tokyo windows, current regime (decisions.md 543)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d8_intraday as d8
import futuresres.reporting.hd_grid as hd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d154_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
PRED = ("mnq", "eurusd", "gold", "brent")
TARGETS = {k: v for k, v in d111.TARGETS.items() if k in ("NKD", "DAX", "MGC")}
_C: dict = {}


def series(p: str, h: int = 1) -> dict:
    if p not in _C:
        out = {}
        if p in ("mnq", "gold"):
            D, C, _, K = d8.load(*(("MNQ", "day") if p == "mnq" else ("MGC", "ny")))
            a, b = (120, 389) if p == "mnq" else (0, 269)
            for i, d in enumerate(D):
                if np.isfinite(C[i, a]) and np.isfinite(C[i, b]) and K[i, a] == K[i, b]:
                    out[d] = float((C[i, b] / C[i, a] - 1) * 1e4)
        else:
            D, C = hd.load({"brent": "bcousd"}.get(p, p))
            for i, d in enumerate(D):
                x0, x1 = hd.at(C, i, 690), hd.at(C, i, 870 if p == "brent" else 959)
                if np.isfinite(x0) and np.isfinite(x1) and x0 > 0:
                    out[d] = float((x1 / x0 - 1) * 1e4)
        ds = [d for d in out if d.weekday() < 5]; _C[p] = d111._clean(ds, np.array([out[d] for d in ds]))
    return _C[p]


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    P = series(p); Y = d111.target(tg)
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
    for p in PRED:
        for tg, cost in TARGETS.items():
            for form in ("all", "strong"):
                D, S, Y, med = rows(p, 1, tg, form, *DISC)
                g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                _, Sc, Yc, _ = rows(p, 1, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                r = {"target": tg, "predictor": p, "h": 1, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else float("nan"), "context_t": _t(cc) if len(cc) > 2 else float("nan")}
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_carries": round(0.025 * len(res), 1), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res[:12]:
        print(f"  {r['target']:3} <- {r['predictor']:6} {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 "
              f"{r['context_net']:+6.2f} t {r['context_t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


if __name__ == "__main__":
    scan()
