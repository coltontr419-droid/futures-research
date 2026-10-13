"""D-series family 52 - the opening print (decisions.md 278): does the first minute after the open (MNQ 09:30 -> 09:31; gold COMEX
08:20 -> 08:21) set the rest of the window? Family-8 grids (bars stamped at their open). Recent-period design.

    python -m futuresres.reporting.d52_open --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d8_intraday as d8

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d52_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
#: market -> (grid, offset of the opening minute, cost bps)
MARKETS = {"MNQ": ("day", 0, 0.5), "MGC": ("london", 320, 0.8)}
_CACHE: dict = {}


def rows(market: str, lo: dt.date, hi: dt.date):
    """(dates, first-minute bps, rest-of-window bps, heavy flag). MNQ's pre-open price is the night grid's last close (09:30:00)."""
    grid, o, _ = MARKETS[market]
    if market not in _CACHE:
        _CACHE[market] = d8.load(market, grid) + ((d8.load("MNQ", "night") if market == "MNQ" else None),)
    D, C, V, K, night = _CACHE[market]
    iN = {d: i for i, d in enumerate(night[0])} if night else None
    e = C.shape[1] - 1; v = V[:, o]; out = []
    for i, d in enumerate(D):
        if i < 20 or not (lo <= d <= hi):
            continue
        if market == "MNQ":
            if d not in iN:
                continue
            j = iN[d]; p0 = night[1][j, -1]; k0 = night[3][j, -1]
        else:
            p0 = C[i, o - 1]; k0 = K[i, o - 1]
        p1, pe = C[i, o], C[i, e]
        if not np.all(np.isfinite([p0, p1, pe])) or len({k0, K[i, o], K[i, e]}) > 1:
            continue
        out.append((d, (p1 / p0 - 1) * 1e4, (pe / p1 - 1) * 1e4, bool(v[i] > 2 * np.median(v[i - 20:i]))))
    D2 = np.array([r[0] for r in out]); X = np.array([r[1] for r in out]); Y = np.array([r[2] for r in out]); H = np.array([r[3] for r in out])
    return D2, X, Y, H


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for m, (_, _, cost) in MARKETS.items():
        D, X, Y, H = rows(m, *DISC); assert D.max() <= DISC[1], "discovery read sealed data"
        for form, mask in (("all", np.ones(len(X), bool)), ("heavy", H)):
            mask = mask & (np.sign(X) != 0)
            g = np.sign(X[mask]) * Y[mask]; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            r = {"market": m, "form": form, "n": int(len(net)), "rule": "follow" if dirn == 1 else "fade", "net_bps": float(net.mean()), "t": _t(net)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
            print(f"{m} {form:5}: n {r['n']:4} {r['rule']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
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
