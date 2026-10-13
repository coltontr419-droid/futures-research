"""D-series family 14 - hour-of-day drift on traded MNQ and gold (decisions.md 182), recent-period design: discovery
2018-01 -> 2022-12; validation 2023-01 -> 2026-08 sealed. Standalone, net of a round trip.

    python -m futuresres.reporting.d14_hours --scan
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
OUT = ROOT / "reports" / "d14_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
COST = {"MNQ": 0.56, "MGC": 1.0}


def cells(market: str, session: str) -> list:
    """(label, start offset, end offset) per clock hour of the session; offsets in the grid's minutes."""
    a, b = d8.SESSIONS[(market, session)]
    T = (b - a) % 1440; out = []; o = 0
    first = (60 - a % 60) % 60 or 60          # first boundary on the hour
    edges = [0] + list(range(first, T, 60)) + [T]
    edges = sorted(set(edges))
    for s, e in zip(edges[:-1], edges[1:]):
        hh, mm = divmod((a + s) % 1440, 60)
        out.append((f"{hh:02d}:{mm:02d}", s, e))
    return out


def hour_returns(market: str, session: str, s: int, e: int, lo: dt.date, hi: dt.date, data=None):
    days, C, V, K = data if data is not None else d8.load(market, session)
    p0 = C[:, s - 1] if s > 0 else C[:, 0]        # the price at the hour's start (previous minute's close; the session's first bar)
    k0 = K[:, s - 1] if s > 0 else K[:, 0]
    p1 = C[:, e - 1]; k1 = K[:, e - 1]
    ok = np.isfinite(p0) & np.isfinite(p1) & (k0 == k1) & np.array([lo <= d <= hi for d in days])
    return np.array(days)[ok], ((p1[ok] / p0[ok]) - 1) * 1e4


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for (m, sess) in d8.SESSIONS:
        data = d8.load(m, sess)
        for lab, s, e in cells(m, sess):
            D, r = hour_returns(m, sess, s, e, *DISC, data=data)
            assert D.max() <= DISC[1] and D.min() >= DISC[0]
            res.append({"market": m, "session": sess, "hour": lab, "start": s, "end": e, "n": int(len(r)), "mean_bps": float(r.mean()),
                        "sd_bps": float(r.std(ddof=1)), "t": _t(r), "cost_bps": COST[m], "direction": "long" if r.mean() > 0 else "short"})
    for q in res:
        q["carried"] = bool(abs(q["t"]) > 1.96 and abs(q["mean_bps"]) > q["cost_bps"])
    res.sort(key=lambda q: -abs(q["t"]))
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_passes_5pct": round(0.05 * len(res), 1),
           "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests on {DISC[0]} -> {DISC[1]}; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for q in res[:14]:
        print(f"  {q['market']} {q['session']:6} {q['hour']} n {q['n']:4} {q['direction']:5} mean {q['mean_bps']:+6.2f} bps sd {q['sd_bps']:5.1f} t {q['t']:+5.2f} "
              f"cost {q['cost_bps']}{'  CARRIED' if q['carried'] else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
