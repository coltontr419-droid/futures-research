"""D-series family 18 - weekly structure and short-trend persistence (decisions.md 192). Yahoo daily sessions, 14 futures,
recent-period design, standalone net of cost.

    python -m futuresres.reporting.d18_weekly --scan
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

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d18_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
KINDS = ("week_so_far", "trend5", "trend20")


def pairs(S: dict, m: str, kind: str, lo, hi):
    """(dates, target session return, predictor) - predictor known before the target session opens."""
    ds = sorted(S[m]); r = np.array([S[m][d] for d in ds]); D, Y, X = [], [], []
    for i, d in enumerate(ds):
        if not (lo <= d <= hi):
            continue
        if kind == "week_so_far":
            if d.weekday() not in (3, 4):
                continue
            wk = d.isocalendar()[:2]
            j = [k for k in range(max(0, i - 6), i) if ds[k].isocalendar()[:2] == wk and ds[k].weekday() <= 2]
            if len(j) < 2:
                continue
            x = r[j].sum()
        else:
            n = 5 if kind == "trend5" else 20
            if i < n:
                continue
            x = r[i - n:i].sum()
        D.append(d); Y.append(r[i]); X.append(x)
    return np.array(D), np.array(Y), np.array(X)


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    S = d10.series(); res = []
    for m in d10.UNIVERSE:
        for kind in KINDS:
            D, Y, X = pairs(S, m, kind, *DISC)
            assert D.max() <= DISC[1] and D.min() >= DISC[0]
            g = np.sign(X) * Y; direction = 1 if g.mean() > 0 else -1
            net = direction * g - d12.COST[m]
            res.append({"market": m, "kind": kind, "n": int(len(net)), "rule": "follow" if direction == 1 else "fade",
                        "gross_bps": float(direction * g.mean()), "net_bps": float(net.mean()), "t": _t(net)})
    for q in res:
        q["carried"] = bool(abs(q["t"]) > 1.96 and q["net_bps"] > 0)
    res.sort(key=lambda q: -q["t"])
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for q in res[:14]:
        print(f"  {q['market']:3} {q['kind']:11} n {q['n']:4} {q['rule']:6} gross {q['gross_bps']:+6.2f} net {q['net_bps']:+6.2f} bps t {q['t']:+5.2f}"
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
