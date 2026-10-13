"""D-series family 26 - the response to a shock over the following sessions (decisions.md 215). Yahoo daily sessions.

    python -m futuresres.reporting.d26_shocklag --scan
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
import futuresres.reporting.d12_extreme as d12
import futuresres.reporting.d24_shock as d24

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d26_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
SHOCKS = ("ZN", "6E", "ES", "CL", "GC")
SPANS = {"next3": (1, 3), "days2-3": (2, 3)}


def trades(Y, p, target, span, direction, lo, hi, shock=True, starts=None):
    """(date, net) per trade: target sessions after the shock date within the span, non-overlapping."""
    sh = d24.shocks(Y, p); ds = sorted(Y[target]); r = np.array([Y[target][d] for d in ds]); a, b = SPANS[span]
    out = []; busy = None
    for i, d in enumerate(ds):
        if busy is not None and d <= busy:
            continue
        q = sh.get(d)
        if q is None or q[1] != shock or not (lo <= d <= hi) or i + b >= len(ds):
            continue
        if not (lo <= ds[i + b] <= hi):
            continue
        g = direction * np.sign(q[0]) * r[i + a:i + b + 1].sum() - (b - a + 1) * d12.COST[target]
        out.append((ds[i + a], float(g))); busy = ds[i + b]
    return out


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    Y = d10.series(); res = []
    for p in SHOCKS:
        for tg in d10.UNIVERSE:
            if tg == p:
                continue
            for span in SPANS:
                fol = trades(Y, p, tg, span, 1, *DISC)
                a, b = SPANS[span]; gross = np.mean([v for _, v in fol]) + (b - a + 1) * d12.COST[tg]
                direction = 1 if gross > 0 else -1
                x = np.array([v for _, v in (fol if direction == 1 else trades(Y, p, tg, span, -1, *DISC))])
                res.append({"shock": p, "target": tg, "span": span, "n": int(len(x)), "rule": "follow" if direction == 1 else "fade",
                            "net_bps": float(x.mean()), "t": _t(x), "carried": bool(_t(x) > 1.96 and x.mean() > 0)})
    res.sort(key=lambda q: -q["t"])
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for q in res[:12]:
        print(f"  after a {q['shock']} shock: {q['target']:3} {q['span']:8} {q['rule']:6} n {q['n']:3} net {q['net_bps']:+7.2f} bps t {q['t']:+5.2f}"
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
