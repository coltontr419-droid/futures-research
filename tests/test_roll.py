"""Roll logic. CLAUDE_FUTURES.md §3.

Two layers. Synthetic series with a crossover placed on a KNOWN session pin the mechanics
exactly — the roll date, the dropped session, the monotonicity rule. Then the real batch is
checked against facts that hold independently of this implementation: an equity-index roll
lands in the days before the third Friday of the delivery month, a gold roll lands before
its delivery month begins, and no series ever rolls backwards.

The real-data checks are marked `slow` and skip when the parquet is absent, so the suite
still runs on a fresh checkout with no data.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from futuresres.data.parse import MONTH_NUMBER
from futuresres.data.roll import (
    ROOT,
    build_calendar,
    continuous_series,
    daily_volume,
    expiry_key,
    load_product,
)

PARQUET = ROOT / "data" / "parquet"
pytestmark_data = pytest.mark.skipif(
    not (PARQUET / "symbol=NQ").exists(), reason="batch not parsed into data/parquet"
)


def _bars(rows: list[tuple[str, str, int]]) -> pl.DataFrame:
    """(utc timestamp, contract, volume) -> a bar frame."""
    return pl.DataFrame({
        "ts_event": [datetime.fromisoformat(r[0]).replace(tzinfo=None) for r in rows],
        "contract": [r[1] for r in rows],
        "volume": [r[2] for r in rows],
        "open": [100.0] * len(rows), "high": [101.0] * len(rows),
        "low": [99.0] * len(rows), "close": [100.5] * len(rows),
    }).with_columns(pl.col("ts_event").dt.replace_time_zone("UTC"))


# ── expiry ordering ──────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_expiry_key_orders_contracts_across_a_decade_boundary() -> None:
    """The reason contracts carry a four-digit year: NQZ2015 must sort before NQZ2025."""
    codes = ["NQZ2025", "NQH2016", "NQZ2015", "NQM2016"]
    assert sorted(codes, key=expiry_key) == ["NQZ2015", "NQH2016", "NQM2016", "NQZ2025"]


# ── the crossover ────────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_roll_happens_on_the_session_volume_crosses() -> None:
    rows = []
    for day in range(10, 14):                       # 2026-03-10 .. 13, RTH bars
        front_vol = 1000 if day < 12 else 400
        next_vol = 200 if day < 12 else 900         # crosses on the 12th
        rows.append((f"2026-03-{day:02d}T15:00:00", "NQH2026", front_vol))
        rows.append((f"2026-03-{day:02d}T15:00:00", "NQM2026", next_vol))
    cal = build_calendar("NQ", daily_volume(_bars(rows)))
    assert len(cal.rolls) == 1
    roll = cal.rolls[0]
    assert roll.session == date(2026, 3, 12)
    assert (roll.from_contract, roll.to_contract) == ("NQH2026", "NQM2026")
    assert roll.from_volume == 400 and roll.to_volume == 900


@pytest.mark.integrity
def test_the_crossover_session_is_dropped_entirely() -> None:
    """Not stitched, not interpolated — removed. §3."""
    rows = []
    for day in range(10, 14):
        rows.append((f"2026-03-{day:02d}T15:00:00", "NQH2026", 1000 if day < 12 else 400))
        rows.append((f"2026-03-{day:02d}T15:00:00", "NQM2026", 200 if day < 12 else 900))
    bars = _bars(rows)
    cal = build_calendar("NQ", daily_volume(bars))
    series = continuous_series(bars, cal)
    sessions = set(series.get_column("session").to_list())
    assert date(2026, 3, 12) not in sessions, "the crossover session survived"
    assert sessions == {date(2026, 3, 10), date(2026, 3, 11), date(2026, 3, 13)}


@pytest.mark.integrity
def test_the_continuous_series_holds_only_the_front_contract() -> None:
    rows = []
    for day in range(10, 14):
        rows.append((f"2026-03-{day:02d}T15:00:00", "NQH2026", 1000 if day < 12 else 400))
        rows.append((f"2026-03-{day:02d}T15:00:00", "NQM2026", 200 if day < 12 else 900))
    bars = _bars(rows)
    series = continuous_series(bars, build_calendar("NQ", daily_volume(bars)))
    per = {r["session"]: r["contract"] for r in series.iter_rows(named=True)}
    assert per[date(2026, 3, 10)] == "NQH2026"
    assert per[date(2026, 3, 13)] == "NQM2026"


@pytest.mark.integrity
def test_the_front_never_rolls_backwards() -> None:
    """Volume is noisy near a roll; a backward roll would re-cross a gap already crossed."""
    rows = []
    for day, (front, nxt) in enumerate(
        [(1000, 200), (400, 900), (1200, 100), (300, 800)], start=10
    ):
        rows.append((f"2026-03-{day:02d}T15:00:00", "NQH2026", front))
        rows.append((f"2026-03-{day:02d}T15:00:00", "NQM2026", nxt))
    cal = build_calendar("NQ", daily_volume(_bars(rows)))
    assert len(cal.rolls) == 1, "it rolled back and forward"
    assert date(2026, 3, 12) in cal.contested, "the disagreement was not recorded"
    assert cal.front_by_session[date(2026, 3, 12)] == "NQM2026"


# ── sessions are trading days, not calendar days ─────────────────────────────


@pytest.mark.integrity
def test_the_evening_open_belongs_to_the_next_session() -> None:
    """18:00 ET Sunday is Monday's session. Getting this wrong shifts every roll by a day."""
    bars = _bars([
        ("2026-03-08T23:00:00", "NQH2026", 10),   # 18:00 ET Sunday -> Monday's session
        ("2026-03-09T14:00:00", "NQH2026", 10),   # 10:00 ET Monday -> Monday's session
        ("2026-03-09T21:00:00", "NQH2026", 10),   # 17:00 ET Monday -> still Monday
        ("2026-03-09T23:00:00", "NQH2026", 10),   # 19:00 ET Monday -> Tuesday
    ])
    sessions = sorted(set(daily_volume(bars).get_column("session").to_list()))
    assert sessions == [date(2026, 3, 9), date(2026, 3, 10)]


