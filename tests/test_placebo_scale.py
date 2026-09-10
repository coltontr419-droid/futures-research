"""Pin the placebo scale correction of 2026-09-09.

The old scale was daily ATR(20) for every level type at once, which put placebos 3x to 63x
further from price than the real levels they stood in for and failed 53 of 55 types. These
tests pin the replacement's arithmetic. They do NOT assert that matching passes - it does
not, and `reports/placebo_match.md` is where that is reported rather than hidden behind a
green test.
"""

from __future__ import annotations

import numpy as np
import pytest

from futuresres.levels.definitions import (
    ATR_HORIZONS,
    LOOKBACK,
    ROW_MINUTES,
    Grid,
    LevelSet,
    window_scale,
)


def _grid(n_rows: int = 60, seed: int = 0) -> Grid:
    """A synthetic grid with a known intraday range, so the scale is checkable by hand."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 1.0, size=(n_rows, ROW_MINUTES))
    close = 1000.0 + np.cumsum(steps, axis=1)
    return Grid(days=np.arange(n_rows), close=close, high=close + 0.5, low=close - 0.5,
                volume=np.ones_like(close), fill_fraction=1.0)


def test_intraday_atr_is_strictly_prior_and_undefined_before_lookback() -> None:
    """Same contract as the daily atr(): no value until LOOKBACK prior sessions exist."""
    g = _grid()
    a = g.intraday_atr(30)
    assert np.isnan(a[:LOOKBACK]).all(), "no average before LOOKBACK sessions"
    assert np.isfinite(a[LOOKBACK:]).all(), "and one for every session after"


def test_intraday_atr_grows_monotonically_with_horizon() -> None:
    """Range over a longer window cannot be smaller than over a shorter one.

    This is the property that makes the log-log interpolation in `window_scale` sane. It is
    also the sanity check that separates a real intraday scale from the daily one: the old
    code had a single number for every horizon, which is what the whole defect was.
    """
    g = _grid()
    medians = [float(np.nanmedian(g.intraday_atr(h))) for h in ATR_HORIZONS]
    assert all(b >= a for a, b in zip(medians, medians[1:])), medians
    assert medians[-1] > medians[0] * 5, "a full day must dwarf a single minute"


def test_intraday_atr_at_full_row_is_the_session_range() -> None:
    """At horizon = ROW_MINUTES the measure degenerates to the session's own high-low.

    That is the top-end agreement with daily true range, and it is why the correction does
    NOT change the two level types that were already matched under the daily scale.
    """
    g = _grid()
    full = g.intraday_atr(ROW_MINUTES)
    session_range = g.high.max(axis=1) - g.low.min(axis=1)
    expected = np.full(g.n, np.nan)
    for i in range(LOOKBACK, g.n):
        expected[i] = session_range[i - LOOKBACK:i].mean()
    assert np.allclose(full[LOOKBACK:], expected[LOOKBACK:], rtol=1e-12)


def test_window_scale_shortens_with_a_later_valid_from() -> None:
    """A level that only becomes valid near the close has less time to be reached.

    THIS IS THE WHOLE IDEA OF THE CORRECTION. The timescale a level operates on is its
    validity window, and `touches` gives every level the remainder of its own row - so two
    levels on the same session get different scales when they become valid at different
    minutes. The old daily scale gave them the same number.
    """
    g = _grid()
    row = np.full(8, g.n - 1, int)
    price = np.full(8, 1000.0)
    early = LevelSet("x", price, row, np.full(8, 10, int), price)
    late = LevelSet("x", price, row, np.full(8, ROW_MINUTES - 30, int), price)
    s_early, s_late = window_scale(g, early), window_scale(g, late)
    assert np.isfinite(s_early).all() and np.isfinite(s_late).all()
    assert (s_late < s_early).all(), (s_late[0], s_early[0])


def test_window_scale_is_bounded_by_the_measured_horizons() -> None:
    """Interpolation, never extrapolation beyond the measured range."""
    g = _grid()
    row = np.full(4, g.n - 1, int)
    price = np.full(4, 1000.0)
    lo = float(g.intraday_atr(ATR_HORIZONS[0])[g.n - 1])
    hi = float(g.intraday_atr(ATR_HORIZONS[-1])[g.n - 1])
    for valid in (0, 500, ROW_MINUTES - 1):
        s = window_scale(g, LevelSet("x", price, row, np.full(4, valid, int), price))
        assert (s >= lo - 1e-9).all() and (s <= hi + 1e-9).all(), (valid, s[0], lo, hi)


def test_make_placebo_rejects_a_scale_of_the_wrong_length() -> None:
    """The scale is PER LEVEL now, not per session - a silent broadcast would be a bug."""
    from futuresres.levels.placebo import make_placebo

    import datetime as dt
    days = np.array([dt.date(2020, 1, 1)] * 5, dtype=object)
    with pytest.raises(ValueError):
        make_placebo(np.ones(5), days, "k", np.ones(4))
