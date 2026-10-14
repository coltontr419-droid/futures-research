"""D-series family 116 - the calendar on the current regime (decisions.md 436).

    python -m futuresres.reporting.d116_calendar --scan
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d116_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
TARGETS = d111.TARGETS
CELLS = ("Mon", "Tue", "Wed", "Thu", "Fri", "first3", "last_day", "mid_month", "expiry_fri", "expiry_week")


def _third_friday(y, m):
    d = dt.date(y, m, 15)
    while d.weekday() != 4:
        d += dt.timedelta(days=1)
    return d


def cell_days(Y: dict, cell: str) -> set:
    days = sorted(Y)
    if cell in ("Mon", "Tue", "Wed", "Thu", "Fri"):
        return {d for d in days if d.weekday() == CELLS.index(cell)}
    bym = collections.defaultdict(list)
    for d in days:
        bym[(d.year, d.month)].append(d)
    out = set()
    for (y, m), v in bym.items():
        if cell == "first3":
            out |= set(v[:3])
        elif cell == "last_day":
            out.add(v[-1])
        elif cell == "mid_month":
            c = [d for d in v if d.day >= 15]
            if c:
                out.add(c[0])
        elif cell == "expiry_fri":
            tf = _third_friday(y, m)
            if tf in v:
                out.add(tf)
        elif cell == "expiry_week":
            tf = _third_friday(y, m)
            out |= {d for d in v if tf - dt.timedelta(days=4) <= d < tf}
    return out


def rows(tg: str, cell: str, lo, hi, placebo_rng=None):
    Y = d111.target(tg); inp = {d: y for d, y in Y.items() if lo <= d <= hi}; cd = cell_days(Y, cell)
    on = [d for d in inp if d in cd]; off = [d for d in inp if d not in cd]
    if placebo_rng is not None:
        on = list(placebo_rng.choice(off, len(on), replace=False)); off = [d for d in inp if d not in set(on)]
    mu = np.mean([inp[d] for d in off])
    return np.array(sorted(on)), np.array([inp[d] - mu for d in sorted(on)])


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for tg, cost in TARGETS.items():
        for cell in CELLS:
            D, x = rows(tg, cell, *DISC)
            if len(x) < 20:
                continue
            dirn = 1 if x.mean() > 0 else -1; net = dirn * x - cost
            _, xc = rows(tg, cell, *CONTEXT); cc = dirn * xc - cost
            r = {"target": tg, "cell": cell, "n": int(len(x)), "side": "long" if dirn == 1 else "short", "net_bps": float(net.mean()), "t": _t(net),
                 "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res[:8]:
        print(f"  {r['target']:3} {r['cell']:11} n {r['n']:4} {r['side']:5} net {r['net_bps']:+7.2f} t {r['t']:+5.2f} | 2010-20 "
              f"{(r['context_net'] or float('nan')):+7.2f} t {(r['context_t'] or float('nan')):+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    if ap.parse_args(argv).scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
