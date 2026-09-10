"""L07 Stage 1 helpers, on synthetic data so no trial is spent verifying the machinery."""

from __future__ import annotations

import numpy as np

from futuresres.levels import definitions as D
from futuresres.signals.l07 import (
    ALPHA,
    GS,
    HOLDS,
    TFS,
    WS,
    Cell,
    _first_entry,
    _paired_stats,
    _signed_return_bps,
    apply_bh,
    benjamini_hochberg,
    matched_types,
)


def _grid(n_rows: int = 40) -> D.Grid:
    close = np.full((n_rows, D.ROW_MINUTES), 100.0)
    return D.Grid(days=np.arange(n_rows), close=close, high=close + 0.5,
                  low=close - 0.5, volume=np.ones_like(close), fill_fraction=1.0)


def test_entry_respects_the_g_delay_and_the_zone_width() -> None:
    """`g` is a delay in BARS, and the zone is a region rather than a point."""
    g = _grid(1)
    g.close[0, :] = 100.0
    g.close[0, 500] = 103.0            # inside a zone centred on 103 half-width 0.5
    centre = np.array([103.0, 103.0, 110.0])
    half = np.array([0.5, 0.5, 0.5])
    row = np.array([0, 0, 0])

    early = _first_entry(g, centre, half, row, np.array([0, 600, 0]))
    assert early[0] == 500, "the entry minute is the first close inside the region"
    assert early[1] == -1, "a delay past the touch must exclude it"
    assert early[2] == -1, "a region price never reaches is never entered"


def test_a_wider_zone_admits_a_closer_miss() -> None:
    g = _grid(1)
    g.close[0, 300] = 101.4
    row, earliest = np.array([0]), np.array([0])
    narrow = _first_entry(g, np.array([102.0]), np.array([0.2]), row, earliest)
    wide = _first_entry(g, np.array([102.0]), np.array([0.8]), row, earliest)
    assert narrow[0] == -1 and wide[0] == 300


def test_signed_return_uses_the_traded_direction_and_the_1555_cap() -> None:
    """Exit at H minutes or 15:55 ET, whichever comes first, and the sign is the trade's."""
    g = _grid(1)
    g.close[0, 100] = 100.0
    g.close[0, 160] = 101.0
    g.close[0, D.RTH_EXIT] = 99.0

    long_ = _signed_return_bps(g, np.array([0]), np.array([100]), np.array([1.0]), 60)
    short = _signed_return_bps(g, np.array([0]), np.array([100]), np.array([-1.0]), 60)
    assert long_[0] > 0 and short[0] < 0
    assert np.isclose(long_[0], -short[0])

    # A horizon that would run past 15:55 is capped there, so it reads the 15:55 close.
    capped = _signed_return_bps(g, np.array([0]), np.array([D.RTH_EXIT - 5]),
                                np.array([1.0]), 10_000)
    assert np.isfinite(capped[0])


def test_a_zero_difference_does_not_separate() -> None:
    """Identical real and placebo returns must give a p of 1 and an interval on zero."""
    rng = np.random.default_rng(0)
    n = 2000
    x = rng.normal(0, 5, n)
    rows = np.repeat(np.arange(n // 20), 20)
    r_mean, p_mean, diff, lo, hi, used, p = _paired_stats(x, x.copy(), rows, rng)
    assert used == n
    assert diff == 0.0
    assert lo <= 0 <= hi
    assert p == 1.0


def test_a_real_difference_is_recovered() -> None:
    """A planted 2 bps edge must come back as ~2 bps with an interval clear of zero."""
    rng = np.random.default_rng(1)
    n = 4000
    rows = np.repeat(np.arange(n // 20), 20)
    plac = rng.normal(0, 5, n)
    real = plac + 2.0
    _, _, diff, lo, hi, _, p = _paired_stats(real, plac, rows, rng)
    assert 1.8 < diff < 2.2, diff
    assert lo > 0, (lo, hi)
    assert p < ALPHA


def test_the_bootstrap_resamples_sessions_so_clustering_widens_the_interval() -> None:
    """Session-level common movement must NOT be mistaken for independent information.

    The same per-event differences, arranged as many small sessions versus few large ones,
    must produce a wider interval in the clustered case. Resampling events instead of
    sessions would make the two identical, which is the error this guards.
    """
    rng = np.random.default_rng(2)
    n = 4000
    per_session = rng.normal(0, 3, 20)
    clustered = np.repeat(per_session, n // 20) + rng.normal(0, 0.1, n)
    rows_few = np.repeat(np.arange(20), n // 20)
    rows_many = np.arange(n)

    _, _, _, lo1, hi1, _, _ = _paired_stats(clustered, np.zeros(n), rows_few, rng)
    _, _, _, lo2, hi2, _, _ = _paired_stats(clustered, np.zeros(n), rows_many, rng)
    assert (hi1 - lo1) > 3 * (hi2 - lo2), (hi1 - lo1, hi2 - lo2)


def test_benjamini_hochberg_is_a_step_up_not_a_per_test_threshold() -> None:
    p = np.array([0.001, 0.02, 0.04, 0.9])
    keep = benjamini_hochberg(p, 0.05)
    # 0.04 <= 0.05*3/4 = 0.0375 is false, but 0.02 <= 0.05*2/4 = 0.025 is true, so the
    # step-up keeps the two smallest and stops.
    assert list(keep) == [True, True, False, False]
    assert not benjamini_hochberg(np.array([0.9, 0.8]), 0.05).any()


def test_bh_denominator_counts_tests_performed_not_cells_registered() -> None:
    """Excluded cells were never looked at, so including them would weaken the correction."""
    cells = [Cell("MGC", 2, 10, 1, 60, "fvg_w2_1m", p_value=0.001, separated=True),
             Cell("MGC", 4, 10, 1, 60, "fvg_w4_1m", p_value=0.20, separated=False),
             Cell("MGC", 8, 10, 1, 60, "fvg_w8_1m", excluded=True, reason="unmatched")]
    apply_bh(cells)
    assert cells[0].bh_survivor is True
    assert cells[1].bh_survivor is False
    assert cells[2].bh_survivor is False, "an excluded cell is not a test"


def test_bh_survival_requires_the_conjunctive_gate_too() -> None:
    """A tiny p with an interval containing zero is not a separation. decisions.md 26."""
    cells = [Cell("MGC", 2, 10, 1, 60, "fvg_w2_1m", p_value=0.0001, separated=False)]
    apply_bh(cells)
    assert cells[0].bh_survivor is False


def test_every_registered_l07_level_type_has_a_matching_verdict_on_file() -> None:
    """The exclusion gate must be able to decide for every cell it will be asked about."""
    mt = matched_types()
    for tf in TFS:
        for w in WS:
            for product in ("MGC", "MNQ"):
                assert (f"fvg_w{w}_{tf}m", product) in mt, (w, tf, product)
    assert len(WS) * len(GS) * len(TFS) == 18, "the registry records 18 cells per product"
    assert HOLDS == (60, 120, 180)
