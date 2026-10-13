"""D-series family 76 - sector and regional ETF shocks (decisions.md 331): SMH, XLF, XLE, EEM, FXI, TLT (Yahoo daily open -> close)
beyond 2 sigma on the previous weekday -> MNQ's day session and gold's London window (family-8 grids). Recent-period design.

    python -m futuresres.reporting.d76_etf --fetch
    python -m futuresres.reporting.d76_etf --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d24_shock as d24
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d63_realyield as d63

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d76_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
EARLY = (dt.date(2010, 1, 1), dt.date(2017, 12, 31))
PRED = ("SMH", "XLF", "XLE", "EEM", "FXI", "TLT")
COST = {"MNQ": 0.5, "MGC": 0.8}
_S: dict = {}


def fetch() -> None:
    for s in PRED:
        a22.fetch(s, "1d"); time.sleep(0.5)


def series() -> dict:
    if not _S:
        for s in PRED:
            z = a22.load(s, "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5)
            r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy(); ds = z["date"].to_list()
            md = np.nanmedian(r); rs = 1.4826 * np.nanmedian(np.abs(r - md))
            _S[s] = {d: float(x) for d, x in zip(ds, r) if np.isfinite(x) and abs(x - md) <= 15 * rs}
    return _S


def rows(p: str, m: str, lo: dt.date, hi: dt.date, shock: bool = True):
    sh = d24.shocks(series(), p); D, Y, X = [], [], []
    for d, y in d63.target(m).items():
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
        for m, cost in COST.items():
            D, Y, X = rows(p, m, *DISC); assert D.max() <= DISC[1], "discovery read sealed data"
            g = np.sign(X) * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            _, Ye, Xe = rows(p, m, *EARLY); ee = dirn * np.sign(Xe) * Ye - cost
            r = {"predictor": p, "target": m, "n": int(len(g)), "rule": "follow" if dirn == 1 else "fade", "net_bps": float(net.mean()), "t": _t(net),
                 "early_net": float(ee.mean()), "early_t": _t(ee)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"])
    for r in res[:6]:
        print(f"{r['target']} after {r['predictor']:3}: n {r['n']} {r['rule']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f}"
              f"{'  CARRIED' if r['carried'] else ''} | 2010-17 {r['early_net']:+6.2f} t {r['early_t']:+5.2f}", flush=True)
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--fetch", action="store_true"); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.fetch:
        fetch()
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
