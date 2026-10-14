"""D-series family 136 - gold's other windows as every-day targets, current regime (decisions.md 499)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d124_relay as d124
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d136_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
PRED = tuple(p for p in d111.OC + d111.CC + d111.FX + d111.FRED if p not in ("GC=F", "GDX", "SOYB"))
_C: dict = {}


def target(name: str) -> dict:
    if name not in _C:
        _C[name] = d124.series("MGC_NY") if name == "gold_ny" else d111.predictor("GC=F")
    return _C[name]


def series(p: str, h: int) -> dict:
    key = (p, h)
    if key not in _C:
        S = d111.predictor(p)
        if h == 1:
            _C[key] = S
        else:
            ds = sorted(S); r = np.array([S[d] for d in ds]); _C[key] = {ds[i]: float(r[i - h + 1:i + 1].sum()) for i in range(h - 1, len(ds))}
    return _C[key]


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
    for tg in ("gold_ny", "gold_session"):
        for p in PRED:
            if tg == "gold_session" and p in d111.FX:
                continue
            for h in (1, 5):
                for form in ("all", "strong"):
                    D, S, Y, med = rows(p, h, tg, form, *DISC)
                    if len(Y) < 100:
                        continue
                    g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - 0.8
                    _, Sc, Yc, _ = rows(p, h, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - 0.8
                    r = {"target": tg, "predictor": p, "h": h, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                         "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
                    r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_carries": round(0.025 * len(res), 1), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in carried:
        print(f"  {r['target']:12} <- {r['predictor']:9} {r['h']}d {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 "
              f"{(r['context_net'] or float('nan')):+6.2f} t {(r['context_t'] or float('nan')):+5.2f}", flush=True)
    return out


if __name__ == "__main__":
    scan()
