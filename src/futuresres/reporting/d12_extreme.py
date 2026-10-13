"""D-series family 12 - after an extreme session (decisions.md 177): do the next 1 / 3 / 5 sessions follow or reverse a move
beyond 2 sigma? 14 futures, Yahoo daily sessions (open -> settlement), standalone, net of cost. Discovery 2010-2017 only.

    python -m futuresres.reporting.d12_extreme --scan
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

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d12_discovery.json"
DISC, VAL = d10.DISC, d10.VAL
COST = {"ES": 0.9, "NQ": 0.5, "RTY": 2.0, "GC": 0.8, "SI": 0.5, "HG": 2.0, "CL": 0.7, "NG": 1.4, "ZN": 0.4, "6E": 0.3, "6J": 0.5,
        "ZC": 1.9, "ZS": 0.7, "ZW": 1.4}
HS = (1, 3, 5)


def arrays(S: dict, m: str):
    d = sorted(S[m]); r = np.array([S[m][x] for x in d])
    sig = np.full(len(r), np.nan)
    for i in range(60, len(r)):
        sig[i] = r[i - 60:i].std(ddof=1)
    return np.array(d), r, sig


def trades(D, r, sig, h, direction, cost, lo, hi, starts=None):
    """Non-overlapping trades after events (or after the given start indices): (date of entry session, net bps)."""
    n = len(r); out = []; busy = -1
    idx = range(n) if starts is None else starts
    for i in idx:
        if i <= busy or i + h >= n or not (lo <= D[i] <= hi) or not np.isfinite(sig[i]):
            continue
        if starts is None and abs(r[i]) <= 2 * sig[i]:
            continue
        if not (lo <= D[i + h] <= hi):
            continue
        g = direction * np.sign(r[i]) * r[i + 1:i + 1 + h].sum()
        out.append((D[i + 1], float(g - h * cost))); busy = i + h
    return out


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    S = d10.series(); res = []
    for m in d10.UNIVERSE:
        D, r, sig = arrays(S, m)
        for h in HS:
            fol = trades(D, r, sig, h, 1, COST[m], *DISC)
            assert all(d <= DISC[1] for d, _ in fol)
            gross = np.mean([v for _, v in fol]) + h * COST[m]
            direction = 1 if gross > 0 else -1
            tr = fol if direction == 1 else trades(D, r, sig, h, -1, COST[m], *DISC)
            x = np.array([v for _, v in tr])
            res.append({"market": m, "h": h, "rule": "follow" if direction == 1 else "fade", "events": int(len(x)),
                        "gross_follow_bps": float(gross), "net_bps": float(x.mean()), "t": _t(x)})
    for q in res:
        q["carried"] = bool(abs(q["t"]) > 1.96 and q["net_bps"] > 0)
    res.sort(key=lambda q: -(q["t"] if q["net_bps"] > 0 else -abs(q["t"])))
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_passes_5pct": round(0.05 * len(res), 1),
           "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for q in res[:14]:
        print(f"  {q['market']:3} next {q['h']} ({q['rule']:6}) events {q['events']:3} gross-follow {q['gross_follow_bps']:+7.1f} net {q['net_bps']:+7.1f} bps "
              f"t {q['t']:+5.2f}{'  CARRIED' if q['carried'] else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
