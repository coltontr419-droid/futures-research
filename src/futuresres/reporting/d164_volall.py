"""D-series family 164 - volume-conditioned moves, every owned market into every plan window (decisions.md 569)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3
from futuresres.data.daily_bars import load_market, load_root

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d164_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
DONE = {("NQ", "MNQ"), ("GC", "MGC"), ("CL", "CL"), ("6E", "DAX"), ("6E", "NKD")}
CELLS = tuple((r, t) for r in ("NQ", "GC", "HG", "CL", "ZN", "6E") for t in ("MNQ", "MGC", "NKD", "DAX", "CL", "ZS") if (r, t) not in DONE)
TARGETS = d111.TARGETS
_C: dict = {}
import futuresres.reporting.d163_volume as d163
bars = d163.bars


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    root = p; B, ds = bars(root)
    if med is None:
        med = float(np.median([v[1] for d, v in B.items() if DISC[0] <= d <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in d111.target(tg).items():
        if not (lo <= d <= hi):
            continue
        q = d3.prev_weekday(d)
        if tg == "CL":
            q = d3.prev_weekday(q)
        b = B.get(q)
        if b is None or (form == "high" and b[1] <= med) or (form == "low" and b[1] > med):
            continue
        D.append(d); S.append(np.sign(b[0])); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for root, tg in CELLS:
        for form in ("high", "low"):
            D, S, Y, med = rows(root, 1, tg, form, *DISC); cost = TARGETS[tg]
            g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            _, Sc, Yc, _ = rows(root, 1, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
            r = {"target": tg, "predictor": root, "h": 1, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                 "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()), "context_t": _t(cc)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
            print(f"  {tg:3} <- {root:2} {form:4}-volume n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 {r['context_net']:+6.2f} t {r['context_t']:+5.2f}"
                  f"{'  CARRIED' if r['carried'] else ''}", flush=True)
    carried = [r for r in res if r["carried"]]
    OUT.write_text(json.dumps({"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}, indent=1) + "\n")
    return res


if __name__ == "__main__":
    scan()
