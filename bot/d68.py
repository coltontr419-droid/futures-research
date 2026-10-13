"""D68 (decisions.md 209-211): after a 10-year-note (ZN) session beyond 2 sigma (SD of its previous 60 sessions, open -> settlement,
Yahoo daily ZN=F), the next MNQ ticket takes the shock's direction - LONG after a bond rally, SHORT after a bond sell-off. Any
other day, or if the data cannot be read: long (the plan unchanged)."""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def zn_sessions() -> list:
    u = "https://query1.finance.yahoo.com/v8/finance/chart/ZN=F?interval=1d&range=6mo"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())["chart"]["result"][0]
    q = d["indicators"]["quote"][0]; out = []
    for t, o, c in zip(d["timestamp"], q["open"], q["close"]):
        if o and c:
            out.append((dt.datetime.fromtimestamp(t, ET).date(), (c / o - 1) * 1e4))
    return out


def mnq_side(alert_day: dt.date, sessions: list | None = None) -> tuple[str, str]:
    """('long' | 'short', reason) for the MNQ ticket issued at the alert on alert_day (today's ZN session must be complete)."""
    try:
        s = sessions if sessions is not None else zn_sessions()
        idx = [i for i, (d, _) in enumerate(s) if d == alert_day]
        if not idx or idx[0] < 60:
            return "long", "no ZN shock (today's ZN session not found)"
        i = idx[0]; r = s[i][1]
        prev = [x for _, x in s[i - 60:i]]; m = sum(prev) / 60
        sd = (sum((x - m) ** 2 for x in prev) / 59) ** 0.5
        if abs(r) > 2 * sd:
            side = "long" if r > 0 else "short"
            return side, f"D68: ZN shock today {r:+.0f} bps (2 sigma = {2 * sd:.0f}) -> MNQ {side.upper()}"
        return "long", f"no ZN shock (today {r:+.0f} bps, 2 sigma = {2 * sd:.0f})"
    except Exception as e:                              # never block the alert
        return "long", f"no ZN shock check ({type(e).__name__})"
