"""The streaming roll path must agree with the eager one bar for bar.

WHY THIS EXISTS. `sink_continuous` avoids a global sort by concatenating contracts in
expiry order, on the argument that a monotonic front month makes those two orderings the
same. That argument is correct but it is an ARGUMENT, and the eager `continuous_series` is
the readable statement of what the roll is. The streaming path was introduced because the
eager one is OOM-killed on this hardware, which is a reason to compute it differently and
not a reason to compute something different.

The fixture is synthetic and small precisely so the eager path can run on it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from futuresres.data.roll import (
    build_calendar,
    continuous_series,
    daily_volume,
    daily_volume_streaming,
    load_product,
    sink_continuous,
)


def _write_fixture(root, product="ZZ", contracts=(("ZZH2020", 1), ("ZZM2020", 2),
                                                  ("ZZU2020", 3))):
    """Three contracts whose volume crosses over, so the calendar contains real rolls."""
    base = datetime(2020, 1, 6, 14, 30, tzinfo=timezone.utc)
    for contract, rank in contracts:
        rows = []
        for day in range(24):                      # 24 sessions
            for minute in range(30):               # 30 bars per session
                ts = base + timedelta(days=day, minutes=minute)
                # volume ramps so each contract leads for a stretch, in expiry order
                lead = (day // 8) + 1
                vol = 100 if rank == lead else 10
                px = 100.0 + rank + day * 0.5 + minute * 0.01
                rows.append({
                    "ts_event": ts, "symbol": product, "contract": contract,
                    "open": px, "high": px, "low": px, "close": px,
                    "volume": vol, "trades": 1,
                })
        d = root / f"symbol={product}" / f"contract={contract}"
        d.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(rows).with_columns(
            pl.col("ts_event").dt.convert_time_zone("UTC")
        ).write_parquet(d / "bars.parquet")
    return product


def test_streaming_roll_matches_eager(tmp_path) -> None:
    """Same bars, same order, same columns — the sort-free path is not a different series."""
    parquet = tmp_path / "parquet"
    product = _write_fixture(parquet)

    bars = load_product(parquet, product)
    cal_eager = build_calendar(product, daily_volume(bars))
    expected = continuous_series(bars, cal_eager)

    cal_stream = build_calendar(product, daily_volume_streaming(parquet, product))
    target = tmp_path / "out.parquet"
    sink_continuous(parquet, product, cal_stream, target)
    got = pl.read_parquet(target)

    assert cal_stream.front_by_session == cal_eager.front_by_session
    assert [r.session for r in cal_stream.rolls] == [r.session for r in cal_eager.rolls]
    assert got.height == expected.height, "streaming dropped or duplicated bars"
    assert sorted(got.columns) == sorted(expected.columns)
    assert got["ts_event"].to_list() == expected["ts_event"].to_list(), "ORDER differs"
    assert got.sort("ts_event").equals(expected.sort("ts_event"))


def test_the_calendar_is_the_same_from_either_volume_path(tmp_path) -> None:
    """`daily_volume_streaming` feeds `build_calendar`; it must not change the roll."""
    parquet = tmp_path / "parquet"
    product = _write_fixture(parquet)
    eager = daily_volume(load_product(parquet, product))
    stream = daily_volume_streaming(parquet, product)
    assert stream.sort(["session", "contract"]).equals(eager.sort(["session", "contract"]))


def test_output_is_ordered_by_timestamp_without_a_global_sort(tmp_path) -> None:
    """The property the sort-free construction claims, asserted directly."""
    parquet = tmp_path / "parquet"
    product = _write_fixture(parquet)
    cal = build_calendar(product, daily_volume_streaming(parquet, product))
    target = tmp_path / "out.parquet"
    sink_continuous(parquet, product, cal, target)
    ts = pl.read_parquet(target)["ts_event"].to_list()
    assert ts == sorted(ts), "concatenating contracts in expiry order did not yield ts order"


def test_crossover_sessions_are_absent_entirely(tmp_path) -> None:
    """Dropped, not stitched — §3. A roll session must contribute no bars at all."""
    parquet = tmp_path / "parquet"
    product = _write_fixture(parquet)
    cal = build_calendar(product, daily_volume_streaming(parquet, product))
    assert cal.rolls, "fixture produced no rolls, so this asserts nothing"
    target = tmp_path / "out.parquet"
    sink_continuous(parquet, product, cal, target)
    sessions = set(pl.read_parquet(target)["session"].to_list())
    assert not (sessions & cal.dropped_sessions)
