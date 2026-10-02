"""T-series measurement machinery, on synthetic data. No market data, no trials.

Each test pins a property a T-series result depends on, so a later edit cannot silently
break it. Two of them pin bugs that were made and caught while building this (decisions.md
S65): a NaN-poisoned rolling sum, and an event-level permutation test that ignored session
clustering.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest

from futuresres.levels import definitions as D
from futuresres.reporting import t05_sign_asymmetry as t05
from futuresres.reporting.t02_t04_scale_collinearity import rolling_sum


# ── rolling sum (T02/T04) ────────────────────────────────────────────────────────

def test_rolling_sum_matches_naive_and_respects_gaps() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(size=500)
    x[[37, 38, 200, 411]] = np.nan
    w = 7
    got = rolling_sum(x, w)
    for i in range(x.size):
        win = x[max(0, i - w + 1): i + 1]
        if i < w - 1 or not np.all(np.isfinite(win)):
            assert np.isnan(got[i]), i
        else:
            assert got[i] == pytest.approx(win.sum(), abs=1e-12), i


def test_rolling_sum_recovers_after_a_gap() -> None:
    """The first version used a raw cumsum, so one NaN poisoned every later window."""
    x = np.array([1.0, 2.0, np.nan, 3.0, 4.0, 5.0, 6.0])
    got = rolling_sum(x, 2)
    assert np.isnan(got[2]) and np.isnan(got[3])
    assert got[4] == 7.0 and got[6] == 11.0


def _jump_fraction(r: np.ndarray, w: int) -> np.ndarray:
    rv = rolling_sum(r * r, w)
    prod = np.full(r.size, np.nan)
    prod[1:] = np.abs(r[1:]) * np.abs(r[:-1])
    bv = (np.pi / 2) * rolling_sum(prod, w - 1)
    return np.clip(rv - bv, 0, None) / rv


def test_jump_fraction_separates_a_jump_from_diffusion() -> None:
    rng = np.random.default_rng(2)
    diffusive = rng.normal(0, 1e-4, 4000)
    j_diff = _jump_fraction(diffusive, 60)
    assert np.nanmedian(j_diff) < 0.15
    jumped = diffusive.copy()
    jumped[3000] = 50e-4
    assert _jump_fraction(jumped, 60)[3030] > 0.7


def test_jump_fraction_is_inflated_by_zero_returns() -> None:
    """The discreteness channel S65 reports: zeros kill two bipower products and one RV term."""
    rng = np.random.default_rng(3)
    r = rng.normal(0, 1e-4, 6000)
    zeroed = r.copy()
    zeroed[rng.random(r.size) < 0.4] = 0.0
    assert np.nanmedian(_jump_fraction(zeroed, 60)) > np.nanmedian(_jump_fraction(r, 60)) + 0.1


# ── session-clustered split and injection (T05) ─────────────────────────────────

def _clustered(n_sessions: int, per: int, rng: np.random.Generator):
    sess = np.repeat(np.arange(n_sessions), per)
    shock = rng.normal(0, 1.0, n_sessions)[sess]          # within-session correlation
    diff = shock + rng.normal(0, 1.0, sess.size)
    up = rng.random(sess.size) < 0.5
    return diff, up, sess


def test_split_recombines_to_the_pooled_mean() -> None:
    rng = np.random.default_rng(4)
    diff, up, sess = _clustered(300, 20, rng)
    bs = t05.session_bootstrap_split(diff, up, sess, rng, 0.05)
    pooled = (bs["mean_up"] * bs["n_up"] + bs["mean_down"] * bs["n_down"]) / diff.size
    assert pooled == pytest.approx(diff.mean(), abs=1e-12)
    assert bs["gap"] == pytest.approx(bs["mean_up"] - bs["mean_down"], abs=1e-12)


def test_injection_moves_the_gap_by_exactly_delta_and_is_detected() -> None:
    rng = np.random.default_rng(5)
    diff, up, sess = _clustered(400, 20, rng)
    inj = t05.inject_and_detect(diff, up, sess, 0.5, rng, 0.05)
    assert inj["plumbing_ok"]
    assert inj["shift_recovered"] == pytest.approx(0.5, abs=1e-12)
    assert inj["detected"]


def test_session_bootstrap_is_wider_than_an_event_level_test() -> None:
    """The unit error the first T05 draft made: with a shared session shock, treating events
    as independent understates the SE. The session bootstrap must not."""
    rng = np.random.default_rng(6)
    diff, up, sess = _clustered(200, 50, rng)
    bs = t05.session_bootstrap_split(diff, up, sess, rng, 0.05)
    naive_se = np.sqrt(diff[up].var(ddof=1) / up.sum())
    assert bs["se_up"] > 2 * naive_se


# ── grid and zones (T05 L07) ─────────────────────────────────────────────────────

def _grid(n: int, seed: int) -> D.Grid:
    rng = np.random.default_rng(seed)
    steps = rng.choice([-0.1, 0.0, 0.1], size=(n, D.ROW_MINUTES), p=[0.3, 0.4, 0.3])
    close = 2000 + np.cumsum(steps, axis=1)
    spread = rng.choice([0.0, 0.1, 0.2, 0.5], size=close.shape)
    days = np.array([np.datetime64("2020-01-01") + i for i in range(n)])
    return D.Grid(days, close, close + spread, close - spread,
                  np.ones_like(close), 1.0)


def test_chunked_fvg_zones_equal_the_direct_builder() -> None:
    g = _grid(13, 7)
    a, ha, da = D.fvg_zones_directed(g, 2, 1, "MGC")
    b, hb, db = t05.fvg_zones_chunked(g, 2, 1, "MGC", n_chunks=4)
    assert a.price.size > 0
    for x, y in ((a.price, b.price), (a.row, b.row), (a.valid_from, b.valid_from),
                 (a.ref_price, b.ref_price), (ha, hb), (da, db)):
        assert np.array_equal(x, y, equal_nan=True)


def test_lowmem_grid_equals_definitions_load(tmp_path, monkeypatch) -> None:
    """Across a year boundary, with gaps, so the year chunking and the fill are both tested."""
    rng = np.random.default_rng(8)
    start = datetime(2019, 12, 30, 23, 0, tzinfo=timezone.utc)
    minutes = np.sort(rng.choice(5 * 1440, size=4000, replace=False))
    ts = [start + timedelta(minutes=int(m)) for m in minutes]
    close = 1500 + np.cumsum(rng.choice([-0.1, 0.0, 0.1], size=minutes.size))
    df = pl.DataFrame({"ts_event": ts, "high": close + 0.1, "low": close - 0.1,
                       "close": close, "volume": rng.integers(1, 50, minutes.size)})
    df = df.with_columns(pl.col("ts_event").dt.cast_time_unit("us"))
    (tmp_path / "data" / "continuous").mkdir(parents=True)
    df.write_parquet(tmp_path / "data" / "continuous" / "MGC.parquet")

    ref = D.load("MGC", tmp_path)
    monkeypatch.setattr(t05, "ROOT", tmp_path)
    got = t05.load_grid_lowmem("MGC")
    assert np.array_equal(ref.days, got.days)
    for name in ("close", "high", "low", "volume"):
        assert np.array_equal(getattr(ref, name), getattr(got, name), equal_nan=True), name
    assert ref.fill_fraction == got.fill_fraction
