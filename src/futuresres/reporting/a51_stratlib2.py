"""A51 - strategy library batch 2: batch 1's intraday rules on eight more markets (decisions.md 586).

    python -m futuresres.reporting.a51_stratlib2 --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.a21_more_accounts as a21
import futuresres.reporting.d8_intraday as d8

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a51_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
COST = {"MGC": 0.8, "DAX": 0.3, "NKD": 0.2, "6E": 0.3, "6B": 0.5, "6A": 0.6, "6J": 0.5, "SI": 0.5}
VARIANTS = ("ORB15", "ORB30", "VB0.3", "VB0.5", "FH")
_G: dict = {}


def grid(mkt: str):
    """(dates, relative minute closes from the window's open) - complete sessions only."""
    if mkt not in _G:
        if mkt == "MGC":
            D, C, _, K = d8.load("MGC", "london"); ds, rows = [], []
            for i, d in enumerate(D):
                c = C[i]
                if np.isfinite(c).all() and K[i, 0] == K[i, -1]:
                    ds.append(d); rows.append(c / c[0] - 1)
        else:
            ds, rows = [], []
            for era in ("pre", "post"):
                z = np.load(a21.CACHE / f"a21_{mkt}_{era}.npz")
                for d, c in zip(z["d"].astype(object), z["c"]):
                    if np.isfinite(c).all():
                        ds.append(d); rows.append(c.astype(np.float64))
        _G[mkt] = (ds, np.array(rows))
    return _G[mkt]


def trades(mkt: str, var: str) -> list:
    D, C = grid(mkt); out = []; prev = None; T = C.shape[1]
    for i, d in enumerate(D):
        c = C[i]
        if var.startswith("ORB"):
            m = int(var[3:]); hi, lo = c[:m].max(), c[:m].min()
            for j in range(m, T - 1):
                if c[j] > hi:
                    out.append((d, 1, i, j)); break
                if c[j] < lo:
                    out.append((d, -1, i, j)); break
        elif var.startswith("VB") and prev is not None:
            k = float(var[2:])
            for j in range(1, T - 1):
                if c[j] >= c[0] + k * prev:
                    out.append((d, 1, i, j)); break
                if c[j] <= c[0] - k * prev:
                    out.append((d, -1, i, j)); break
        elif var == "FH" and T > 61:
            s = np.sign(c[60] - c[0])
            if s:
                out.append((d, int(s), i, 60))
        prev = float(c.max() - c.min())
    return out


def net_bps(mkt: str, t) -> float:
    d, s, i, j = t; c = grid(mkt)[1][i]
    return s * ((1 + c[-1]) / (1 + c[j]) - 1) * 1e4 - COST[mkt]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = {}
    for mkt in COST:
        for v in VARIANTS:
            T = trades(mkt, v); row = {}
            for per, (lo, hi) in (("2010-20", CONTEXT), ("2021-24", DISC)):
                x = np.array([net_bps(mkt, t) for t in T if lo <= t[0] <= hi])
                row[per] = {"n": int(len(x)), "net": float(x.mean()) if len(x) else float("nan"), "t": _t(x)}
            row["carried"] = bool(row["2021-24"]["net"] > 0 and row["2021-24"]["t"] > 1.96)
            res[f"{mkt}:{v}"] = row
            print(f"{mkt:4} {v:6}: 2021-24 n {row['2021-24']['n']:4} net {row['2021-24']['net']:+6.2f} t {row['2021-24']['t']:+5.2f} | 2010-20 net "
                  f"{row['2010-20']['net']:+6.2f} t {row['2010-20']['t']:+5.2f}{'  CARRIED' if row['carried'] else ''}", flush=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    if ap.parse_args().scan:
        scan()
