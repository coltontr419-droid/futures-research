"""D-series family 57 - the newer shock predictors into the plan's other products (decisions.md 289): ZT, ZB, DX, HYG, BTC (family
39's Yahoo series) and the VIX (family 38, log change) shocking on the previous weekday -> NKD and DAX windows (A21 paths), CL and ZS
sessions (family 10). Recent-period design.

    python -m futuresres.reporting.d57_newshock --scan
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

import futuresres.reporting.a21_more_accounts as a21
import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d24_shock as d24
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d57_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
PRED = {"ZT": "ZT=F", "ZB": "ZB=F", "DX": "DX-Y.NYB", "HYG": "HYG", "BTC": "BTC-USD"}
COST = {"NKD": 0.2, "DAX": 0.3, "CL": 0.7, "ZS": 0.7}


def _ser(sym: str) -> dict:
    z = a22.load(sym, "1d")
    ts = z["ts"].dt.convert_time_zone("UTC") if sym == "BTC-USD" else z["ts"]
    z = z.with_columns(ts.dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5)
    r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy(); ds = z["date"].to_list()
    med = np.nanmedian(r); rsd = 1.4826 * np.nanmedian(np.abs(r - med))
    return {d: float(x) for d, x in zip(ds, r) if np.isfinite(x) and abs(x - med) <= 15 * rsd}


def predictors() -> dict:
    S = {k: _ser(v) for k, v in PRED.items()}
    z = a22.load("^VIX", "1d"); vd = [a.date() for a in z["ts"].to_list()]; vc = z["c"].to_numpy()
    S["VIX"] = {vd[i]: float(np.log(vc[i] / vc[i - 1]) * 1e4) for i in range(1, len(vd)) if vc[i] > 0 and vc[i - 1] > 0}
    return S


def targets() -> dict:
    T = {}
    for tg in ("NKD", "DAX"):
        Y = {}
        for era in ("pre", "post"):
            z = np.load(a21.CACHE / f"a21_{tg}_{era}.npz")
            for d, c in zip(z["d"].astype(object), z["c"][:, -1]):
                Y[d] = float(c) * 1e4
        T[tg] = Y
    U = d10.series(); T["CL"] = U["CL"]; T["ZS"] = U["ZS"]
    return T


def rows(S, T, p, tg, lo, hi, shock=True):
    sh = d24.shocks(S, p); D, Y, X = [], [], []
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
    S, T = predictors(), targets(); res = []
    for p in S:
        for tg in T:
            D, Y, X = rows(S, T, p, tg, *DISC); assert D.max() <= DISC[1], "discovery read sealed data"
            g = np.sign(X) * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - COST[tg]
            r = {"predictor": p, "target": tg, "n": int(len(g)), "rule": "follow" if dirn == 1 else "fade", "net_bps": float(net.mean()), "t": _t(net)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"])
    for r in res[:8]:
        print(f"{r['target']:3} after {r['predictor']:3} shock: n {r['n']:3} {r['rule']:6} net {r['net_bps']:+7.2f} t {r['t']:+5.2f}"
              f"{'  CARRIED' if r['carried'] else ''}", flush=True)
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    if ap.parse_args(argv).scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
