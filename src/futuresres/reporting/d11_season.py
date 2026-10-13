"""D-series family 11 - commodity seasonality as a standalone strategy (decisions.md 174): does a market drift reliably in a
calendar month? Daily session round trips (open -> settlement), net of each market's cost. Discovery 2010-01 -> 2017-12 only.

    python -m futuresres.reporting.d11_season --scan
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

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d11_discovery.json"
DISC = (dt.date(2010, 1, 1), dt.date(2017, 12, 31))
VAL = (dt.date(2018, 1, 1), dt.date(2026, 8, 31))
MARKETS = {"CL": ("CL=F", 0.7), "NG": ("NG=F", 1.4), "ZC": ("ZC=F", 1.9), "ZS": ("ZS=F", 0.7), "ZW": ("ZW=F", 1.4),
           "GC": ("GC=F", 0.8), "SI": ("SI=F", 0.5), "HG": ("HG=F", 2.0)}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def series(market: str) -> dict:
    z = a22.load(MARKETS[market][0], "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5)
    r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy(); ds = z["date"].to_list()
    med = np.median(r); rsd = 1.4826 * np.median(np.abs(r - med))
    return {d: float(x) for d, x in zip(ds, r) if np.isfinite(x) and abs(x - med) <= 15 * rsd}


def month_days(S: dict, month: int, lo: dt.date, hi: dt.date):
    inm = sorted(d for d in S if lo <= d <= hi and d.month == month)
    out = sorted(d for d in S if lo <= d <= hi and d.month != month)
    return np.array(inm), np.array([S[d] for d in inm]), np.array([S[d] for d in out])


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for m, (sym, cost) in MARKETS.items():
        S = series(m)
        for mo in range(1, 13):
            D, Y, _ = month_days(S, mo, *DISC)
            assert D.max() <= DISC[1], "discovery read sealed data"
            res.append({"market": m, "month": mo, "n": int(len(Y)), "mean_bps": float(Y.mean()), "sd_bps": float(Y.std(ddof=1)), "t": _t(Y),
                        "cost_bps": cost, "direction": "long" if Y.mean() > 0 else "short", "net_bps": float(abs(Y.mean()) - cost)})
    for r in res:
        r["carried"] = bool(abs(r["t"]) > 1.96 and abs(r["mean_bps"]) > r["cost_bps"])
    res.sort(key=lambda r: -abs(r["t"]))
    carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_passes_5pct": round(0.05 * len(res), 1),
           "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res[:16]:
        print(f"  {r['market']:2} {MONTHS[r['month'] - 1]} n {r['n']:3} {r['direction']:5} mean {r['mean_bps']:+7.2f} bps sd {r['sd_bps']:6.1f} t {r['t']:+5.2f} "
              f"net {r['net_bps']:+6.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
