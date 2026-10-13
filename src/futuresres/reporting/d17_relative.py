"""D-series family 17 - relative-value states (decisions.md 190): when a pair is stretched from its 60-session mean, does the next
session of either leg revert or continue? Yahoo daily sessions; roll-free indices. Recent-period design.

    python -m futuresres.reporting.d17_relative --scan
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
OUT = ROOT / "reports" / "d17_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
PAIRS = [("GC", "SI"), ("HG", "GC"), ("ES", "ZN"), ("NQ", "ES"), ("CL", "NG"), ("ZS", "ZC")]
COST = d12.COST


def states(S: dict, a: str, b: str):
    """Common dates (sorted), z known before each date's session, the next-session returns of A and B on that date."""
    ds = sorted(set(S[a]) & set(S[b]))
    ra = np.array([S[a][d] for d in ds]) / 1e4; rb = np.array([S[b][d] for d in ds]) / 1e4
    spread = np.cumsum(np.log1p(ra)) - np.cumsum(np.log1p(rb))
    z = np.full(len(ds), np.nan)
    for i in range(61, len(ds)):
        w = spread[i - 61:i - 1]                           # the 60 sessions BEFORE the previous close
        sd = w.std(ddof=1)
        if sd > 0:
            z[i] = (spread[i - 1] - w.mean()) / sd         # the state at the previous close, known before session i
    return np.array(ds), z, ra * 1e4, rb * 1e4


def trades(c, S, lo, hi, permute_rng=None):
    a, b = c["pair"]; ds, z, ra, rb = states(S, a, b)
    m = np.array([lo <= d <= hi for d in ds]) & np.isfinite(z)
    ds, z, ra, rb = ds[m], z[m], ra[m], rb[m]
    if permute_rng is not None:
        z = permute_rng.permutation(z)
    on = np.abs(z) > c["threshold"]
    leg_r = ra if c["leg"] == a else rb
    s = (-1.0 if c["leg"] == a else 1.0) * np.sign(z)          # reversion: A against z, B with it
    s = s if c["rule"] == "revert" else -s
    return ds[on], s[on] * leg_r[on] - COST[c["leg"]]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    S = d10.series(); res = []
    for a, b in PAIRS:
        for leg in (a, b):
            for thr in (1.5, 2.5):
                c = {"pair": [a, b], "leg": leg, "threshold": thr, "rule": "revert"}
                D, net = trades(c, S, *DISC)
                assert D.max() <= DISC[1] and D.min() >= DISC[0]
                gross = net + COST[leg]
                rule = "revert" if gross.mean() > 0 else "continue"
                net2 = net if rule == "revert" else -gross - COST[leg]
                res.append({"pair": [a, b], "leg": leg, "threshold": thr, "rule": rule, "n": int(len(net2)), "gross_revert_bps": float(gross.mean()),
                            "net_bps": float(net2.mean()), "t": _t(net2)})
    for q in res:
        q["carried"] = bool(abs(q["t"]) > 1.96 and q["net_bps"] > 0)
    res.sort(key=lambda q: -q["t"])
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for q in res:
        print(f"  {q['pair'][0]}/{q['pair'][1]} trade {q['leg']:2} |z|>{q['threshold']} n {q['n']:4} {q['rule']:8} net {q['net_bps']:+7.2f} bps t {q['t']:+5.2f}"
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
