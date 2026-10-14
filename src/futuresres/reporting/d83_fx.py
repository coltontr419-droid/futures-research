"""D-series family 83 - shocks into the currencies not yet targeted (decisions.md 347): ES, NQ, CL, GC, HG, ZN shocks (family 24) ->
6A, 6B, 6C, 6S next sessions (Yahoo daily open -> settlement). Recent-period design.

    python -m futuresres.reporting.d83_fx --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d24_shock as d24
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d83_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
EARLY = (dt.date(2010, 1, 1), dt.date(2017, 12, 31))
PRED = ("ES", "NQ", "CL", "GC", "HG", "ZN")
TARGETS = ("6A", "6B", "6C", "6S")
COST = 0.5
_C: dict = {}


def _ser(sym: str) -> dict:
    z = a22.load(sym, "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5)
    r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy(); ds = z["date"].to_list()
    md = np.nanmedian(r); rs = 1.4826 * np.nanmedian(np.abs(r - md))
    return {d: float(x) for d, x in zip(ds, r) if np.isfinite(x) and abs(x - md) <= 15 * rs}


def data():
    if not _C:
        _C["S"] = d10.series(); _C["T"] = {k: _ser(k + "=F") for k in TARGETS}
    return _C["S"], _C["T"]


def rows(p: str, tg: str, lo: dt.date, hi: dt.date, shock: bool = True):
    S, T = data(); sh = d24.shocks(S, p); D, Y, X = [], [], []
    for d, y in T[tg].items():
        if not (lo <= d <= hi):
            continue
        q = sh.get(d3.prev_weekday(d))
        if q is None or q[1] != shock:
            continue
        D.append(d); Y.append(y); X.append(q[0])
    o = np.argsort(D)
    return np.array(D)[o], np.array(Y)[o], np.array(X)[o]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for p in PRED:
        for tg in TARGETS:
            D, Y, X = rows(p, tg, *DISC); assert D.max() <= DISC[1], "discovery read sealed data"
            g = np.sign(X) * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - COST
            _, Ye, Xe = rows(p, tg, *EARLY); ee = dirn * np.sign(Xe) * Ye - COST
            r = {"predictor": p, "target": tg, "n": int(len(g)), "rule": "follow" if dirn == 1 else "fade", "net_bps": float(net.mean()), "t": _t(net),
                 "early_net": float(ee.mean()), "early_t": _t(ee)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"])
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"carried {len(out['carried'])} of {len(res)}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    if ap.parse_args(argv).scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
