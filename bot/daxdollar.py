"""The DAX-dollar rule (decisions.md 445-448; D171/D174/D175): the next FDXM ticket takes the sign of today's dollar move (Yahoo
DX-Y.NYB daily bar, open -> latest, read at the 17:30 ET alert) - LONG after the dollar rises, SHORT after it falls. Every day.
If the data cannot be read, or the dollar is unchanged: long (the plan unchanged)."""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def dollar_today(alert_day: dt.date) -> float | None:
    u = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1d&range=1mo"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    for t, o, c in zip(d["timestamp"], q["open"], q["close"]):
        if dt.datetime.fromtimestamp(t, ET).date() == alert_day and o and c:
            return (c / o - 1) * 1e4
    return None


def fdxm_side(alert_day: dt.date, move_bps: float | None = None, fetch: bool = True) -> tuple[str, str]:
    """('long' | 'short', reason) for the FDXM ticket issued at the alert on alert_day."""
    try:
        r = move_bps if move_bps is not None or not fetch else dollar_today(alert_day)
        if r is None:
            return "long", "DAX-dollar: today's dollar move not found -> long"
        if r == 0:
            return "long", "DAX-dollar: dollar unchanged -> long"
        side = "long" if r > 0 else "short"
        return side, f"DAX-dollar: dollar index today {r:+.0f} bps -> FDXM {side.upper()}"
    except Exception as e:                              # never block the alert
        return "long", f"DAX-dollar: dollar check failed ({type(e).__name__}) -> long"
