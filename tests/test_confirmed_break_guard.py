"""`confirmed_break` must refuse the shape that silently broke three hypotheses.

L02's sweep arm, L05 and L11 all fired on every level at the first bar examined, because the
function tested a run beyond the level in EITHER direction and each was applied to a level
price already sat strictly inside. Every one looked healthy in the firing-rate table.
decisions.md 41.
"""

from __future__ import annotations

import numpy as np
import pytest

from futuresres.levels.definitions import (
    ROW_MINUTES,
    DegenerateCondition,
    Grid,
    LevelSet,
    confirmed_break,
)


def _grid(n_rows: int = 30, price: float = 100.0) -> Grid:
    close = np.full((n_rows, ROW_MINUTES), price)
    return Grid(days=np.arange(n_rows), close=close, high=close + 1.0, low=close - 1.0,
                volume=np.ones_like(close), fill_fraction=1.0)


def _levels(kind: str, price: float, n_rows: int = 30, valid: int = 0) -> LevelSet:
    return LevelSet(kind=kind,
                    price=np.full(n_rows, price),
                    row=np.arange(n_rows),
                    valid_from=np.full(n_rows, valid),
                    ref_price=np.full(n_rows, 100.0))


def test_direction_is_required_and_validated() -> None:
    """The either-direction default is what made the defect expressible at all."""
    g = _grid()
    with pytest.raises(TypeError):
        confirmed_break(g, _levels("x", 105.0), 2, "MNQ")          # no direction
    with pytest.raises(ValueError, match="must be 'up' or 'down'"):
        confirmed_break(g, _levels("x", 105.0), 2, "MNQ", direction="either")


def test_a_level_price_already_sits_past_is_refused() -> None:
    """The L02-sweep / L05 / L11 shape: price 100, level 105, testing a DOWNWARD break.

    Price is below the level at every bar, so `path < px` is true immediately and stays true.
    Under the old either-direction test this fired on all 30 levels at valid_from + (k-1).
    """
    g = _grid(price=100.0)
    with pytest.raises(DegenerateCondition) as e:
        confirmed_break(g, _levels("or15", 105.0), 2, "MNQ", direction="down")
    msg = str(e.value)
    assert "100.0%" in msg
    assert "does not select events" in msg
    assert "decisions.md 41" in msg


def test_a_level_price_approaches_is_allowed() -> None:
    """Price starts below the level and never crosses: legitimate, and simply does not fire."""
    g = _grid(price=100.0)
    fired, minute = confirmed_break(g, _levels("or15", 105.0), 2, "MNQ", direction="up")
    assert not fired.any()
    assert (minute == -1).all()


def test_a_real_break_fires_once_at_the_confirming_bar() -> None:
    """k consecutive closes beyond, and the entry is the bar that completes the run."""
    close = np.full((4, ROW_MINUTES), 100.0)
    close[:, 500:] = 110.0                       # crosses above 105 at minute 500
    g = Grid(days=np.arange(4), close=close, high=close + 1, low=close - 1,
             volume=np.ones_like(close), fill_fraction=1.0)
    fired, minute = confirmed_break(g, _levels("or15", 105.0, n_rows=4), 3, "MNQ",
                                    direction="up")
    assert fired.all()
    # run of 3 completes on the third bar beyond: 500, 501, 502
    assert (minute == 502).all()


def test_k_selects_rather_than_offsets_when_the_condition_is_sound() -> None:
    """The property whose ABSENCE was the defect: different k must not be a fixed shift.

    A path that pokes above the level for two bars and then retreats confirms at k=2 but
    never at k=3 -- so k changes WHETHER the level fires, not merely when.
    """
    close = np.full((4, ROW_MINUTES), 100.0)
    close[:, 500:502] = 110.0                    # exactly two bars beyond, then back
    g = Grid(days=np.arange(4), close=close, high=close + 1, low=close - 1,
             volume=np.ones_like(close), fill_fraction=1.0)
    lv = _levels("or15", 105.0, n_rows=4)
    f2, _ = confirmed_break(g, lv, 2, "MNQ", direction="up")
    f3, _ = confirmed_break(g, lv, 3, "MNQ", direction="up")
    assert f2.all(), "two consecutive closes beyond should confirm at k=2"
    assert not f3.any(), "and must NOT confirm at k=3 -- otherwise k is an offset"


def test_sweep_reclaim_directed_matches_the_undirected_scan() -> None:
    """The directed variant must not change WHICH levels fire or WHEN -- only report the side.

    Written because a second implementation of a firing rule is exactly where the two quietly
    drift apart, and the runners consume the directed one while level_rates consumes the other.
    """
    import numpy as np
    from futuresres.levels.definitions import (
        ROW_MINUTES, Grid, LevelSet, sweep_reclaim, sweep_reclaim_directed,
    )
    rng = np.random.default_rng(4)
    n_rows = 40
    close = 100.0 + np.cumsum(rng.normal(0, 0.05, size=(n_rows, ROW_MINUTES)), axis=1)
    g = Grid(days=np.arange(n_rows), close=close, high=close + 0.1, low=close - 0.1,
             volume=np.ones_like(close), fill_fraction=1.0)
    lv = LevelSet(kind="t", price=close[:, 300].copy(), row=np.arange(n_rows),
                  valid_from=np.full(n_rows, 300), ref_price=close[:, 300].copy())
    for m in (2, 4, 8):
        for k in (2, 3, 5):
            f1, m1 = sweep_reclaim(g, lv, m, k, "MNQ")
            f2, m2, d = sweep_reclaim_directed(g, lv, m, k, "MNQ")
            assert (f1 == f2).all(), f"fired mask differs at m={m} k={k}"
            assert (m1 == m2).all(), f"entry minute differs at m={m} k={k}"
            assert set(np.unique(d[f2]).tolist()) <= {-1, 1}
            assert (d[~f2] == 0).all(), "unfired levels must carry no direction"
