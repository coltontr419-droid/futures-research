"""D-series family 22 - gap-fill brackets at the window open (decisions.md 203). MNQ day window vs the previous 16:00 close; MGC
London window vs the previous 11:30 close. Owned minute trades (family-8 grids). Recent-period design.

    python -m futuresres.reporting.d22_gapfill --scan
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
OUT = ROOT / "reports" / "d22_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
COST = {"MNQ": 0.56, "MGC": 1.0}
WIN = {"MNQ": "day", "MGC": "london"}
THR = (0.25, 0.5, 1.0)
STOPS = (0.5, 1.0, 2.0)


def gaps(market: str):
    """Per day with a previous window: date, open price (first minute close), previous close, the window's minute closes."""
    days, C, V, K = d8.load(market, WIN[market])
    out = []
    for i in range(1, len(days)):
        c, k, pc, pk = C[i], K[i], C[i - 1, -1], K[i - 1, -1]
        if not (np.isfinite(c).all() and np.isfinite(pc)) or (k != k[0]).any() or pk != k[0]:
            continue
        out.append((days[i], float(c[0]), float(pc), c.astype(np.float64)))
    g = np.array([(o - pc) / pc * 1e4 for _, o, pc, _ in out])
    sig = np.full(len(g), np.nan)
    for i in range(60, len(g)):
        sig[i] = g[i - 60:i].std(ddof=1)
    return out, g, sig


def bracket(path, entry, take_px, stop_px, side):
    """Net-of-nothing return (bps of entry) of a bracket on minute closes: side +1 long / -1 short."""
    for p in path[1:]:
        hit_stop = (p <= stop_px) if side > 0 else (p >= stop_px)
        hit_take = (p >= take_px) if side > 0 else (p <= take_px)
        if hit_stop:
            return (stop_px - entry) / entry * 1e4 * side
        if hit_take:
            return (take_px - entry) / entry * 1e4 * side
    return (path[-1] - entry) / entry * 1e4 * side


def trades(market, thr, s, lo, hi, breakout=False):
    out, g, sig = gaps(market); res = []
    for (d, o, pc, path), gi, si in zip(out, g, sig):
        if not (lo <= d <= hi) or not np.isfinite(si) or abs(gi) <= thr * si:
            continue
        side = -np.sign(gi) if not breakout else np.sign(gi)        # toward the fill (or away, the placebo)
        dist = abs(o - pc)
        take = o + side * dist; stop = o - side * s * dist
        res.append((d, bracket(path, o, take, stop, side) - COST[market]))
    return res


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for m in WIN:
        for thr in THR:
            for s in STOPS:
                tr = trades(m, thr, s, *DISC); x = np.array([v for _, v in tr])
                assert all(d <= DISC[1] for d, _ in tr)
                res.append({"market": m, "threshold_sigma": thr, "stop_multiple": s, "n": int(len(x)), "net_bps": float(x.mean()), "t": _t(x),
                            "carried": bool(_t(x) > 1.96 and x.mean() > 0)})
                q = res[-1]
                print(f"  {m} |gap| > {thr} sigma, stop {s}x: n {q['n']:4} net {q['net_bps']:+6.2f} bps t {q['t']:+5.2f}{'  CARRIED' if q['carried'] else ''}", flush=True)
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; carried {len(carried)}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
