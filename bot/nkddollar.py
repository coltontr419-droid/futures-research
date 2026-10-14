"""The NKD dollar-week rule (decisions.md 451-454; D227): the next NKD ticket follows the euro's (6E=F, Yahoo daily, open -> close)
summed move over the last 5 sessions through today - LONG after a week of dollar weakness (euro up), SHORT after a week of dollar
strength. Every day. Replaced D139 on the NKD ticket (decisions.md 454). If today's session or 5 sessions cannot be read: long."""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def euro_sessions() -> list:
    u = "https://query1.finance.yahoo.com/v8/finance/chart/6E=F?interval=1d&range=1mo"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())["chart"]["result"][0]
    q = d["indicators"]["quote"][0]; out = []
    for t, o, c in zip(d["timestamp"], q["open"], q["close"]):
        day = dt.datetime.fromtimestamp(t, ET).date()
        if o and c and day.weekday() < 5:
            out.append((day, (c / o - 1) * 1e4))
    return out


def nkd_side(alert_day: dt.date, sessions: list | None = None) -> tuple[str, str]:
    """('long' | 'short', reason) for the NKD ticket issued at the alert on alert_day."""
    try:
        s = sessions if sessions is not None else euro_sessions()
        idx = [i for i, (d, _) in enumerate(s) if d == alert_day]
        if not idx or idx[0] < 4:
            return "long", "dollar-week: today's euro session not found -> long"
        week = sum(x for _, x in s[idx[0] - 4:idx[0] + 1])
        if week == 0:
            return "long", "dollar-week: euro unchanged over the week -> long"
        side = "long" if week > 0 else "short"
        return side, f"dollar-week: euro {week:+.0f} bps over 5 sessions (dollar {'weaker' if week > 0 else 'stronger'}) -> NKD {side.upper()}"
    except Exception as e:                              # never block the alert
        return "long", f"dollar-week: euro check failed ({type(e).__name__}) -> long"
