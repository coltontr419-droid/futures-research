"""L11's band boundaries. Registration-time checks; no Stage 1 and no market data.

The arithmetic is testable on synthetic input, which is the point of testing it now: the
firing rate and the placebo match cannot be measured without the real series, but whether
`bollinger_levels` computes a Bollinger band correctly does not depend on the data at all.
"""

from __future__ import annotations

import numpy as np
import pytest

from futuresres.levels.definitions import (
    RTH_OPEN,
    ROW_MINUTES,
    Grid,
    bollinger_levels,
)


def _grid(n_rows: int = 40, seed: int = 0) -> Grid:
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 1.0, size=(n_rows, ROW_MINUTES))
    close = 1000.0 + np.cumsum(steps, axis=1)
    return Grid(days=np.arange(n_rows), close=close, high=close + 0.5, low=close - 0.5,
                volume=np.ones_like(close), fill_fraction=1.0)


def _flat_grid(n_rows: int = 40, price: float = 1000.0) -> Grid:
    close = np.full((n_rows, ROW_MINUTES), price)
    return Grid(days=np.arange(n_rows), close=close, high=close, low=close,
                volume=np.ones_like(close), fill_fraction=1.0)


def test_the_bands_are_mean_plus_minus_k_sigma_of_the_last_period_hourly_closes() -> None:
    """Computed independently here from the same closes, so the assertion is arithmetic."""
    g = _grid()
    period, k, tf = 20, 2.0, 60
    up, lo = bollinger_levels(g, period, k, tf)

    sampled = g.close[:, ::tf]
    flat = sampled.ravel()
    col = min((RTH_OPEN + 60) // tf, sampled.shape[1] - 1)
    for row in range(5, g.n):
        end = row * sampled.shape[1] + col          # index of this row's sampled bar
        window = flat[end - period + 1:end + 1]     # INCLUDES the current bar
        mean, sd = window.mean(), window.std()      # population sigma, ddof=0
        assert up.price[row] == pytest.approx(mean + k * sd)
        assert lo.price[row] == pytest.approx(mean - k * sd)


def test_a_motionless_market_has_zero_width_bands() -> None:
    """sigma = 0, so both boundaries collapse onto the mean and onto the price itself."""
    up, lo = bollinger_levels(_flat_grid(), 20, 2.0, 60)
    finite = np.isfinite(up.price)
    assert finite.any()
    assert np.allclose(up.price[finite], 1000.0)
    assert np.allclose(lo.price[finite], 1000.0)


def test_upper_is_never_below_lower() -> None:
    up, lo = bollinger_levels(_grid(), 20, 2.0, 60)
    both = np.isfinite(up.price) & np.isfinite(lo.price)
    assert both.any()
    assert (up.price[both] >= lo.price[both]).all()


def test_warm_up_is_nan_rather_than_fabricated() -> None:
    """A band from fewer than `period` bars is not the band anyone is watching.

    With 1,375-minute rows and hourly sampling there are 23 bars per row, so a 20-bar window
    is not full until partway through the first row. That row must carry no level.
    """
    g = _grid()
    tf, period = 60, 20
    sampled_per_row = g.close[:, ::tf].shape[1]
    assert sampled_per_row < 2 * period, "fixture no longer exercises the warm-up"
    up, _ = bollinger_levels(g, period, 2.0, tf)
    assert not np.isfinite(up.price[0]), "row 0 cannot have a full 20-bar window at 10:30"
    assert np.isfinite(up.price[1:]).all()


def test_upper_and_lower_are_distinct_level_types() -> None:
    """Pooling them would let a placebo drawn for one stand in for the other.

    Their distance distributions differ - price is not symmetrically placed between the
    bands - so one shared type would break the matching the placebo construction relies on.
    """
    up, lo = bollinger_levels(_grid(), 20, 2.0, 60)
    assert up.kind != lo.kind
    assert up.kind == "bb20k2_60m_upper"
    assert lo.kind == "bb20k2_60m_lower"


def test_the_kind_string_records_the_settings_that_were_fixed_a_priori() -> None:
    """L11's premise is that 20 and 2.0 specifically are the watched numbers.

    If a later reader finds `bb14k2.5_60m` in a report, that is a swept parameter and the
    self-fulfilling mechanism no longer applies to it. The name is what makes that visible.
    """
    up, _ = bollinger_levels(_grid(), 14, 2.5, 60)
    assert up.kind == "bb14k2.5_60m_upper"
