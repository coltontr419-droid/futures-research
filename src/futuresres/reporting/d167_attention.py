"""D-series family 167 - public attention (Wikipedia pageviews) as every-day predictors, current regime (decisions.md 588)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "data" / "cache" / "wiki" / "pageviews.json"
OUT = ROOT / "reports" / "d167_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2016, 1, 1), dt.date(2020, 12, 31))
TARGETS = d111.TARGETS
LAG = {"MNQ": 1, "DAX": 2, "MGC": 2, "NKD": 2, "CL": 2, "ZS": 2}
_C: dict = {}


def series(p: str, h: int) -> dict:
    key = (p, h)
    if key not in _C:
        raw = json.loads(SRC.read_text())[p]
        ds = sorted(dt.datetime.strptime(k, "%Y%m%d").date() for k in raw); v = np.log(np.array([max(raw[d.strftime("%Y%m%d")], 1) for d in ds], float))
        shock = {ds[i]: float(v[i] - np.log(np.mean(np.exp(v[i - 20:i])))) for i in range(20, len(ds))}
        if h == 1:
            _C[key] = shock
        else:
            wd = sorted(d for d in shock if d.weekday() < 5); x = np.array([shock[d] for d in wd])
            _C[key] = {wd[i]: float(x[i - 4:i + 1].mean()) for i in range(4, len(wd))}
    return _C[key]


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    P = series(p, h); Y = d111.target(tg)
    if med is None:
        med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in Y.items():
        q = d
        for _ in range(LAG[tg]):
            q = d3.prev_weekday(q)
        x = P.get(q)
        if lo <= d <= hi and x and (form == "all" or abs(x) > med):
            D.append(d); S.append(np.sign(x)); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for p in json.loads(SRC.read_text()):
        for h in (1, 5):
            for tg, cost in TARGETS.items():
                for form in ("all", "strong"):
                    D, S, Y, med = rows(p, h, tg, form, *DISC)
                    g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                    _, Sc, Yc, _ = rows(p, h, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                    r = {"target": tg, "predictor": p, "h": h, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                         "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()), "context_t": _t(cc)}
                    r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_carries": round(0.025 * len(res), 1), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in carried:
        print(f"  {r['target']:3} <- {r['predictor']:22} {r['h']}d {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2016-20 "
              f"{r['context_net']:+6.2f} t {r['context_t']:+5.2f}", flush=True)
    return out


if __name__ == "__main__":
    scan()
