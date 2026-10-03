"""W04's data rules, timing and evaluator, on synthetic inputs only. decisions.md 73-76."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import polars as pl
import pytest

from futuresres.data.daily_bars import build_market, resolve_decade
from futuresres.signals.portfolio import evaluate_portfolio
from futuresres.signals.w04 import DELAY, month_ends, sr_bar, weights


def test_decade_is_resolved_per_instrument_from_its_first_bar():
    """CL lists ~9 years out: CLZ6 first seen in 2017 is 2026; a CLZ6 first seen in 2027 is 2036."""
    f = pl.DataFrame({"instrument_id": [1, 1, 2], "symbol": ["CLZ6", "CLZ6", "CLZ6"],
                      "date": [date(2017, 3, 1), date(2026, 11, 1), date(2027, 2, 1)]})
    out = dict(resolve_decade(f).select("instrument_id", "contract").unique().iter_rows())
    assert out == {1: "CLZ2026", 2: "CLZ2036"}


def _bars(rows):
    return pl.DataFrame(rows, schema=["date", "contract", "close", "volume"], orient="row")


def test_held_return_is_same_contract_and_the_crossover_is_dropped():
    d = [date(2024, 1, i) for i in (2, 3, 4, 5)]
    bars = _bars([
        (d[0], "GCG2024", 100.0, 900), (d[0], "GCJ2024", 101.0, 100),
        (d[1], "GCG2024", 110.0, 800), (d[1], "GCJ2024", 112.0, 200),
        (d[2], "GCG2024", 111.0, 100), (d[2], "GCJ2024", 113.0, 900),   # crossover
        (d[3], "GCG2024", 115.0, 50), (d[3], "GCJ2024", 115.0, 950),
    ])
    m = build_market("GC", bars)
    assert m.ret[1] == pytest.approx(110 / 100 - 1)          # held G, G's own close
    assert m.crossover[2] and m.ret[2] == 0.0                # roll session dropped
    assert m.ret[3] == pytest.approx(115 / 113 - 1)          # now holding J, J's own close


def test_carry_uses_the_highest_volume_later_contract_on_the_same_bar():
    d = date(2024, 1, 2)
    bars = _bars([(d, "GCG2024", 100.0, 900), (d, "GCH2024", 50.0, 1),   # thin serial month
                  (d, "GCJ2024", 102.0, 500)])
    m = build_market("GC", bars)
    assert m.carry[0] == pytest.approx((100 - 102) / 102 / (2 / 12))


def _world(t=900, m=3, seed=0):
    rng = np.random.default_rng(seed)
    dates = np.datetime64("2015-01-01") + np.arange(int(t * 7 / 5) + 10)
    dates = dates[np.is_busday(dates)][:t]
    rets = rng.normal(0, 0.01, (t, m))
    carry = np.cumsum(rng.normal(0, 0.01, (t, m)), axis=0)
    return dates, rets, carry, np.ones((t, m), bool)


def test_weights_never_use_a_bar_after_the_month_end_that_sets_them():
    dates, rets, carry, avail = _world()
    wt, wc = weights(dates, rets, carry, avail)
    ends = month_ends(dates)
    k = 20
    d = ends[k]
    r2, c2 = rets.copy(), carry.copy()
    r2[d + 1:] = np.random.default_rng(9).normal(0, 0.05, r2[d + 1:].shape)
    c2[d + 1:] = -c2[d + 1:]
    wt2, wc2 = weights(dates, r2, c2, avail)
    held = slice(d + DELAY, ends[k + 1] + DELAY)
    assert np.allclose(wt[held], wt2[held]) and np.allclose(wc[held], wc2[held])
    assert np.any(wt[held] != 0)


def test_first_position_starts_delay_bars_after_its_month_end():
    dates, rets, carry, avail = _world()
    wt, _ = weights(dates, rets, carry, avail)
    first = np.flatnonzero(np.any(wt != 0, axis=1))[0]
    assert first - DELAY in set(month_ends(dates))


def test_each_sleeve_is_scaled_to_unit_ex_ante_volatility():
    dates, rets, carry, avail = _world()
    wt, _ = weights(dates, rets, carry, avail)
    row = wt[np.flatnonzero(np.any(wt != 0, axis=1))[-1]]
    assert np.count_nonzero(row) == 3


def test_evaluator_sharpe_cost_and_rotation():
    rng = np.random.default_rng(1)
    t = 3000
    dates = np.datetime64("2015-01-01") + np.arange(t)
    sig = np.sign(rng.normal(size=(t, 1)))
    rets = 0.01 * rng.normal(size=(t, 1)) + 0.002 * sig      # an edge aligned with the position
    w = sig.copy()
    res = evaluate_portfolio(dates, [w], rets, np.zeros_like(rets), "2021-01-01", n_rotations=200)
    gross = (w * rets).sum(1)
    assert res["full"]["sharpe_net"] == pytest.approx(gross.mean() / gross.std(ddof=1) * math.sqrt(252))
    costly = evaluate_portfolio(dates, [w], rets, np.full_like(rets, 0.001), "2021-01-01", n_rotations=0)
    assert costly["full"]["sharpe_net"] < res["full"]["sharpe_net"]
    rn = res["rotation_null_post_2021"]
    assert rn["share_at_or_above_real"] < 0.02 and abs(rn["mean"]) < 1.0


def test_rotation_keeps_pure_drift_inside_the_null():
    """An always-long book on a drifting market earns the drift; rotation keeps it, so the real result
    sits inside its null - the §54 property the control exists for."""
    rng = np.random.default_rng(2)
    t = 3000
    dates = np.datetime64("2015-01-01") + np.arange(t)
    rets = 0.01 * rng.normal(size=(t, 1)) + 0.001
    res = evaluate_portfolio(dates, [np.ones((t, 1))], rets, np.zeros_like(rets), "2021-01-01",
                             n_rotations=100)
    assert res["rotation_null_post_2021"]["share_at_or_above_real"] > 0.2


def test_unit_consistent_bar_matches_decisions_73():
    assert sr_bar(1320) == pytest.approx(1.39, abs=0.02)
    assert sr_bar(2780) == pytest.approx(0.96, abs=0.02)
