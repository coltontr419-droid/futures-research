"""D-series family 66 - the Tokyo fix on gotobi days (decisions.md 310): USD/JPY (HistData, corrected clock) 08:00 -> 09:55 and
09:55 -> 12:00 Tokyo on the 5th/10th/15th/20th/25th/last day of the month (weekend dates to the previous weekday), in 6J's direction.
Recent-period design.

    python -m futuresres.reporting.d66_gotobi --scan
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d66_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
COST = 0.5
_F: dict = {}


def gotobi(y0: int = 2015, y1: int = 2026) -> set:
    G = set()
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            last = calendar.monthrange(y, m)[1]
            for dd in (5, 10, 15, 20, 25, last):
                d = dt.date(y, m, min(dd, last))
                while d.weekday() > 4:
                    d -= dt.timedelta(days=1)
                G.add(d)
    return G


def frame():
    if "f" not in _F:
        f = d3.histdata("usdjpy", {"a": ("Asia/Tokyo", 8, 0), "b": ("Asia/Tokyo", 9, 55), "c": ("Asia/Tokyo", 12, 0)})
        _F["f"] = f.filter(pl.col("date").dt.weekday() <= 5).drop_nulls()
    return _F["f"]


def rows(window: str, lo: dt.date, hi: dt.date, on_gotobi: bool = True):
    """(dates, 6J-direction bps) for 'pre' (08:00 -> 09:55) or 'post' (09:55 -> 12:00)."""
    f = frame(); G = gotobi(); D = f["date"].to_list(); a, b, c = (f[k].to_numpy() for k in "abc")
    x = -(b / a - 1) * 1e4 if window == "pre" else -(c / b - 1) * 1e4
    keep = np.array([(lo <= d <= hi) and ((d in G) == on_gotobi) for d in D])
    return np.array(D)[keep], x[keep]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for w in ("pre", "post"):
        D, x = rows(w, *DISC); assert D.max() <= DISC[1], "discovery read sealed data"
        dirn = 1 if x.mean() > 0 else -1; net = dirn * x - COST
        _, xn = rows(w, *DISC, on_gotobi=False); ng = dirn * xn - COST
        _, xe = rows(w, dt.date(2016, 1, 1), dt.date(2017, 12, 31)); ee = dirn * xe - COST
        r = {"window": w, "n": int(len(x)), "rule": "long 6J" if dirn == 1 else "short 6J", "net_bps": float(net.mean()), "t": _t(net),
             "non_gotobi_net": float(ng.mean()), "non_gotobi_t": _t(ng), "early_net": float(ee.mean()), "early_t": _t(ee)}
        r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
        print(f"{w}: n {r['n']} {r['rule']:8} net {r['net_bps']:+5.2f} t {r['t']:+5.2f}{'  CARRIED' if r['carried'] else ''} | non-gotobi "
              f"{r['non_gotobi_net']:+5.2f} | 2016-17 {r['early_net']:+5.2f} t {r['early_t']:+5.2f}", flush=True)
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
