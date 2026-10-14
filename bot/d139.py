"""D139 (decisions.md 429-432): after a CME bitcoin-futures (BTC=F) session beyond 2 sigma (SD of its previous 60 sessions, open ->
close, Yahoo daily), the next NKD ticket FADES it - SHORT after a bitcoin rally, LONG after a bitcoin sell-off. Any other day, or if
the data cannot be read: long (the plan unchanged)."""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def btc_sessions() -> list:
    u = "https://query1.finance.yahoo.com/v8/finance/chart/BTC=F?interval=1d&range=6mo"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())["chart"]["result"][0]
    q = d["indicators"]["quote"][0]; out = []
    for t, o, c in zip(d["timestamp"], q["open"], q["close"]):
        if o and c:
            out.append((dt.datetime.fromtimestamp(t, ET).date(), (c / o - 1) * 1e4))
    return out


def nkd_side(alert_day: dt.date, sessions: list | None = None) -> tuple[str, str]:
    """('long' | 'short', reason) for the NKD ticket issued at the alert on alert_day (today's BTC=F session must be complete)."""
    try:
        s = sessions if sessions is not None else btc_sessions()
        idx = [i for i, (d, _) in enumerate(s) if d == alert_day]
        if not idx or idx[0] < 60:
            return "long", "no bitcoin shock (today's BTC=F session not found)"
        i = idx[0]; r = s[i][1]
        prev = [x for _, x in s[i - 60:i]]; m = sum(prev) / 60
        sd = (sum((x - m) ** 2 for x in prev) / 59) ** 0.5
        if abs(r) > 2 * sd:
            side = "short" if r > 0 else "long"
            return side, f"D139: bitcoin shock today {r:+.0f} bps (2 sigma = {2 * sd:.0f}) -> NKD {side.upper()} (fade)"
        return "long", f"no bitcoin shock (today {r:+.0f} bps, 2 sigma = {2 * sd:.0f})"
    except Exception as e:                              # never block the alert
        return "long", f"no bitcoin shock check ({type(e).__name__})"
