"""D-series family 25 - shocks into the plan's next windows (decisions.md 212). Shock in ZN / 6E / ES / CL / GC (Yahoo sessions) on
day D-1; targets the plan's windows dated D. Recent-period design.

    python -m futuresres.reporting.d25_shockwin --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d24_shock as d24

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d25_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
SHOCKS = ("ZN", "6E", "ES", "CL", "GC")
TARGETS = ("NKD_win", "DAX_win", "MGC_win", "MNQ_win", "ZS")
COST = {"MNQ_win": 0.5, "MGC_win": 0.8, "NKD_win": 0.2, "DAX_win": 0.3, "ZS": 0.7}


def rows(Y, W, p, target, lo, hi, shock=True):
    sh = d24.shocks(Y, p); D, R, X = [], [], []
    for d, r in W[target].items():
        if not (lo <= d <= hi):
            continue
        q = sh.get(d3.prev_weekday(d))
        if q is None or q[1] != shock:
            continue
        D.append(d); R.append(r); X.append(q[0])
    o = np.argsort(D)
    return np.array(D)[o], np.array(R)[o], np.array(X)[o]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    Y = d10.series(); W = d3.series(); res = []
    for p in SHOCKS:
        for tg in TARGETS:
            if (p, tg) == ("ZN", "MNQ_win"):
                continue
            D, R, X = rows(Y, W, p, tg, *DISC)
            g = np.sign(X) * R; direction = 1 if g.mean() > 0 else -1
            net = direction * g - COST[tg]
            res.append({"shock": p, "target": tg, "n": int(len(net)), "rule": "follow" if direction == 1 else "fade",
                        "net_bps": float(net.mean()), "t": _t(net), "carried": bool(_t(net) > 1.96 and net.mean() > 0)})
    res.sort(key=lambda q: -q["t"])
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for q in res[:8]:
        print(f"  after a {q['shock']} shock: {q['target']:8} {q['rule']:6} n {q['n']:3} net {q['net_bps']:+7.2f} bps t {q['t']:+5.2f}"
              f"{'  CARRIED' if q['carried'] else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
