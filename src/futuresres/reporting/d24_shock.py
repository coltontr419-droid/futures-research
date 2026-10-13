"""D-series family 24 - the next session across markets after a shock day (decisions.md 207). Yahoo daily sessions, 14 futures.

    python -m futuresres.reporting.d24_shock --scan
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
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d24_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
PREDICTORS = ("ES", "CL", "GC", "ZN")


def shocks(S, p):
    ds = sorted(S[p]); r = np.array([S[p][d] for d in ds]); out = {}
    for i in range(60, len(r)):
        sd = r[i - 60:i].std(ddof=1)
        out[ds[i]] = (r[i], bool(abs(r[i]) > 2 * sd))
    return out


def rows(S, p, target, lo, hi, shock=True):
    sh = shocks(S, p); D, Y, X = [], [], []
    for d, y in S[target].items():
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
    S = d10.series(); res = []
    for p in PREDICTORS:
        for tg in d10.UNIVERSE:
            if tg == p:
                continue
            D, Y, X = rows(S, p, tg, *DISC)
            g = np.sign(X) * Y; direction = 1 if g.mean() > 0 else -1
            net = direction * g - d12.COST[tg]
            res.append({"predictor": p, "target": tg, "n": int(len(net)), "rule": "follow" if direction == 1 else "fade",
                        "net_bps": float(net.mean()), "t": _t(net), "carried": bool(_t(net) > 1.96 and net.mean() > 0)})
    res.sort(key=lambda q: -q["t"])
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for q in res[:10]:
        print(f"  after a {q['predictor']} shock: {q['target']:3} {q['rule']:6} n {q['n']:3} net {q['net_bps']:+7.2f} bps t {q['t']:+5.2f}"
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
