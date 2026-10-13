"""D-series family 49 - follow or fade the morning by the recent intraday regime (decisions.md 271): VR = var(30-min) / (6 x
var(5-min)) log returns within each session, averaged over the previous 20 sessions; the afternoon is traded in sign(morning) x
sign(VR - 1), or its inverse, fixed by discovery. MNQ day and gold London grids (family 8). Recent-period design.

    python -m futuresres.reporting.d49_vr --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.d8_intraday as d8

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d49_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
#: market -> (grid, (morning start, morning end, afternoon start, afternoon end) grid offsets, cost bps)
MARKETS = {"MNQ": ("day", (0, 150, 210, 389), 0.5), "MGC": ("london", (0, 240, 330, 509), 0.8)}


def vr_series(C, K) -> np.ndarray:
    """Per session: the 20-session trailing mean of the within-session variance ratio (NaN where unavailable)."""
    warnings.filterwarnings("ignore")
    L = np.log(C)

    def kr(k):
        R = np.full(C.shape, np.nan); R[:, k:] = L[:, k:] - L[:, :-k]; R[:, k:][K[:, k:] != K[:, :-k]] = np.nan
        return R[:, k::k]
    VR = np.nanvar(kr(30), 1) / (6 * np.nanvar(kr(5), 1))
    out = np.full(len(C), np.nan)
    for i in range(20, len(C)):
        out[i] = np.nanmean(VR[i - 20:i])
    return out


def rows(market: str, lo: dt.date, hi: dt.date, shift: int = 0):
    """(dates, signal = sign(morning) x sign(VR - 1), afternoon bps). `shift` rolls the regime series (the placebo)."""
    grid, (a, b, c, e), _ = MARKETS[market]
    D, C, _, K = d8.load(market, grid)
    vr = vr_series(C, K)
    if shift:
        vr = np.roll(vr, shift)
    out_d, X, Y = [], [], []
    for i, d in enumerate(D):
        if not (lo <= d <= hi) or not np.isfinite(vr[i]):
            continue
        p = C[i, [a, b, c, e]]; k = K[i, [a, b, c, e]]
        if not np.all(np.isfinite(p)) or len(set(k)) > 1:
            continue
        out_d.append(d); X.append(np.sign(p[1] / p[0] - 1) * np.sign(vr[i] - 1)); Y.append((p[3] / p[2] - 1) * 1e4)
    return np.array(out_d), np.array(X), np.array(Y)


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for m, (_, _, cost) in MARKETS.items():
        D, X, Y = rows(m, *DISC); assert D.max() <= DISC[1], "discovery read sealed data"
        g = X * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
        r = {"market": m, "n": int(len(net)), "rule": "as stated" if dirn == 1 else "inverse", "net_bps": float(net.mean()), "t": _t(net)}
        r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
        print(f"{m}: n {r['n']} {r['rule']:9} net {r['net_bps']:+6.2f} t {r['t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
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
