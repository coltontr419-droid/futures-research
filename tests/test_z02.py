"""Z02's signal construction against the paper's own definitions, on synthetic inputs. decisions.md 87."""

from __future__ import annotations

import numpy as np
import pytest

from futuresres.signals.z02 import calendar_signal, month_positions, threshold_signal, weights


def _bdays(start: str, n: int) -> np.ndarray:
    d = np.datetime64(start) + np.arange(int(n * 1.6) + 10)
    return d[np.is_busday(d)][:n]


def test_the_papers_worked_example():
    """'If the equity market outperforms the bond market by 10% on a single day within the 60/40
    portfolio, both rebalancing signals should increase by approximately 2.26%.' (Section 1.2)"""
    dates = _bdays("2024-01-02", 3)
    r_sp = np.array([0.0, 0.10, 0.0]); r_ty = np.zeros(3)
    assert threshold_signal(r_sp, r_ty)[1] == pytest.approx(0.0226, abs=1e-4)
    assert calendar_signal(dates, r_sp, r_ty)[1] == pytest.approx(0.0226, abs=1e-4)


def test_delta_zero_rebalances_every_day_and_larger_deltas_let_weights_drift():
    """A 1% equity day, then a flat day: delta = 0 resets, so its signal returns to 0; every delta above
    the 0.24-point deviation lets the weight stay drifted, so the AVERAGE stays positive."""
    r_sp = np.array([0.01, 0.0]); r_ty = np.zeros(2)
    s = threshold_signal(r_sp, r_ty)
    assert s[0] > 0
    assert 0 < s[1] < s[0]


def test_calendar_state_resets_after_the_last_business_day():
    dates = _bdays("2024-01-25", 8)                  # spans the January month-end
    r_sp = np.full(8, 0.01); r_ty = np.zeros(8)
    cal = calendar_signal(dates, r_sp, r_ty)
    pos, first = month_positions(dates)
    after = np.flatnonzero(first)[0]                 # first business day of February
    assert cal[after] < cal[after - 1]               # the drift restarted from 60%


def test_week4_takes_the_opposite_sign_of_the_calendar_signal_and_other_days_are_zero():
    dates = _bdays("2024-01-02", 60)
    r_sp = np.full(60, 0.002); r_ty = np.zeros(60)  # equities steadily outperform: Calendar > 0
    w = weights(dates, r_sp, r_ty)
    pos, first = month_positions(dates)
    thr_part = 0.5 * (-threshold_signal(r_sp, r_ty) / 0.015)
    mod = (w - thr_part) / 0.5
    assert np.allclose(mod[pos >= -5], -1)                                  # sign(-Calendar), Calendar > 0
    assert np.allclose(mod[(pos < -5) & ~first], 0)
    assert np.allclose(mod[first][1:], 1)                                   # sign(+Calendar at -4)


def test_month_positions_count_back_from_the_last_business_day():
    dates = _bdays("2024-02-26", 6)                  # Feb 26-29, Mar 1, Mar 4
    pos, first = month_positions(dates)
    assert list(pos[:4]) == [-4, -3, -2, -1]
    assert first[4] and not first[5]
