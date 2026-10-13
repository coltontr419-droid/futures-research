"""D-series family 27 - volume shocks (decisions.md 218, with its amendment): after a session whose volume exceeds 2 x its previous
60-session mean, does the next session (or three) follow or reverse that session's move? Yahoo daily bars.

    python -m futuresres.reporting.d27_volume --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d27_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))


def market(m):
    z = a22.load(d10.UNIVERSE[m], "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5).sort("date")
    S = d10.series()[m]
    ds = [d for d in z["date"].to_list() if d in S]
    vol = dict(zip(z["date"].to_list(), z["v"].to_list()))
    return np.array(ds), np.array([S[d] for d in ds]), np.array([vol.get(d) or np.nan for d in ds], float)


def trades(m, h, direction, lo, hi, shock=True):
    ds, r, v = market(m); out = []; busy = -1
    for i in range(60, len(ds) - h):
        if i <= busy or not (lo <= ds[i] <= hi and lo <= ds[i + h] <= hi):
            continue
        base = np.nanmean(v[i - 60:i])
        is_shock = np.isfinite(v[i]) and base > 0 and v[i] > 2 * base
        if is_shock != shock:
            continue
        g = direction * np.sign(r[i]) * r[i + 1:i + 1 + h].sum() - h * d12.COST[m]
        out.append((ds[i + 1], float(g))); busy = i + h
    return out


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for m in d10.UNIVERSE:
        for h in (1, 3):
            fol = trades(m, h, 1, *DISC)
            if len(fol) < 10:
                continue
            gross = np.mean([v for _, v in fol]) + h * d12.COST[m]; direction = 1 if gross > 0 else -1
            x = np.array([v for _, v in (fol if direction == 1 else trades(m, h, -1, *DISC))])
            res.append({"market": m, "h": h, "n": int(len(x)), "rule": "follow" if direction == 1 else "fade", "net_bps": float(x.mean()),
                        "t": _t(x), "carried": bool(_t(x) > 1.96 and x.mean() > 0)})
    res.sort(key=lambda q: -q["t"])
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for q in res[:10]:
        print(f"  {q['market']:3} next {q['h']} {q['rule']:6} n {q['n']:3} net {q['net_bps']:+7.2f} bps t {q['t']:+5.2f}{'  CARRIED' if q['carried'] else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
