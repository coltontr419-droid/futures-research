"""Session mapping across time zones. CLAUDE_FUTURES.md §2.

LOAD-BEARING INFRASTRUCTURE, NOT A UTILITY. Half this catalog is session-anchored. Europe
and the United States change clocks on different dates, so for several weeks a year the gap
between London and New York is four hours rather than five. A one-hour misalignment during
those weeks produces results that look real and are not, and it would be invisible in every
downstream check — the returns are real returns, just of the wrong hour.

THE RULE: anchor to exchange LOCAL time and convert. Never store a session as a fixed ET
offset. `SESSIONS` below is defined entirely in local time; the ET expression is derived.

    London cash opens at 08:00 Europe/London. That is 03:00 ET for most of the year and
    04:00 ET during the divergence weeks. The 08:00 is the fact; the 03:00 is a consequence.

A CORRECTION TO THE CATALOG. FUTURES_STRATEGY_HYPOTHESES.md states that the London open
"sits at 03:00 ET most of the year and 02:00 ET for a few weeks each spring and autumn."
The direction is inverted: it is **04:00 ET**, never 02:00. During divergence the US has
sprung forward and Europe has not, so the ET clock has moved toward UTC while London's has
not, and London's fixed local open lands one hour LATER in ET, not earlier.

02:00 ET would require Europe on summer time while the US is on standard time. That
combination never occurs: EU summer time (last Sunday March to last Sunday October) is
entirely nested inside US daylight time (second Sunday March to first Sunday November).
`test_session_calendar.py` asserts the 04:00 result and asserts 02:00 never happens, so the
catalog's number cannot be reintroduced by someone trusting the prose.

WHY CME IS ANCHORED TO CHICAGO. The exchange is in Chicago and Globex opens 17:00 CT. That
is 18:00 ET on every date, because both US zones shift together — but it is anchored to
Chicago anyway, and a test asserts the equivalence holds year-round. Writing "18:00 ET"
directly would be a fixed offset that happens to be right, which is the habit this module
exists to break.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

ET: Final[ZoneInfo] = ZoneInfo("America/New_York")
CT: Final[ZoneInfo] = ZoneInfo("America/Chicago")
LONDON: Final[ZoneInfo] = ZoneInfo("Europe/London")
TOKYO: Final[ZoneInfo] = ZoneInfo("Asia/Tokyo")
UTC: Final[ZoneInfo] = ZoneInfo("UTC")


@dataclass(frozen=True, slots=True)
class Anchor:
    """One session boundary, defined in the exchange's own local time."""

    name: str
    zone: ZoneInfo
    local: time
    description: str

    def at(self, day: date) -> datetime:
        """The instant this anchor occurs on `day`, as a tz-aware datetime in its zone."""
        return _localize(day, self.local, self.zone, self.name)

    def in_et(self, day: date) -> datetime:
        return self.at(day).astimezone(ET)

    def in_utc(self, day: date) -> datetime:
        return self.at(day).astimezone(UTC)


def _localize(day: date, wall: time, zone: ZoneInfo, label: str) -> datetime:
    """Attach `zone` to a local wall-clock time, refusing times that do not exist.

    A spring-forward gap makes some wall-clock times nonexistent, and a fall-back overlap
    makes others ambiguous. Python resolves both silently — `fold=0` picks one and moves on
    — which is precisely how a session anchor ends up an hour wrong twice a year. Every
    anchor currently defined sits far from any transition hour, so this never fires today;
    it exists so that adding an anchor at 01:30 or 02:30 local fails loudly instead.
    """
    naive = datetime.combine(day, wall)
    attached = naive.replace(tzinfo=zone)
    # A nonexistent time does not survive a round trip through UTC.
    if attached.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != naive:
        raise ValueError(
            f"{label}: {naive} does not exist in {zone.key} — it falls in a "
            f"spring-forward gap. Choose an anchor outside the transition hour."
        )
    # An ambiguous time has two distinct UTC instants; fold=1 differs from fold=0.
    if attached.utcoffset() != attached.replace(fold=1).utcoffset():
        raise ValueError(
            f"{label}: {naive} is ambiguous in {zone.key} — it occurs twice on a "
            f"fall-back date. Choose an anchor outside the transition hour."
        )
    return attached


