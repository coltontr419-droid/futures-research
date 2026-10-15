"""D-series family 144 - more candidate account markets, every day, current regime (decisions.md 519)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d136_goldwin as d136
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d144_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
TARGETS = {"YM=F": 1.0, "ZN=F": 0.4, "ZB=F": 0.8, "NG=F": 1.4, "ZC=F": 1.9, "ZW=F": 1.4, "HE=F": 2.0, "LE=F": 1.0, "BTC=F": 3.0}
PRED = d111.OC + d111.CC + d111.FRED
_C: dict = {}


def target(sym: str) -> dict:
    if sym not in _C:
        z = a22.load(sym, "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5).unique("date", keep="last").sort("date")
        _C[sym] = d111._clean(z["date"].to_list(), ((z["c"] / z["o"] - 1) * 1e4).to_numpy())
    return _C[sym]


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    P = d136.series(p, h); Y = target(tg)
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
        for p in PRED:
            if p == tg:
                continue
            for h in (1, 5):
                for form in ("all", "strong"):
                    D, S, Y, med = rows(p, h, tg, form, *DISC)
                    if len(Y) < 100:
                        continue
                    g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                    _, Sc, Yc, _ = rows(p, h, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                    r = {"target": tg, "predictor": p, "h": h, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                         "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
                    r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_carries": round(0.025 * len(res), 1), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in carried:
        print(f"  {r['target']:6} <- {r['predictor']:9} {r['h']}d {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 "
              f"{(r['context_net'] or float('nan')):+6.2f} t {(r['context_t'] or float('nan')):+5.2f}", flush=True)
    return out


if __name__ == "__main__":
    scan()
