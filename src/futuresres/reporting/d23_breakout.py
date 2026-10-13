"""D-series family 23 - breakouts after range compression (decisions.md 205). MNQ day and MGC London windows, owned minute trades.

    python -m futuresres.reporting.d23_breakout --scan
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
OUT = ROOT / "reports" / "d23_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
COST = {"MNQ": 0.56, "MGC": 1.0}
WIN = {"MNQ": "day", "MGC": "london"}


def sessions(market):
    days, C, V, K = d8.load(market, WIN[market]); out = []
    for i in range(len(days)):
        c, k = C[i], K[i]
        if np.isfinite(c).all() and (k == k[0]).all():
            out.append((days[i], int(k[0]), c.astype(np.float64)))
    return out


def trade(path, hi, lo, stop_kind):
    mid = (hi + lo) / 2
    for j, p in enumerate(path):
        if p > hi or p < lo:
            side = 1.0 if p > hi else -1.0; entry = p
            stop = mid if stop_kind == "mid" else (lo if side > 0 else hi)
            for q in path[j + 1:]:
                if (side > 0 and q <= stop) or (side < 0 and q >= stop):
                    return (stop - entry) / entry * 1e4 * side
            return (path[-1] - entry) / entry * 1e4 * side
    return None


def trades(market, N, stop_kind, lo_d, hi_d, nr=True):
    S = sessions(market); rng = [(c.max() - c.min()) / c.mean() for _, _, c in S]; res = []
    for i in range(N, len(S)):
        d, k, c = S[i]; pd_, pk, pc = S[i - 1]
        if not (lo_d <= d <= hi_d) or pk != k:
            continue
        is_nr = rng[i - 1] <= min(rng[i - N:i])
        if is_nr != nr:
            continue
        r = trade(c, pc.max(), pc.min(), stop_kind)
        if r is not None:
            res.append((d, r - COST[market]))
    return res


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for m in WIN:
        for N in (4, 7):
            for st in ("mid", "far"):
                tr = trades(m, N, st, *DISC); x = np.array([v for _, v in tr])
                base = np.array([v for _, v in trades(m, N, st, *DISC, nr=False)])
                res.append({"market": m, "N": N, "stop": st, "n": int(len(x)), "net_bps": float(x.mean()), "t": _t(x),
                            "non_nr_net_bps": float(base.mean()), "carried": bool(_t(x) > 1.96 and x.mean() > 0)})
                q = res[-1]
                print(f"  {m} NR{N} stop {st}: n {q['n']:4} net {q['net_bps']:+6.2f} bps t {q['t']:+5.2f} (other days {q['non_nr_net_bps']:+6.2f})"
                      f"{'  CARRIED' if q['carried'] else ''}", flush=True)
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
