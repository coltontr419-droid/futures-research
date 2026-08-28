"""The signed-exposure Stage 1 evaluator. CLAUDE.md §5 Stage 1, §7.

THE PROPERTY THAT MATTERS is drift invariance. Adding a constant drift to a price series
adds nothing predictable — nothing observable forecasts a constant — so a signal's measured
edge must not move when it is added. The implemented `evaluate_signal`, used on a signed
signal through `evaluate_cell`, fails this: it compares a long/short conditional against a
long-only unconditional, so the drift lands in the statistic. The signed evaluator is
invariant to it EXACTLY, not approximately, and that is asserted to floating-point
tolerance rather than to a threshold.
"""

from __future__ import annotations

import numpy as np
import pytest

from futuresres.signals.stage1 import (
    evaluate_signal,
    evaluate_signed_signal,
    forward_returns,
    signed_forward,
    signed_rotation_null,
)


def _random_walk(n: int, seed: int, drift: float = 0.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.normal(drift, 1e-3, n)) + np.log(30_000.0)


def _balanced_direction(n: int, seed: int, every: int = 50) -> np.ndarray:
    """A signal firing on a fixed grid with an equal number of longs and shorts."""
    rng = np.random.default_rng(seed)
    d = np.zeros(n)
    at = np.arange(every, n - every, every)
    signs = np.where(rng.random(at.size) < 0.5, -1.0, 1.0)
    d[at] = signs
    return d


# ── hand-checkable ──────────────────────────────────────────────────────────


def test_forward_window_is_entry_close_to_exit_close() -> None:
    lp = np.array([0.0, 1.0, 3.0, 6.0, 10.0])
    np.testing.assert_allclose(signed_forward(lp, 1), [1.0, 2.0, 3.0, 4.0])
    np.testing.assert_allclose(signed_forward(lp, 2), [3.0, 5.0, 7.0])


def test_signed_forward_matches_the_existing_forward_returns() -> None:
    """The two paths must describe the same window, or the fix would change the target."""
    lp = _random_walk(5_000, seed=1)
    r1 = np.zeros(lp.size)
    r1[1:] = np.diff(lp)
    for h in (1, 7, 60):
        old = forward_returns(r1, h)
        new = signed_forward(lp, h)
        np.testing.assert_allclose(new, old[: new.size], atol=1e-12)


def test_rotation_null_at_zero_is_the_observed_mean() -> None:
    """k = 0 must reproduce the point estimate, or the null is not comparable to it."""
    F = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    d = np.array([1.0, 0.0, -1.0, 0.0, 1.0, 0.0])
    null = signed_rotation_null(d, F)
    # (1*1 + (-1)*3 + 1*5) / 3 = 1.0
    assert null[0] == pytest.approx(1.0)


def test_rotation_null_shifts_the_returns_circularly() -> None:
    F = np.array([1.0, 2.0, 3.0, 4.0])
    d = np.array([1.0, 0.0, 0.0, 0.0])
    null = signed_rotation_null(d, F)
    np.testing.assert_allclose(null, [1.0, 2.0, 3.0, 4.0])


# ── the property the old statistic violates ─────────────────────────────────


def test_signed_shift_is_exactly_invariant_to_constant_drift() -> None:
    """A constant drift is not an edge. It must not change the measured shift at all."""
    n = 40_000
    lp = _random_walk(n, seed=11)
    d = _balanced_direction(n, seed=12)
    rng = lambda: np.random.default_rng(99)

    base = evaluate_signed_signal(d, lp, 60, rng=rng(), n_bootstrap=200)
    for per_bar_drift in (1e-5, 5e-5, -2e-5):
        drifted = lp + per_bar_drift * np.arange(n)
        moved = evaluate_signed_signal(d, drifted, 60, rng=rng(), n_bootstrap=200)
        assert moved.mean_shift == pytest.approx(base.mean_shift, abs=1e-15)
        assert moved.p_value == pytest.approx(base.p_value, abs=1e-12)