#: Every session boundary this project uses, in local time. Order is the trading day's.
SESSIONS: Final[dict[str, Anchor]] = {
    "cme_open": Anchor(
        "cme_open", CT, time(17, 0),
        "CME Globex opens; a new trading day begins (18:00 ET)",
    ),
    "tokyo_open": Anchor(
        "tokyo_open", TOKYO, time(9, 0),
        "Tokyo cash open (19:00 ET winter / 20:00 ET summer)",
    ),
    "london_open": Anchor(
        "london_open", LONDON, time(8, 0),
        "London cash open (03:00 ET, 04:00 ET in divergence weeks)",
    ),
    "us_cash_open": Anchor(
        "us_cash_open", ET, time(9, 30), "US cash open, RTH begins",
    ),
    "us_cash_close": Anchor(
        "us_cash_close", ET, time(16, 0), "US cash close, RTH ends",
    ),
    "hard_exit": Anchor(
        "hard_exit", ET, time(17, 0),
        "PROP CONSTRAINT — flat by this time, no exceptions",
    ),
}

#: The prop account's hard flat-by time. Named separately because it is a rule, not a
#: description of the market: §2 treats a position open after it as a failed backtest.
HARD_EXIT: Final[Anchor] = SESSIONS["hard_exit"]


def et_time_of(session: str, day: date) -> time:
    """The ET wall-clock time a session anchor lands on for a given date."""
    return SESSIONS[session].in_et(day).timetz().replace(tzinfo=None)


def us_dst(day: date) -> bool:
    """Is New York on daylight time on this date? Measured at noon, away from transitions."""
    return datetime.combine(day, time(12, 0), ET).dst() != timedelta(0)


def eu_dst(day: date) -> bool:
    """Is London on summer time on this date?"""
    return datetime.combine(day, time(12, 0), LONDON).dst() != timedelta(0)


def offsets_diverge(day: date) -> bool:
    """True on dates where the US and Europe are NOT in the same DST state.

    These are the weeks a fixed ET offset for a European session is wrong. There are two
    such windows a year: roughly three weeks in spring (US springs forward first) and one
    in autumn (Europe falls back first).
    """
    return us_dst(day) != eu_dst(day)


def divergence_days(year: int) -> list[date]:
    """Every date in `year` where the US and EU DST states differ."""
    day = date(year, 1, 1)
    out: list[date] = []
    while day.year == year:
        if offsets_diverge(day):
            out.append(day)
        day += timedelta(days=1)
    return out


def cme_trading_day(instant: datetime) -> date:
    """The CME trading day an instant belongs to.

    The trading day runs from 18:00 ET to 17:00 ET the following calendar day, so an Asia
    session opening at 19:00 ET on Monday belongs to Tuesday's trading day. This is what
    makes an overnight hypothesis compatible with the hard exit: it opens after the CME
    open and closes before the next 17:00, never crossing a settlement.
    """
    local = instant.astimezone(ET)
    day = local.date()
    return day + timedelta(days=1) if local.hour >= 18 else day


def session_window(session_open: str, session_close: str, day: date) -> tuple[datetime, datetime]:
    """(open, close) as UTC instants, for slicing a bar series."""
    return SESSIONS[session_open].in_utc(day), SESSIONS[session_close].in_utc(day)


def describe(day: date) -> str:
    """One line per anchor, for eyeballing a date. Used in reports, not in logic."""
    rows = [f"{day.isoformat()}  US_DST={us_dst(day)}  EU_DST={eu_dst(day)}"
            f"  diverged={offsets_diverge(day)}"]
    for name, anchor in SESSIONS.items():
        local = anchor.at(day)
        rows.append(
            f"  {name:<14} {local.strftime('%H:%M %Z'):>12} "
            f"-> {anchor.in_et(day).strftime('%H:%M %Z'):>10}"
        )
    return "\n".join(rows)
