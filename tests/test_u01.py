"""U01 gap construction on a synthetic series. No market data, no trials.

Pins the definition the measurement rests on: weekly vs daily opens, the gap, same-session
fill, and each validity rule (late first print, stale prior close) - each of which was decided
in decisions.md 67 and would silently change the event count if it drifted.
"""
from __future__ import annotations

from datetime import datetime, timezone

import polars as pl
import pytest

from futuresres.reporting import u01_gap_fill as u


def _bar(ts: str, session: str, o: float, h: float, lo: float, c: float, contract="MGCM2024"):
    return {"ts_event": datetime.fromisoformat(ts).replace(tzinfo=timezone.utc),
            "contract": contract, "session": datetime.fromisoformat(session).date(),
            "open": o, "high": h, "low": lo, "close": c}


@pytest.fixture()
def ev(tmp_path, monkeypatch):
    # April 2024, EDT (UTC-4): 18:00 ET = 22:00Z, 09:30 ET = 13:30Z, 16:59 ET = 20:59Z
    rows = [
        # Fri 04-05: closes 100.0 at 16:59 ET
        _bar("2024-04-04T22:00", "2024-04-05", 100, 100, 100, 100),
        _bar("2024-04-05T20:59", "2024-04-05", 100, 100, 100, 100.0),
        # Mon 04-08, opened Sunday 18:00 ET (weekly): +0.6% gap, later trades back to 99.9
        _bar("2024-04-07T22:00", "2024-04-08", 100.6, 100.7, 100.5, 100.6),
        _bar("2024-04-08T13:30", "2024-04-08", 100.2, 100.3, 99.9, 100.1),
        _bar("2024-04-08T20:59", "2024-04-08", 101.0, 101.0, 101.0, 101.0),
        # Tue 04-09 (daily): +0.49% gap that never trades back to 101.0
        _bar("2024-04-08T22:00", "2024-04-09", 101.5, 101.6, 101.4, 101.5),
        _bar("2024-04-09T13:30", "2024-04-09", 101.4, 101.5, 101.2, 101.3),
        _bar("2024-04-09T20:59", "2024-04-09", 102.0, 102.0, 102.0, 102.0),
        # Wed 04-10: first print 30 minutes after the reopen -> invalid
        _bar("2024-04-09T22:30", "2024-04-10", 102, 102, 102, 102),
        _bar("2024-04-10T20:59", "2024-04-10", 102, 102, 102, 102),
        # Thu 04-11: valid open, but last trades at 12:00 ET -> stale close for Friday
        _bar("2024-04-10T22:00", "2024-04-11", 102, 102, 102, 102),
        _bar("2024-04-11T16:00", "2024-04-11", 102, 102, 102, 102),
        # Fri 04-12: its prior close is stale -> invalid
        _bar("2024-04-11T22:00", "2024-04-12", 103, 103, 103, 103),
        _bar("2024-04-12T20:59", "2024-04-12", 103, 103, 103, 103),
    ]
    df = pl.DataFrame(rows).with_columns(pl.col("ts_event").dt.cast_time_unit("us"))
    (tmp_path / "MGC.parquet").parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(tmp_path / "MGC.parquet")
    monkeypatch.setattr(u, "CONTINUOUS", tmp_path)
    out = u.events("MGC")
    return {r["session"].isoformat(): r for r in out.iter_rows(named=True)}


def test_sunday_reopen_is_weekly_and_fills(ev) -> None:
    m = ev["2024-04-08"]
    assert m["kind"] == "weekly" and m["valid"]
    assert m["gap"] == pytest.approx(0.0059820716, abs=1e-9)
    assert m["filled"] is True


def test_weekday_reopen_is_daily_and_an_untouched_prior_close_is_no_fill(ev) -> None:
    t = ev["2024-04-09"]
    assert t["kind"] == "daily" and t["valid"]
    assert abs(t["gap"]) >= u.THRESHOLD
    assert t["filled"] is False


def test_a_late_first_print_is_not_an_open(ev) -> None:
    assert ev["2024-04-10"]["first_print_offset"] == 30
    assert not ev["2024-04-10"]["valid"]


def test_a_stale_prior_close_is_not_a_close(ev) -> None:
    assert ev["2024-04-11"]["valid"]
    assert ev["2024-04-11"]["traded_at_close"] is False
    assert not ev["2024-04-12"]["valid"]


def test_reflection_principle_benchmark() -> None:
    import numpy as np
    from scipy.stats import norm
    p = u.rw_fill(np.array([0.0, 0.01, 0.02]), np.array([0.01, 0.01, 0.01]))
    assert p[0] == pytest.approx(1.0)
    assert p[1] == pytest.approx(2 * (1 - norm.cdf(1.0)))
    assert p[2] < p[1] < p[0]
