"""DST correctness for the session mapper. CLAUDE_FUTURES.md §2.

FUTURES_STRATEGY_HYPOTHESES.md calls DST handling "the single most likely source of a
silent bug in this catalog," and it is right: half the hypotheses are session-anchored, the
US and Europe shift on different dates, and a one-hour error during the divergence weeks
produces real returns from the wrong hour — which no downstream check would flag.

So the transition dates are written down as literals here and asserted against, rather than
computed from the same library the module uses. A test that derives its expectations the
same way the code does proves only that the code is self-consistent.

    US   second Sunday in March    -> first Sunday in November
    EU   last Sunday in March      -> last Sunday in October

The dates below are those rules evaluated by hand for 2024-2026.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from futuresres.session.calendar import (
    ET,
    HARD_EXIT,
    SESSIONS,
    cme_trading_day,
    divergence_days,
    et_time_of,
    eu_dst,
    offsets_diverge,
    us_dst,
)

# Hand-evaluated from the statutory rules, not read back from zoneinfo.
US_DST_START = {2024: date(2024, 3, 10), 2025: date(2025, 3, 9), 2026: date(2026, 3, 8)}
US_DST_END   = {2024: date(2024, 11, 3), 2025: date(2025, 11, 2), 2026: date(2026, 11, 1)}
EU_DST_START = {2024: date(2024, 3, 31), 2025: date(2025, 3, 30), 2026: date(2026, 3, 29)}
EU_DST_END   = {2024: date(2024, 10, 27), 2025: date(2025, 10, 26), 2026: date(2026, 10, 25)}

YEARS = (2024, 2025, 2026)


# ── the transition dates themselves ──────────────────────────────────────────


@pytest.mark.integrity
@pytest.mark.parametrize("year", YEARS)
def test_us_transitions_match_the_statutory_rule(year: int) -> None:
    start, end = US_DST_START[year], US_DST_END[year]
    assert not us_dst(start - timedelta(days=1)), f"{year}: DST began too early"
    assert us_dst(start), f"{year}: DST did not begin on {start}"
    assert us_dst(end - timedelta(days=1)), f"{year}: DST ended too early"
    assert not us_dst(end), f"{year}: DST did not end on {end}"


@pytest.mark.integrity
@pytest.mark.parametrize("year", YEARS)
def test_eu_transitions_match_the_statutory_rule(year: int) -> None:
    start, end = EU_DST_START[year], EU_DST_END[year]
    assert not eu_dst(start - timedelta(days=1))
    assert eu_dst(start)
    assert eu_dst(end - timedelta(days=1))
    assert not eu_dst(end)


# ── the divergence windows ───────────────────────────────────────────────────


@pytest.mark.integrity
@pytest.mark.parametrize("year", YEARS)
def test_divergence_windows_are_exactly_where_expected(year: int) -> None:
    """Divergence runs US-start -> EU-start in spring and EU-end -> US-end in autumn."""
    spring = {US_DST_START[year] + timedelta(days=i)
              for i in range((EU_DST_START[year] - US_DST_START[year]).days)}
    autumn = {EU_DST_END[year] + timedelta(days=i)
              for i in range((US_DST_END[year] - EU_DST_END[year]).days)}
    assert set(divergence_days(year)) == spring | autumn


@pytest.mark.integrity
@pytest.mark.parametrize("year", YEARS)
def test_divergence_is_about_four_weeks_a_year(year: int) -> None:
    """The blast radius of getting this wrong: ~8% of trading days, every year."""
    n = len(divergence_days(year))
    assert 25 <= n <= 30, f"{year}: {n} divergent days, expected ~28"


# ── London: the anchor the catalog got backwards ─────────────────────────────


@pytest.mark.integrity
@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2026, 1, 15), time(3, 0)),    # both on standard time
        (date(2026, 7, 15), time(3, 0)),    # both on summer time
        (date(2026, 3, 9),  time(4, 0)),    # spring divergence, day after US springs
        (date(2026, 3, 20), time(4, 0)),    # mid spring divergence
        (date(2026, 3, 28), time(4, 0)),    # last day before EU springs
        (date(2026, 3, 29), time(3, 0)),    # EU springs forward, back in step
        (date(2026, 10, 25), time(4, 0)),   # EU falls back, autumn divergence opens
        (date(2026, 10, 31), time(4, 0)),   # last day before US falls back
        (date(2026, 11, 1),  time(3, 0)),   # US falls back, back in step
    ],
)
def test_london_open_in_et(day: date, expected: time) -> None:
    assert et_time_of("london_open", day) == expected


@pytest.mark.integrity
@pytest.mark.parametrize("year", YEARS)
def test_london_open_is_never_02_00_et(year: int) -> None:
    """The catalog's claimed divergence value. It cannot occur, and here is why.

    02:00 ET requires Europe on summer time while the US is on standard time. EU summer
    time (last Sunday March -> last Sunday October) is entirely nested inside US daylight
    time (second Sunday March -> first Sunday November), so that combination never exists.
    Asserted over every day of three years rather than argued.
    """
    day = date(year, 1, 1)
    seen: set[time] = set()
    while day.year == year:
        seen.add(et_time_of("london_open", day))
        day += timedelta(days=1)
    assert seen == {time(3, 0), time(4, 0)}, (
        f"{year}: London open landed on {sorted(seen)} in ET. The catalog says 02:00 "
        f"occurs during divergence; it is 04:00, and 02:00 is unreachable."
    )


@pytest.mark.integrity
@pytest.mark.parametrize("year", YEARS)
def test_a_fixed_et_offset_would_be_wrong_on_every_divergent_day(year: int) -> None:
    """Quantifies what the local-time anchor buys: the number of days it saves."""
    wrong = [d for d in divergence_days(year) if et_time_of("london_open", d) != time(3, 0)]
    assert len(wrong) == len(divergence_days(year))
    assert all(et_time_of("london_open", d) == time(4, 0) for d in wrong)


# ── Tokyo: no DST of its own, so it moves only with New York ─────────────────


@pytest.mark.integrity
@pytest.mark.parametrize(
    "day,expected",
    [(date(2026, 1, 15), time(19, 0)), (date(2026, 7, 15), time(20, 0))],
)
def test_tokyo_open_in_et(day: date, expected: time) -> None:
    assert et_time_of("tokyo_open", day) == expected


@pytest.mark.integrity
def test_tokyo_open_lands_on_the_previous_calendar_day_in_et() -> None:
    """09:00 JST is the evening before in New York — an off-by-one-day trap."""
    day = date(2026, 7, 15)
    assert SESSIONS["tokyo_open"].in_et(day).date() == date(2026, 7, 14)


@pytest.mark.integrity
@pytest.mark.parametrize("year", YEARS)
def test_tokyo_open_takes_exactly_two_et_values(year: int) -> None:
    day = date(year, 1, 1)
    seen: set[time] = set()
    while day.year == year:
        seen.add(et_time_of("tokyo_open", day))
        day += timedelta(days=1)
    assert seen == {time(19, 0), time(20, 0)}


# ── US anchors and the prop constraint ───────────────────────────────────────


@pytest.mark.integrity
@pytest.mark.parametrize("year", YEARS)
def test_us_anchors_are_fixed_in_et_all_year(year: int) -> None:
    """ET-anchored sessions never move in ET — including across both transitions."""
    day = date(year, 1, 1)
    while day.year == year:
        assert et_time_of("us_cash_open", day) == time(9, 30)
        assert et_time_of("us_cash_close", day) == time(16, 0)
        assert et_time_of("hard_exit", day) == time(17, 0)
        day += timedelta(days=1)


@pytest.mark.integrity
@pytest.mark.parametrize("year", YEARS)
def test_cme_open_is_18_00_et_every_day_despite_being_chicago_anchored(year: int) -> None:
    """Chicago and New York shift together, so 17:00 CT is 18:00 ET on every date.

    The anchor is defined in Chicago local time deliberately — writing 18:00 ET would be a
    fixed offset that happens to be correct, which is the habit the module exists to break.
    This test is what makes the indirection safe rather than merely principled.
    """
    day = date(year, 1, 1)
    while day.year == year:
        assert et_time_of("cme_open", day) == time(18, 0), day
        day += timedelta(days=1)


@pytest.mark.integrity
def test_hard_exit_is_one_hour_after_the_cash_close() -> None:
    day = date(2026, 6, 15)
    gap = HARD_EXIT.in_utc(day) - SESSIONS["us_cash_close"].in_utc(day)
    assert gap == timedelta(hours=1)


# ── the CME trading day ──────────────────────────────────────────────────────


@pytest.mark.integrity
@pytest.mark.parametrize(
    "et_wall,expected",
    [
        ((2026, 6, 15, 19, 0), date(2026, 6, 16)),   # Asia session -> next trading day
        ((2026, 6, 15, 23, 30), date(2026, 6, 16)),
        ((2026, 6, 16, 3, 0), date(2026, 6, 16)),    # London, same trading day
        ((2026, 6, 16, 9, 30), date(2026, 6, 16)),   # RTH
        ((2026, 6, 16, 16, 59), date(2026, 6, 16)),  # before the hard exit
        ((2026, 6, 16, 18, 0), date(2026, 6, 17)),   # CME reopens -> next again
    ],
)
def test_cme_trading_day_boundaries(et_wall: tuple, expected: date) -> None:
    assert cme_trading_day(datetime(*et_wall, tzinfo=ET)) == expected


@pytest.mark.integrity
def test_an_overnight_hypothesis_never_crosses_a_settlement() -> None:
    """The catalog's claim that the 17:00 exit is less binding than it looks.

    An Asia entry at 19:00 ET and a four-hour hold sits inside one trading day, so the hard
    exit never bites. Asserted rather than trusted, because it is the reason the overnight
    hypotheses are registered at all.
    """
    entry = datetime(2026, 6, 15, 19, 0, tzinfo=ET)
    exit_ = entry + timedelta(hours=4)
    assert cme_trading_day(entry) == cme_trading_day(exit_)
    assert exit_ < HARD_EXIT.at(cme_trading_day(entry))


# ── the guard against anchors inside a transition hour ───────────────────────


@pytest.mark.integrity
def test_a_nonexistent_local_time_is_refused_not_silently_moved() -> None:
    """02:30 does not exist in New York on a spring-forward date."""
    from futuresres.session.calendar import Anchor, _localize

    with pytest.raises(ValueError, match="does not exist"):
        _localize(date(2026, 3, 8), time(2, 30), ET, "test_anchor")


@pytest.mark.integrity
def test_an_ambiguous_local_time_is_refused() -> None:
    """01:30 occurs twice in New York on a fall-back date."""
    from futuresres.session.calendar import _localize

    with pytest.raises(ValueError, match="ambiguous"):
        _localize(date(2026, 11, 1), time(1, 30), ET, "test_anchor")


@pytest.mark.integrity
def test_every_registered_anchor_is_safe_on_every_transition_date() -> None:
    """No currently-defined anchor may sit in a gap or an overlap, in any year tested."""
    for year in YEARS:
        for day in (US_DST_START[year], US_DST_END[year],
                    EU_DST_START[year], EU_DST_END[year]):
            for name, anchor in SESSIONS.items():
                anchor.at(day)          # raises if the anchor is unsafe
