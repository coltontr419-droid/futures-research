"""D-series discovery (decisions.md 129-130): hour-of-day and hour-by-weekday return patterns on markets this programme
has not examined, on 2010-2017 ONLY. A SCAN, not a trial; it selects at most 5 candidates for one-shot validation on the
sealed 2018-2026 window.

    python -m futuresres.reporting.d_discovery

Families (fixed in decisions.md 129 before this code ran): D-a, each UTC hour's 1-hour return over all weekdays; D-b,
each UTC hour on each weekday. Selection: two-sided |t| > 4.1 (Bonferroni over 1,008 tests) AND |mean| > 2 x round-trip
cost; at most 5 by |t|; a D-b cell inside a carried D-a hour of the same instrument is a duplicate.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

from futuresres.data.fx_fix import hourly_utc

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d_discovery.json"
DISCOVERY_END = dt.datetime(2018, 1, 1, tzinfo=dt.timezone.utc)
UNIVERSE = {"gbpusd": ("6B", 0.8), "audusd": ("6A", 0.8), "usdcad": ("6C", 0.8), "usdchf": ("6S", 0.8),
            "grxeur": ("FDAX", 1.0), "jpxjpy": ("NKD", 1.0), "xagusd": ("SI", 1.5)}
T_SEL, MAX_CARRY = 4.1, 5
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")


def hourly_returns(pair: str, start: dt.datetime | None = None, end: dt.datetime = DISCOVERY_END) -> pl.DataFrame:
    """1-hour returns (bps) labelled by the UTC hour they START, weekdays only, from consecutive whole-hour prices."""
    h = hourly_utc(pair).sort("utc")
    if start is not None:
        h = h.filter(pl.col("utc") >= start)
    h = h.filter(pl.col("utc") < end)
    r = h.with_columns(pl.col("utc").shift(1).alias("prev_t"), pl.col("c").shift(1).alias("prev_c"))
    r = r.filter((pl.col("utc") - pl.col("prev_t")) == pl.duration(hours=1))
    r = r.with_columns(((pl.col("c") / pl.col("prev_c") - 1) * 1e4).alias("bps"), pl.col("prev_t").dt.hour().alias("hour"),
                       pl.col("prev_t").dt.weekday().alias("wd"))
    return r.filter(pl.col("wd") <= 5).select(pl.col("prev_t").alias("start"), "hour", "wd", "bps")


def _cell(x: np.ndarray) -> dict:
    n = len(x)
    if n < 30:
        return {"n": n}
    return {"n": n, "mean": float(x.mean()), "sd": float(x.std(ddof=1)), "t": float(x.mean() / (x.std(ddof=1) / math.sqrt(n)))}


def scan() -> dict:
    cells = []
    for pair, (fut, cost) in UNIVERSE.items():
        r = hourly_returns(pair)
        assert r["start"].max() < DISCOVERY_END, "discovery read past 2017-12-31"
        for h in range(24):
            x = r.filter(pl.col("hour") == h)["bps"].to_numpy()
            cells.append({"family": "D-a", "pair": pair, "future": fut, "cost": cost, "hour": h, "weekday": None, **_cell(x)})
            for wd in range(1, 6):
                x = r.filter((pl.col("hour") == h) & (pl.col("wd") == wd))["bps"].to_numpy()
                cells.append({"family": "D-b", "pair": pair, "future": fut, "cost": cost, "hour": h, "weekday": WEEKDAYS[wd - 1], **_cell(x)})
    tests = [c for c in cells if "t" in c]
    passing = [c for c in tests if abs(c["t"]) > T_SEL and abs(c["mean"]) > 2 * c["cost"]]
    passing.sort(key=lambda c: -abs(c["t"]))
    carried = []
    for c in passing:
        if len(carried) >= MAX_CARRY:
            break
        if c["family"] == "D-b" and any(k["family"] == "D-a" and k["pair"] == c["pair"] and k["hour"] == c["hour"] for k in carried):
            continue
        carried.append(c)
    top = sorted(tests, key=lambda c: -abs(c["t"]))[:15]
    return {"window": ["2010-01-01", "2017-12-31"], "tests": len(tests), "t_threshold": T_SEL, "passing_selection": len(passing),
            "carried": carried, "top15_by_abs_t": top}


def main(argv=None) -> int:
    r = scan()
    OUT.write_text(json.dumps(r, indent=1) + "\n")
    print(f"{r['tests']} tests on 2010-2017; {r['passing_selection']} pass |t| > {T_SEL} and |mean| > 2 x cost; carried {len(r['carried'])}")
    for c in r["top15_by_abs_t"]:
        mark = "CARRIED" if c in r["carried"] else ""
        print(f"  {c['family']} {c['pair']:6} {c['future']:4} hour {c['hour']:02d} UTC {c['weekday'] or 'all':3}  n {c['n']:5}  mean {c['mean']:+6.2f} bps"
              f"  sd {c['sd']:5.1f}  t {c['t']:+5.2f}  cost {c['cost']}  {mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
