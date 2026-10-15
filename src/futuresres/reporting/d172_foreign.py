"""D-series family 172 - pooled foreign-index signals (DAX + NKD windows together), current regime (decisions.md 600)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d136_goldwin as d136
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d172_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
COST = {"DAX": 0.3, "NKD": 0.2}
TARGETS = {"DAX+NKD": 0.25}
EXCL = {"6E=F", "DX-Y.NYB"}
PRED = tuple(p for p in d111.OC + d111.CC + d111.FRED if p not in EXCL and d111.eligible(p, "DAX") and d111.eligible(p, "NKD"))
_SD: dict = {}


def sd(tg):
    if tg not in _SD:
        Y = d111.target(tg); _SD[tg] = float(np.std([v for d, v in Y.items() if DISC[0] <= d <= DISC[1]]))
    return _SD[tg]


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None, split=False):
    """Pooled rows: y in units of each window's SD (net of its own cost in the same units); with split, also each window's label."""
    P = d136.series(p, h)
    if med is None:
        med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
    D, S, Y, L = [], [], [], []
    for w in ("DAX", "NKD"):
        for d, y in d111.target(w).items():
            x = P.get(d3.prev_weekday(d))
            if lo <= d <= hi and x and (form == "all" or abs(x) > med):
                D.append(d); S.append(np.sign(x)); Y.append(y / sd(w) * 100); L.append(w)
    o = np.argsort(D, kind="stable")
    if split:
        return np.array(D)[o], np.array(S)[o], np.array(Y)[o], med, np.array(L)[o]
    return np.array(D)[o], np.array(S)[o], np.array(Y)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []; cs = {w: COST[w] / sd(w) * 100 for w in COST}
    for p in PRED:
        for h in (1, 5):
            for form in ("all", "strong"):
                D, S, Y, med, L = rows(p, h, "DAX+NKD", form, *DISC, split=True)
                c = np.array([cs[w] for w in L]); g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - c
                each = {w: float(net[L == w].mean()) for w in COST}
                _, Sc, Yc, _, Lc = rows(p, h, "DAX+NKD", form, *CONTEXT, med=med, split=True)
                cc = dirn * Sc * Yc - np.array([cs[w] for w in Lc])
                r = {"target": "DAX+NKD", "predictor": p, "h": h, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "net_bps": float(net.mean()), "t": _t(net), "each": each, "context_net": float(cc.mean()), "context_t": _t(cc)}
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0 and all(v > 0 for v in each.values())); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "units": "1/100 of each window's SD", "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res[:12]:
        print(f"  {r['predictor']:9} {r['h']}d {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} (DAX {r['each']['DAX']:+5.2f}, NKD "
              f"{r['each']['NKD']:+5.2f}) | 2010-20 {r['context_net']:+6.2f} t {r['context_t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


if __name__ == "__main__":
    scan()
