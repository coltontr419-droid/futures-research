"""D-series family 5 - the calendar (decisions.md 155): does a day's place in the week, month or year set the direction of the
plan's windows? A SCAN on 2010-06 -> 2017-12 over the family-3 window returns (d3_relay table).

    python -m futuresres.reporting.d5_calendar --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d5_discovery.json"
DISC, VAL = d3.DISC, d3.VAL
TARGETS = ("NKD_win", "DAX_win", "MGC_win", "MNQ_win", "MCL", "ZS")
CELLS = ("Mon", "Tue", "Wed", "Thu", "Fri", "month_last", "month_first3", "pre_holiday", "post_holiday", "opex_friday",
         "opex_week", "quarter_last5")


def us_trading_days(S: dict) -> list:
    return sorted(set(S["MNQ_win"]) | set(S["MCL"]))


def calendar(S: dict) -> dict:
    """date -> set of cells, for every weekday in the data's span (US trading-day structure from MNQ and MCL)."""
    td = us_trading_days(S); tds = set(td)
    lo, hi = td[0], td[-1]
    out = {}
    d = lo
    weekdays = []
    while d <= hi:
        if d.weekday() < 5:
            weekdays.append(d)
        d += dt.timedelta(days=1)
    holidays = {w for w in weekdays if w not in tds}
    by_month: dict = {}
    for t in td:
        by_month.setdefault((t.year, t.month), []).append(t)
    for (y, m), ds in by_month.items():
        ds.sort()
        for i, t in enumerate(ds):
            c = out.setdefault(t, set())
            c.add(("Mon", "Tue", "Wed", "Thu", "Fri")[t.weekday()])
            if i == len(ds) - 1:
                c.add("month_last")
            if i < 3:
                c.add("month_first3")
            if m in (3, 6, 9, 12) and i >= len(ds) - 5:
                c.add("quarter_last5")
    for t in td:
        nxt = t + dt.timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += dt.timedelta(days=1)
        if nxt in holidays:
            out[t].add("pre_holiday")
        prv = t - dt.timedelta(days=1)
        while prv.weekday() >= 5:
            prv -= dt.timedelta(days=1)
        if prv in holidays:
            out[t].add("post_holiday")
        third_fri = _third_friday(t.year, t.month)
        if t == third_fri:
            out[t].add("opex_friday")
        if third_fri - dt.timedelta(days=4) <= t < third_fri:
            out[t].add("opex_week")
    return out


def _third_friday(y: int, m: int) -> dt.date:
    d = dt.date(y, m, 1)
    while d.weekday() != 4:
        d += dt.timedelta(days=1)
    return d + dt.timedelta(days=14)


def cell_days(S: dict, target: str, cell: str, cal: dict, lo: dt.date, hi: dt.date):
    """(dates, raw target, in-cell mask) over the target's days in [lo, hi] that have a calendar entry."""
    D, Y, M = [], [], []
    for d, y in sorted(S[target].items()):
        if lo <= d <= hi and d in cal:
            D.append(d); Y.append(y); M.append(cell in cal[d])
    return np.array(D), np.array(Y), np.array(M)


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    S = d3.series(); cal = calendar(S); res = []
    for tg in TARGETS:
        for cell in CELLS:
            D, Y, M = cell_days(S, tg, cell, cal, *DISC)
            assert D.max() <= DISC[1], "discovery read sealed data"
            z = (Y - Y.mean())[M]
            res.append({"target": tg, "cell": cell, "n": int(M.sum()), "mean_bps": float(z.mean()), "sd_bps": float(z.std(ddof=1)),
                        "t": _t(z), "direction": "long" if z.mean() > 0 else "short"})
    res.sort(key=lambda r: -abs(r["t"]))
    carried = [r for r in res if abs(r["t"]) > 1.96]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_passes_5pct": round(0.05 * len(res), 1),
           "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests on {DISC[0]} -> {DISC[1]}; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res[:16]:
        print(f"  {r['target']:8} {r['cell']:14} n {r['n']:4} {r['direction']:5} vs ordinary day {r['mean_bps']:+7.2f} bps t {r['t']:+5.2f}"
              f"{'  CARRIED' if abs(r['t']) > 1.96 else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
