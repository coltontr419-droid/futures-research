"""Shadow tracking: how each issued ticket played out, whether or not it was traded. Free Yahoo Finance 1-minute
bars (NQ=F, GC=F, CL=F - the same prices as MNQ, MGC, MCL; ~7 days of history), plain Python. Same rules as the
backtests: entry at the open of the entry minute's bar, take / stop at their prices, a bar touching both counts as the
STOP, otherwise out at the close of the bar before the exit time; commissions charged. decisions.md 125.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
YAHOO = {"MNQ": "NQ=F", "MGC": "GC=F", "MCL": "CL=F", "NKD": "NKD=F", "FDXM": "^GDAXI",   # FDXM tracked on the DAX index
         "ZS": "ZS=F"}   # soybeans, cents a bushel; Yahoo's continuous series can mix two months near a roll (decisions.md 140)


def bars(product: str, start: dt.datetime, end: dt.datetime) -> list[tuple[dt.datetime, float, float, float, float]]:
    """1-minute (time ET, open, high, low, close) from Yahoo between start and end (ET-aware datetimes)."""
    from accounts import base
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{YAHOO[base(product)]}?interval=1m"
           f"&period1={int(start.timestamp()) - 60}&period2={int(end.timestamp()) + 60}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    r = d["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(r.get("timestamp") or []):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        ts = dt.datetime.fromtimestamp(t, ET).replace(second=0, microsecond=0)
        if start <= ts < end:
            out.append((ts, float(o), float(h), float(l), float(c)))
    return out


def simulate(b: list, side: str, take_pts: float, stop_pts: float, n: int, mult: float, rt: float) -> dict:
    """Outcome of one ticket on its window's bars (b sorted, first bar = the entry minute)."""
    if not b:
        return {"outcome": "NO DATA"}
    entry = b[0][1]
    sgn = 1.0 if side == "long" else -1.0
    take_px = entry + sgn * take_pts; stop_px = entry - sgn * stop_pts
    cost = rt * n
    for ts, o, h, l, c in b:
        hit_take = h >= take_px if sgn > 0 else l <= take_px
        hit_stop = l <= stop_px if sgn > 0 else h >= stop_px
        if hit_stop:                                   # a bar touching both counts as the stop (as the backtests)
            return {"outcome": "STOP", "time": ts.strftime("%H:%M"), "entry": entry, "exit": stop_px,
                    "pnl": round(-stop_pts * mult * n - cost, 2)}
        if hit_take:
            return {"outcome": "TAKE", "time": ts.strftime("%H:%M"), "entry": entry, "exit": take_px,
                    "pnl": round(take_pts * mult * n - cost, 2)}
    last = b[-1][4]
    return {"outcome": "TIME EXIT", "time": b[-1][0].strftime("%H:%M"), "entry": entry, "exit": last,
            "pnl": round(sgn * (last - entry) * mult * n - cost, 2)}