def test_the_implemented_statistic_is_not_drift_invariant() -> None:
    """Documents the defect the signed evaluator exists to fix, so it cannot regress.

    Built the way `evaluate_cell` builds it: off-event bars oriented LONG.

    EVENTS MUST BE SPARSE for the defect to appear. The bias lives in the off-event bars,
    which are the ones forced long; if the event windows tile the series there are almost
    none left to be biased. S09 fires roughly once per 760 bars, so `every=500` with a
    60-bar hold is the regime that matters. A first version of this test used overlapping
    windows and saw a 1.8e-6 effect where the real one is three orders of magnitude larger.
    """
    n = 200_000
    hold = 60
    lp = _random_walk(n, seed=11)
    d = _balanced_direction(n, seed=12, every=500)

    def old_shift(log_price: np.ndarray) -> float:
        r1 = np.zeros(n)
        r1[1:] = np.diff(log_price)
        oriented = np.zeros(n)
        for i in np.flatnonzero(d):
            oriented[i:min(i + hold, n)] = d[i]
        flow = np.where(oriented != 0, oriented, 1.0) * r1
        fwd = forward_returns(flow, hold)
        v = np.isfinite(fwd)
        sig = d[v] != 0
        return float(fwd[v][sig].mean() - fwd[v].mean())

    per_bar_drift = 5e-5
    base = old_shift(lp)
    drifted = old_shift(lp + per_bar_drift * np.arange(n))
    delta = drifted - base

    # The drift lands in the statistic, and it lands NEGATIVE: the conditional side is
    # balanced long/short so drift cancels there, while the unconditional side is forced
    # long and collects all of it. Magnitude is the drift over one hold, scaled by the
    # fraction of bars left outside an event window.
    assert delta < 0, (base, drifted)
    assert abs(delta) > 0.5 * per_bar_drift * hold, delta


# ── behaviour ───────────────────────────────────────────────────────────────


def test_flipping_every_direction_flips_the_shift() -> None:
    n = 30_000
    lp = _random_walk(n, seed=21)
    d = _balanced_direction(n, seed=22)
    a = evaluate_signed_signal(d, lp, 30, rng=np.random.default_rng(5), n_bootstrap=200)
    b = evaluate_signed_signal(-d, lp, 30, rng=np.random.default_rng(5), n_bootstrap=200)
    assert b.mean_shift == pytest.approx(-a.mean_shift, rel=1e-12)
    assert b.p_value == pytest.approx(a.p_value, abs=1e-12)


def test_an_injected_edge_is_recovered_and_separates() -> None:
    """Positive control: a real, sizeable effect must be found. §7.2."""
    n = 60_000
    hold = 30
    rng = np.random.default_rng(31)
    r = rng.normal(0.0, 1e-3, n)
    d = _balanced_direction(n, seed=32, every=40)
    events = np.flatnonzero(d)
    for i in events:                       # push the next `hold` bars the signal's way
        r[i + 1:i + 1 + hold] += d[i] * 3e-4
    lp = np.cumsum(r) + np.log(30_000.0)

    res = evaluate_signed_signal(d, lp, hold, rng=np.random.default_rng(7))
    assert res.mean_shift > 0
    assert res.p_value < 0.05
    assert res.separated, res.reason


def test_pure_noise_separates_at_about_the_nominal_rate() -> None:
    """Negative control. §7.2.

    ASSERTED AS A RATE, NOT ONE DRAW. A single noise series clears α = 0.05 about one time
    in twenty by definition, so a one-seed negative control is a coin flip dressed as a
    test — the first version of this used seed 41 and failed on exactly that. What is
    actually claimed is a false-positive RATE near nominal, so that is what is measured.
    The bound is loose because 24 replications cannot resolve 0.05 tightly; it is here to
    catch a badly miscalibrated null, not to certify the level. The 400-replication
    calibration on GARCH is what pins the number down.
    """
    n = 60_000
    separated = 0
    for seed in range(24):
        lp = _random_walk(n, seed=400 + seed)
        d = _balanced_direction(n, seed=900 + seed, every=40)
        res = evaluate_signed_signal(
            d, lp, 30, rng=np.random.default_rng(seed), n_bootstrap=400
        )
        separated += bool(res.separated)
    assert separated <= 5, f"{separated}/24 noise series separated"


def test_too_few_events_is_refused_not_answered() -> None:
    n = 20_000
    lp = _random_walk(n, seed=51)
    d = np.zeros(n)
    d[[100, 200, 300]] = 1.0
    res = evaluate_signed_signal(d, lp, 30, rng=np.random.default_rng(9))
    assert not res.separated
    assert "no information" in res.reason


def test_unconditional_field_is_the_drift_benchmark() -> None:
    """mean_unconditional must be what the signal's NET exposure earns from drift."""
    n = 30_000
    lp = _random_walk(n, seed=61, drift=2e-5)
    d = np.zeros(n)
    at = np.arange(50, n - 50, 50)
    d[at] = 1.0                                   # all long -> net exposure 1.0
    res = evaluate_signed_signal(d, lp, 60, rng=np.random.default_rng(3), n_bootstrap=200)
    F = signed_forward(lp, 60)
    assert res.mean_unconditional == pytest.approx(float(F.mean()), rel=1e-12)
