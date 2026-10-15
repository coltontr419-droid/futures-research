"""D-series family 140 - spreads between markets as every-day predictors, current regime (decisions.md 510)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d140_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
SPREADS = {"curve": ("ZN=F", "ZT=F"), "hyg_tlt": ("HYG", "TLT"), "lqd_tlt": ("LQD", "TLT"), "nq_es": ("NQ=F", "ES=F"),
           "rty_es": ("RTY=F", "ES=F"), "smh_nq": ("SMH", "NQ=F")}
TARGETS = d111.TARGETS
_C: dict = {}


def series(name: str, h: int) -> dict:
    key = (name, h)
    if key not in _C:
        a, b = (d111.predictor(x) for x in SPREADS[name])
        S = {d: a[d] - b[d] for d in a if d in b}
        ds = sorted(S); r = np.array([S[d] for d in ds])
        _C[key] = {ds[i]: float(r[i - h + 1:i + 1].sum()) for i in range(h - 1, len(ds))}
    return _C[key]


def rows(name: str, h: int, tg: str, form: str, lo, hi, med=None):
    P = series(name, h); Y = d111.target(tg)
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
    for name in SPREADS:
        for h in (1, 5):
            for tg, cost in TARGETS.items():
                for form in ("all", "strong"):
                    D, S, Y, med = rows(name, h, tg, form, *DISC)
                    if len(Y) < 100:
                        continue
                    g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                    _, Sc, Yc, _ = rows(name, h, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                    r = {"spread": name, "h": h, "target": tg, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                         "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
                    r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_carries": round(0.025 * len(res), 1), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in carried:
        print(f"  {r['target']:3} <- {r['spread']:8} {r['h']}d {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 "
              f"{(r['context_net'] or float('nan')):+6.2f} t {(r['context_t'] or float('nan')):+5.2f}", flush=True)
    return out


if __name__ == "__main__":
    scan()
