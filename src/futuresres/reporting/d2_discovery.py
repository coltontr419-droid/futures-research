"""D-series family 2 discovery (decisions.md 132-134): 30-minute windows before and after scheduled fixings, opens and
closes, on 2010-2017 ONLY. A SCAN, not a trial. Selection per the user's amendment (decisions.md 133): two-sided |t| > 1.96
(uncorrected) and |mean| > 2 x cost; every passing cell carried.

    python -m futuresres.reporting.d2_discovery
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from futuresres.data.fx_fix import quarter_marks

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d2_discovery.json"
UTC = dt.timezone.utc
LDN, NY, TKY, FRA = ZoneInfo("Europe/London"), ZoneInfo("America/New_York"), ZoneInfo("Asia/Tokyo"), ZoneInfo("Europe/Berlin")
COST = {"gbpusd": 0.8, "audusd": 0.8, "usdcad": 0.8, "usdchf": 0.8, "grxeur": 1.0, "jpxjpy": 1.0, "xagusd": 1.5}
FUT = {"gbpusd": "6B", "audusd": "6A", "usdcad": "6C", "usdchf": "6S", "grxeur": "FDAX", "jpxjpy": "NKD", "xagusd": "SI"}
T_SEL = 1.96
DISC = (dt.date(2010, 1, 1), dt.date(2017, 12, 31))


def _w(pair, label, tz, hh, mm, before: bool):
    """A 30-minute window ending (before=True) or starting at the local event time."""
    return {"pair": pair, "label": f"{label} {'before' if before else 'after'}", "tz": tz, "hh": hh, "mm": mm, "before": before}


def windows() -> list[dict]:
    w = []
    for p in ("gbpusd", "audusd", "usdcad", "usdchf"):
        for b in (True, False):
            w.append(_w(p, "WM/R 16:00 London fix", LDN, 16, 0, b))
            w.append(_w(p, "Tokyo 09:55 fix", TKY, 9, 55, b))
    for b in (True, False):
        w.append(_w("usdcad", "Bank of Canada 16:30 NY rate", NY, 16, 30, b))
    w.append(_w("xagusd", "COMEX settlement 13:25 NY", NY, 13, 25, True))
    w.append(_w("xagusd", "COMEX settlement 13:25 NY", NY, 13, 25, False))
    w.append(_w("xagusd", "London silver fix 12:00", LDN, 12, 0, False))     # the before-window is D01's
    w.append(_w("grxeur", "Xetra open 09:00", FRA, 9, 0, False))
    w.append(_w("grxeur", "US open 15:30 Frankfurt", FRA, 15, 30, False))
    w.append(_w("grxeur", "Xetra close auction 17:30", FRA, 17, 30, True))
    w.append(_w("grxeur", "Xetra close auction 17:30", FRA, 17, 30, False))
    w.append(_w("jpxjpy", "Tokyo open 09:00", TKY, 9, 0, False))
    w.append(_w("jpxjpy", "Tokyo morning close 11:30", TKY, 11, 30, True))
    w.append(_w("jpxjpy", "Tokyo afternoon open 12:30", TKY, 12, 30, False))
    w.append(_w("jpxjpy", "Tokyo close 15:00", TKY, 15, 0, True))
    return w


def _span(win: dict, day: dt.date):
    ev = dt.datetime.combine(day, dt.time(win["hh"], win["mm"]), win["tz"]).astimezone(UTC)
    return (ev - dt.timedelta(minutes=30), ev) if win["before"] else (ev, ev + dt.timedelta(minutes=30))


def _cme_break(a: dt.datetime, b: dt.datetime) -> bool:
    """True if [a, b) overlaps 17:00-18:00 New York."""
    la, lb = a.astimezone(NY), b.astimezone(NY)
    for d in {la.date(), lb.date()}:
        s = dt.datetime.combine(d, dt.time(17, 0), NY); e = s + dt.timedelta(hours=1)
        if la < e and lb > s:
            return True
    return False


def _last_weekdays(d0: dt.date, d1: dt.date) -> set:
    out, d = set(), d0
    while d <= d1:
        nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        last = nxt - dt.timedelta(days=1)
        while last.weekday() >= 5:
            last -= dt.timedelta(days=1)
        out.add(last); d = nxt
    return out


def returns(win: dict, marks: dict, d0: dt.date, d1: dt.date) -> tuple[list, np.ndarray]:
    days, r = [], []
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            a, b = _span(win, d)
            if a in marks and b in marks:
                days.append(d); r.append((marks[b] / marks[a] - 1) * 1e4)
        d += dt.timedelta(days=1)
    return days, np.array(r)


def _stats(x: np.ndarray) -> dict:
    if len(x) < 30:
        return {"n": int(len(x))}
    return {"n": int(len(x)), "mean": float(x.mean()), "sd": float(x.std(ddof=1)), "t": float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))}


def scan() -> dict:
    cells, skipped = [], []
    me = _last_weekdays(*DISC)
    cache = {}
    for win in windows():
        p = win["pair"]
        a, b = _span(win, dt.date(2016, 1, 15)); a2, b2 = _span(win, dt.date(2016, 7, 15))
        if _cme_break(a, b) or _cme_break(a2, b2):
            skipped.append(win["label"] + " " + p); continue
        if p not in cache:
            cache[p] = quarter_marks(p)
        days, r = returns(win, cache[p], *DISC)
        assert not days or max(days) <= DISC[1], "discovery read past 2017"
        m = np.array([d in me for d in days])
        for dayset, x in (("all weekdays", r), ("month-end", r[m] if len(r) else r)):
            cells.append({"pair": p, "future": FUT[p], "cost": COST[p], "window": win["label"], "dayset": dayset,
                          "tz": str(win["tz"]), "hh": win["hh"], "mm": win["mm"], "before": win["before"], **_stats(x)})
    tests = [c for c in cells if "t" in c]
    passing = sorted([c for c in tests if abs(c["t"]) > T_SEL and abs(c["mean"]) > 2 * c["cost"]], key=lambda c: -abs(c["t"]))
    carried = []
    for c in passing:
        if c["dayset"] == "month-end" and any(k["pair"] == c["pair"] and k["window"] == c["window"] and k["dayset"] == "all weekdays" for k in carried):
            continue
        carried.append(c)
    return {"window": ["2010-01-01", "2017-12-31"], "tests": len(tests), "expected_chance_passes_5pct": round(0.05 * len(tests), 1),
            "skipped_cme_break": skipped, "passing": len(passing), "carried": carried,
            "all_cells": sorted(tests, key=lambda c: -abs(c["t"]))}


def main(argv=None) -> int:
    r = scan()
    OUT.write_text(json.dumps(r, indent=1) + "\n")
    print(f"{r['tests']} tests (2010-17); ~{r['expected_chance_passes_5pct']} would pass |t|>1.96 by chance; "
          f"{r['passing']} pass |t|>1.96 and |mean|>2x cost; carried {len(r['carried'])}; skipped (CME break): {r['skipped_cme_break']}")
    for c in r["all_cells"][:20]:
        mark = "CARRIED" if c in r["carried"] else ""
        print(f"  {c['pair']:6} {c['future']:4} {c['window']:38} {c['dayset']:12} n {c['n']:5} mean {c['mean']:+6.2f} bps sd {c['sd']:5.1f} "
              f"t {c['t']:+5.2f} cost {c['cost']} {mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
