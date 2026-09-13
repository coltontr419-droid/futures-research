"""Pin Q09's first-passage arithmetic, because the table it supersedes could not be reproduced.

The handoff's Phase 1 table matched the trailing-drawdown formula in some cells and missed others by
13-22 points, and nothing recorded how it was made. The replacement therefore carries its own
checks: the closed-form limits the formula must hit, agreement with the handoff where the handoff is
reproducible, and agreement with a Monte Carlo that does not share the formula's assumptions.
decisions.md §59.
"""

from __future__ import annotations

import math

import pytest

from futuresres.reporting.q09_drawdown import (
    DRAWDOWN,
    HANDOFF_TABLE,
    TARGET_ASSUMED,
    TARGET_CONFIRMED,
    monte_carlo,
    p_reach_before_trailing,
    p_ruin_static,
)


def _static_reach(a: float, d: float, sharpe: float, sigma: float) -> float:
    """Classic gambler's ruin with drift: reach +a before a FIXED floor at -d."""
    if sharpe == 0:
        return d / (a + d)
    g = 2 * sharpe / sigma
    return (1 - math.exp(-g * d)) / (1 - math.exp(-g * (a + d)))


def test_a_driftless_walk_reaches_the_lock_with_exp_minus_one_at_any_size() -> None:
    """The number that answers "can sizing rescue a strategy with no edge": no, at any size."""
    for sigma in (0.02, 0.06, 0.20):
        p = p_reach_before_trailing(TARGET_CONFIRMED, DRAWDOWN, 0.0, sigma)
        assert p == pytest.approx(math.exp(-1), abs=1e-12)


def test_trailing_is_harsher_than_static_with_equal_target_and_barrier() -> None:
    """Why the brief's ~50% baseline was wrong: 50% is the STATIC answer."""
    assert _static_reach(0.04, 0.04, 0.0, 0.06) == pytest.approx(0.5)
    for sharpe in (0.0, 1.0, 1.5, 2.1):
        sigma = 0.06
        assert (p_reach_before_trailing(0.04, 0.04, sharpe, sigma)
                < _static_reach(0.04, 0.04, sharpe, sigma))


@pytest.mark.parametrize("cell", [(1.0, 0.01), (1.0, 0.005), (1.0, 0.0025), (1.5, 0.01)])
def test_the_formula_reproduces_the_handoff_cells_that_are_reproducible(cell) -> None:
    """Provenance, pinned where it holds. The cells that do NOT match are recorded in §59."""
    s, m = cell
    p = p_reach_before_trailing(TARGET_ASSUMED, DRAWDOWN, s, 12 * m / s)
    assert p == pytest.approx(HANDOFF_TABLE[cell], abs=0.01)


def test_k_times_sizing_takes_the_k_th_root_of_the_breach_probability() -> None:
    """The Phase 2 step-up arithmetic, and the cushion-proportional rule that replaces it."""
    s, m = 1.5, 0.005
    sigma = 12 * m / s
    base = p_ruin_static(DRAWDOWN, s, sigma)
    for k in (2, 3, 4):
        assert p_ruin_static(DRAWDOWN, s, k * sigma) == pytest.approx(base ** (1 / k))
        # size proportional to cushion holds breach probability fixed
        assert p_ruin_static(k * DRAWDOWN, s, k * sigma) == pytest.approx(base)


def test_monte_carlo_agrees_with_the_formula_within_discretisation() -> None:
    """Independent check: trade-level monitoring can only miss breaches, so it may sit slightly
    ABOVE the continuous formula, never materially below it."""
    s, m = 1.5, 0.005
    sigma = 12 * m / s
    f = p_reach_before_trailing(TARGET_CONFIRMED, DRAWDOWN, s, sigma)
    mc = monte_carlo(TARGET_CONFIRMED, DRAWDOWN, s, sigma, paths=3000, years=3, nu=None, seed=5)
    assert mc["unresolved"] < 0.01
    assert f - 0.03 < mc["p_reach"] < f + 0.05, (f, mc["p_reach"])
