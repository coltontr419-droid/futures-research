"""Pin the null as redefined 2026-09-09: an arbitrary region at a matched distance.

The placebo used to be the real level displaced by a hash-derived offset. That construction
carries a geometric defect no parameter removes - a level already displaced by `d`, offset by
`~d`, lands at `~2d` or `~0` for a median near `1.4d`. These tests pin the replacement's
contract, including the case it cannot serve.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

from futuresres.levels.placebo import (
    make_placebo,
    make_region_placebo,
    region_index,
    verify,
)


def _days(n: int) -> np.ndarray:
    base = dt.date(2020, 1, 6)
    return np.array([base + dt.timedelta(days=int(i)) for i in range(n)], dtype=object)


def test_distance_distribution_is_matched_by_construction() -> None:
    """The whole point: matched because of how it is built, not because it was tuned."""
    rng = np.random.default_rng(0)
    n = 4000
    refs = np.full(n, 100.0)
    scale = np.full(n, 2.0)
    levels = refs + rng.normal(0.0, 3.0, n)

    pl = make_region_placebo(levels, refs, _days(n), "k", scale)

    real_d = np.abs(levels - refs)
    pl_d = np.abs(pl - refs)
    ratio = float(np.median(pl_d) / np.median(real_d))
    assert 0.9 < ratio < 1.1, ratio


def test_the_displacement_construction_produces_the_1_4x_bias_it_was_replaced_for() -> None:
    """The defect, pinned so the old construction is not reintroduced by accident.

    Scale is set so the offset MAGNITUDE equals the real distance - the most favourable
    choice available to the old method - and the median distance still lands near 1.4x.
    """
    rng = np.random.default_rng(1)
    n = 4000
    refs = np.full(n, 100.0)
    levels = refs + rng.normal(0.0, 3.0, n)
    real_d = np.abs(levels - refs)
    # offset_unit averages 0.9 in magnitude over [0.3, 1.5]
    scale = np.full(n, float(np.median(real_d)) / 0.9)

    old = make_placebo(levels, _days(n), "k", scale)
    ratio = float(np.median(np.abs(old - refs)) / np.median(real_d))
    assert 1.25 < ratio < 1.6, (
        f"expected the ~1.4x geometric bias that motivated the redefinition, got {ratio}"
    )


def test_scaling_is_volatility_normalised_not_pooled_raw() -> None:
    """A quiet session must not inherit a busy session's spread.

    Distances are normalised by each level's own scale before pooling and rescaled by the
    receiving level's scale, so a session with half the range gets half the distances.
    """
    n = 2000
    refs = np.full(n, 100.0)
    scale = np.where(np.arange(n) % 2 == 0, 1.0, 10.0)
    levels = refs + np.where(np.arange(n) % 2 == 0, 1.0, 10.0)

    pl = make_region_placebo(levels, refs, _days(n), "k", scale)
    d = np.abs(pl - refs)
    quiet, busy = d[::2], d[1::2]
    assert np.isfinite(quiet).all() and np.isfinite(busy).all()
    assert 8.0 < float(np.median(busy) / np.median(quiet)) < 12.0


def test_a_level_sitting_at_the_reference_price_is_degenerate_and_says_so() -> None:
    """open_RTH / open_CME. No distance to match, so no comparable region exists.

    This is a property of the level definition, not a tuning failure, and it means L06 has
    no valid control under this null. It must surface as its own failure kind rather than as
    an ordinary mismatch that a future reader might try to fix with a scale.
    """
    n = 500
    refs = np.full(n, 100.0)
    levels = refs.copy()                      # the level IS the reference price
    scale = np.full(n, 2.0)

    pl = make_region_placebo(levels, refs, _days(n), "open_RTH", scale)
    assert np.isnan(pl).all(), "a degenerate type must not produce a fake placebo"

    rep = verify("open_RTH", "MGC", levels, pl,
                 np.abs(levels - refs), np.abs(pl - refs),
                 np.ones(n, bool), np.zeros(n, bool), strict=False)
    assert not rep.ok
    assert any("DEGENERATE" in f for f in rep.failures), rep.failures


def test_region_selection_is_deterministic_across_processes() -> None:
    """SHA-256 of (day, level_type, index), never Python's salted hash().

    The salted-hash bug forced a floor sweep to be discarded and re-run earlier in this
    project; the replacement construction inherits the same discipline.
    """
    day = dt.date(2021, 3, 4)
    a = [region_index(day, "fvg_w2_1m", i, 977) for i in range(50)]
    b = [region_index(day, "fvg_w2_1m", i, 977) for i in range(50)]
    assert a == b
    assert a != [region_index(day, "or30", i, 977) for i in range(50)]
    assert {s for _, s in a} == {1.0, -1.0}, "both sides must be used"
    assert all(0 <= p < 977 for p, _ in a)


def test_touch_rate_is_not_fitted() -> None:
    """Only distance is designed. Touch is measured, so it stays an independent check.

    Fitting touch as well would erase part of the effect under test: a level type that
    genuinely attracts price would force its placebo closer to equalise touch, which would
    then break the distance match. The construction takes no touch data as input, and this
    test pins that by signature.
    """
    import inspect

    params = set(inspect.signature(make_region_placebo).parameters)
    assert params == {"levels", "refs", "days", "level_type", "scale"}, params
    assert not any("touch" in p for p in params)
