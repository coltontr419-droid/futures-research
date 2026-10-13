"""A28 - engineering a trade around the London continuation in gold and silver (decisions.md 197-198). DESIGN on 2010-2017 only:
the entry hour (03:00 ... 10:00, exit 11:30 New York) and the day filter (every day / |overnight move| above its 2010-17 median /
top fifth) chosen by one criterion - the largest t of the direction-signed, drift-removed return; then FROZEN and evaluated on
2018-2026 (raw trade and a standalone account). A COMPUTATION; the gold and silver effects were already seen on 2018-26 (§151,
§154, §163, §196), so the evaluation is not blind - only the entry hour and the day filter are new.

    python -m futuresres.reporting.a28_metals_design --design
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.a26_silver as a26
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d7_london as d7
import futuresres.reporting.d8_intraday as d8

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a28_design.json"
DESIGN = (dt.date(2010, 1, 1), dt.date(2017, 12, 31))
EVAL = (dt.date(2018, 1, 1), dt.date(2026, 8, 31))
STARTS = tuple(range(0, 8))                      # hours after 03:00
FILTERS = ("all", "half", "fifth")


def gold_rows():
    days, C, V, K = d8.load("MGC", "london"); pre = d3.series()["MGC_pre"]
    D, X, P = [], [], []
    for i, d in enumerate(days):
        c, k = C[i], K[i]
        if d in pre and np.isfinite(c).all() and (k == k[0]).all():
            D.append(d); X.append(pre[d]); P.append(c)
    return np.array(D), np.array(X), np.array(P)


def silver_rows():
    _, pre = d7.series("xagusd"); D, X, P = [], [], []
    for era in ("pre", "post"):
        z = np.load(a26.CACHE / f"a26_SIL_{era}.npz")
        for d, c in zip(z["d"].astype("datetime64[D]").astype(object), z["c"]):
            if d in pre:
                D.append(d); X.append(pre[d]); P.append(1.0 + c.astype(np.float64))     # relative path -> a price-like path
    o = np.argsort(D)
    return np.array(D)[o], np.array(X)[o], np.array(P)[o]


def leg(P, start_h):
    """Return (bps) from the start hour to 11:30 for each day."""
    j0 = start_h * 60 - 1 if start_h > 0 else 0
    return (P[:, -1] / P[:, j0] - 1) * 1e4


def design(metal: str) -> dict:
    D, X, P = gold_rows() if metal == "gold" else silver_rows()
    m = np.array([DESIGN[0] <= d <= DESIGN[1] for d in D])
    Xd, Pd = X[m], P[m]
    q50, q80 = float(np.quantile(np.abs(Xd), 0.5)), float(np.quantile(np.abs(Xd), 0.8))
    best = None; grid = []
    for h in STARTS:
        r = leg(Pd, h); r = r - r.mean()
        for f in FILTERS:
            sel = np.ones(len(Xd), bool) if f == "all" else np.abs(Xd) > (q50 if f == "half" else q80)
            z = np.sign(Xd[sel]) * r[sel]; t = float(z.mean() / (z.std(ddof=1) / math.sqrt(len(z))))
            grid.append({"start": f"{3 + h:02d}:00", "filter": f, "n": int(sel.sum()), "bps": float(z.mean()), "t": t})
            if best is None or t > best["t"]:
                best = {"start_h": h, "start": f"{3 + h:02d}:00", "filter": f, "t": t, "bps": float(z.mean()), "n": int(sel.sum())}
    best.update({"q50": q50, "q80": q80, "design_days": int(m.sum())})
    return {"best": best, "grid": grid}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--design", action="store_true")
    a = ap.parse_args(argv)
    if a.design:
        out = {}
        for metal in ("gold", "silver"):
            r = design(metal); out[metal] = r; b = r["best"]
            print(f"{metal}: {b['design_days']} design days (2010-17). CHOSEN: enter {b['start']}, filter {b['filter']} -> {b['bps']:+.2f} bps beyond drift, "
                  f"t {b['t']:+.2f}, n {b['n']}", flush=True)
            for g in sorted(r["grid"], key=lambda g: -g["t"])[:5]:
                print(f"    {g['start']} {g['filter']:5} n {g['n']:4} {g['bps']:+6.2f} bps t {g['t']:+5.2f}", flush=True)
        OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
