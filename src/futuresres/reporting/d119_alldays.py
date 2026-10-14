"""D-series family 119 - yesterday's direction across markets, every day, on the current regime (decisions.md 443)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d119_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
PRED = d111.OC + d111.CC + d111.FX + d111.FRED
TARGETS = d111.TARGETS


def rows(p: str, tg: str, form: str, lo, hi, med=None):
    P = d111.predictor(p); Y = d111.target(tg)
    if med is None:
        med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in Y.items():
        if not (lo <= d <= hi):
            continue
        x = P.get(d3.prev_weekday(d))
        if x is None or x == 0 or (form == "strong" and abs(x) <= med):
            continue
        D.append(d); S.append(np.sign(x)); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for p in PRED:
        for tg, cost in TARGETS.items():
            if not d111.eligible(p, tg):
                continue
            for form in ("all", "strong"):
                D, S, Y, med = rows(p, tg, form, *DISC)
                if len(Y) < 100:
                    continue
                g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                _, Sc, Yc, _ = rows(p, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                r = {"predictor": p, "target": tg, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_carries": round(0.025 * len(res), 1), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in carried:
        print(f"  {r['target']:3} <- {r['predictor']:9} {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 "
              f"{(r['context_net'] or float('nan')):+6.2f} t {(r['context_t'] or float('nan')):+5.2f}", flush=True)
    return out


if __name__ == "__main__":
    scan()
