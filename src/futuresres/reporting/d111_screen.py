"""D-series family 111 - a two-period screen of the shock class (decisions.md 414): every fetched daily series' 2-sigma shocks on the
previous weekday -> the plan's six targets; carried only if 2018-22 t > 1.96 and 2010-17 (same rule) t > 1.0.

    python -m futuresres.reporting.d111_screen --scan
"""

from __future__ import annotations

import argparse
import csv
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
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d63_realyield as d63

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d111_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
EARLY = (dt.date(2010, 1, 1), dt.date(2017, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
OC = ("6A=F", "6B=F", "6C=F", "6E=F", "6J=F", "6S=F", "BTC=F", "CL=F", "ES=F", "GC=F", "HE=F", "HG=F", "HO=F", "LE=F", "NG=F", "NKD=F",
      "NQ=F", "RB=F", "RTY=F", "SI=F", "ZB=F", "ZC=F", "ZL=F", "ZM=F", "ZN=F", "ZS=F", "ZT=F", "ZW=F", "DX-Y.NYB",
      "ADM", "BG", "EEM", "FXI", "GDX", "HYG", "KRE", "LQD", "SMH", "SOYB", "TLT", "XLE", "XLF", "XLK", "XLU", "XLY", "XOP", "^GDAXI")
CC = ("^VIX", "^VIX3M", "^VVIX", "^SKEW", "^GVZ", "^OVX", "PL=F")
FX = ("ARS=X", "CLP=X", "COP=X", "INR=X", "KRW=X", "MXN=X", "MYR=X", "NOK=X", "PEN=X", "RUB=X", "ZAR=X", "CAD=X", "BRL=X", "AUDUSD=X",
      "IDR=X", "BTC-USD")
FRED = ("DFII10", "T10YIE")
TARGETS = {"MNQ": 0.5, "MGC": 0.8, "NKD": 0.2, "DAX": 0.3, "CL": 0.7, "ZS": 0.7}
SELF = {"MNQ": {"NQ=F"}, "MGC": {"GC=F"}, "NKD": {"NKD=F"}, "DAX": {"^GDAXI"}, "CL": {"CL=F"}, "ZS": {"ZS=F", "SOYB"}}
VALIDATED = {("ZN=F", "MNQ"), ("HYG", "DAX"), ("DFII10", "MGC"), ("XLF", "MNQ"), ("XLK", "MNQ"), ("TLT", "MGC"), ("LQD", "MGC"),
             ("BRL=X", "ZS")}
UNIV14 = {"ES=F", "NQ=F", "RTY=F", "GC=F", "SI=F", "HG=F", "CL=F", "NG=F", "ZN=F", "6E=F", "6J=F", "ZC=F", "ZS=F", "ZW=F"}
_C: dict = {}


def _clean(ds, r):
    md = np.nanmedian(r); rs = 1.4826 * np.nanmedian(np.abs(r - md))
    return {d: float(x) for d, x in zip(ds, r) if np.isfinite(x) and abs(x - md) <= 15 * rs}


def predictor(sym: str) -> dict:
    if sym in _C:
        return _C[sym]
    if sym in FRED:
        rows = [(dt.date.fromisoformat(a), float(b)) for a, b in list(csv.reader(open(ROOT / "data" / "cache" / f"fred_{sym}.csv")))[1:] if b not in ("", ".")]
        ds = [r[0] for r in rows]; v = np.array([r[1] for r in rows]); out = _clean(ds[1:], np.diff(v) * 100)
    else:
        z = a22.load(sym, "1d")
        if sym in FX:
            z = z.with_columns(pl.col("ts").dt.convert_time_zone("UTC").dt.date().alias("date"))
        else:
            z = z.with_columns(pl.col("ts").dt.date().alias("date"))
        z = z.filter(pl.col("date").dt.weekday() <= 5).unique("date", keep="last").sort("date")
        ds = z["date"].to_list()
        if sym in OC:
            r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy()
        else:
            c = z["c"].to_numpy(); r = np.r_[np.nan, np.diff(np.log(c)) * 1e4]
        out = _clean(ds, r)
    _C[sym] = out
    return out


def shocks(sym: str) -> dict:
    key = "sh_" + sym
    if key not in _C:
        S = predictor(sym); ds = sorted(S); r = np.array([S[d] for d in ds]); out = {}
        for i in range(60, len(r)):
            out[ds[i]] = (float(r[i]), bool(abs(r[i]) > 2 * r[i - 60:i].std(ddof=1)))
        _C[key] = out
    return _C[key]


def target(tg: str) -> dict:
    key = "tg_" + tg
    if key not in _C:
        if tg in ("MNQ", "MGC"):
            _C[key] = d63.target(tg)
        elif tg in ("NKD", "DAX"):
            Y = {}
            for era in ("pre", "post"):
                z = np.load(a21.CACHE / f"a21_{tg}_{era}.npz")
                for d, c in zip(z["d"].astype(object), z["c"][:, -1]):
                    Y[d] = float(c) * 1e4
            _C[key] = Y
        else:
            _C[key] = d10.series()[tg]
    return _C[key]


def eligible(p: str, tg: str) -> bool:
    if p in SELF[tg] or (p, tg) in VALIDATED:
        return False
    if tg in ("CL", "NKD") and p in FX:
        return False
    if tg in ("CL", "ZS") and p in UNIV14:
        return False
    return True


def rows(p: str, tg: str, lo: dt.date, hi: dt.date, shock: bool = True):
    sh = shocks(p); D, Y, X = [], [], []
    for d, y in target(tg).items():
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
    for p in OC + CC + FX + FRED:
        for tg, cost in TARGETS.items():
            if not eligible(p, tg):
                continue
            D, Y, X = rows(p, tg, *DISC)
            if len(Y) < 20:
                continue
            g = np.sign(X) * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            _, Ye, Xe = rows(p, tg, *EARLY); ee = dirn * np.sign(Xe) * Ye - cost
            r = {"predictor": p, "target": tg, "n": int(len(g)), "rule": "follow" if dirn == 1 else "fade", "net_bps": float(net.mean()), "t": _t(net),
                 "early_n": int(len(ee)), "early_net": float(ee.mean()) if len(ee) else None, "early_t": _t(ee) if len(ee) > 2 else None}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0 and r["early_t"] is not None and r["early_t"] > 1.0 and r["early_net"] > 0)
            res.append(r)
    res.sort(key=lambda r: -r["t"])
    n = len(res); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": n, "expected_chance_carries": round(0.004 * n, 2), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{n} tests; ~{0.004 * n:.1f} carried by chance; carried {len(carried)}; passing 2018-22 alone {sum(r['t'] > 1.96 and r['net_bps'] > 0 for r in res)}", flush=True)
    for r in res[:15]:
        print(f"  {r['target']:3} after {r['predictor']:9} n {r['n']:3} {r['rule']:6} net {r['net_bps']:+7.2f} t {r['t']:+5.2f} | 2010-17 "
              f"{(r['early_net'] or float('nan')):+7.2f} t {(r['early_t'] or float('nan')):+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    if ap.parse_args(argv).scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