# ── against the real batch ───────────────────────────────────────────────────


def _third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    fridays = [d + timedelta(days=i) for i in range(31)
               if (d + timedelta(days=i)).month == month
               and (d + timedelta(days=i)).weekday() == 4]
    return fridays[2]


@pytest.mark.slow
@pytestmark_data
@pytest.mark.parametrize("product", ["NQ", "MNQ"])
def test_equity_index_rolls_land_before_the_third_friday(product: str) -> None:
    """Independent fact: NQ/MNQ expire on the third Friday, and volume crosses before it."""
    bars = load_product(PARQUET, product)
    cal = build_calendar(product, daily_volume(bars))
    assert cal.rolls, "no rolls found"
    for roll in cal.rolls:
        year, month = expiry_key(roll.from_contract)
        expiry = _third_friday(year, month)
        lead = (expiry - roll.session).days
        assert 0 < lead <= 21, (
            f"{product} rolled out of {roll.from_contract} on {roll.session}, "
            f"{lead} days before its {expiry} expiry"
        )


@pytest.mark.slow
@pytestmark_data
def test_gold_rolls_before_its_delivery_month_begins() -> None:
    """MGC delivers in the contract month, so the front must move on before it starts."""
    bars = load_product(PARQUET, "MGC")
    cal = build_calendar("MGC", daily_volume(bars))
    assert cal.rolls
    for roll in cal.rolls:
        year, month = expiry_key(roll.from_contract)
        assert roll.session < date(year, month, 1) + timedelta(days=1), (
            f"MGC still front-month in {roll.from_contract} on {roll.session}"
        )


@pytest.mark.slow
@pytestmark_data
@pytest.mark.parametrize("product", ["NQ", "MNQ", "MGC"])
def test_rolls_are_strictly_forward_in_expiry(product: str) -> None:
    bars = load_product(PARQUET, product)
    cal = build_calendar(product, daily_volume(bars))
    keys = [expiry_key(r.to_contract) for r in cal.rolls]
    assert keys == sorted(keys), f"{product} rolled to an earlier expiry"
    for roll in cal.rolls:
        assert expiry_key(roll.to_contract) > expiry_key(roll.from_contract)


@pytest.mark.slow
@pytestmark_data
@pytest.mark.parametrize("product", ["NQ", "MNQ", "MGC"])
def test_the_continuous_series_contains_no_crossover_session(product: str) -> None:
    bars = load_product(PARQUET, product)
    cal = build_calendar(product, daily_volume(bars))
    series = continuous_series(bars, cal)
    present = set(series.get_column("session").to_list())
    assert not (present & cal.dropped_sessions), "a dropped session is in the series"


@pytest.mark.slow
@pytestmark_data
@pytest.mark.parametrize("product", ["NQ", "MNQ", "MGC"])
def test_each_session_of_the_continuous_series_has_exactly_one_contract(
    product: str,
) -> None:
    """The defining property of a front-month series: never two contracts on one day."""
    bars = load_product(PARQUET, product)
    cal = build_calendar(product, daily_volume(bars))
    series = continuous_series(bars, cal)
    per = (series.group_by("session")
           .agg(pl.col("contract").n_unique().alias("n"))
           .filter(pl.col("n") > 1))
    assert per.height == 0, f"{per.height} sessions carry more than one contract"
