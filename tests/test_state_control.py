"""Fault-inject the state control before trusting it — the loader, §41 and §52 precedent.

WHAT IS BEING TESTED, AND WHY IT IS NOT ENOUGH TO ASSERT IT. §54 recorded a claim: a state
condition cannot beat a covariate-matched control by firing in favourable regimes, because
the control fires in the same regimes by construction. A claim of that shape is exactly what
`decisions.md` §52 was written about — the P-series draft asserted "ratio-form, so the scale
check passes natively", and the assertion was wrong. So the claim is verified here in the
only way that means anything:

    1. a deliberately REGIME-LOADED fake condition, carrying no information whatsoever,
       is confirmed to BEAT a rotation null           — the danger is real, not hypothetical
    2. the SAME condition is confirmed NOT to beat the matched control
    3. a GENUINE state effect IS confirmed to beat it — without this, (2) would also pass
       for a control that always returns null, which is the trivial way to look rigorous

The fake condition in (1) and (2) fires on EVEN-NUMBERED SESSIONS inside a high-volatility,
near-the-open regime that carries drift. Session parity cannot relate to returns by
construction — it is the F14 idea (§30) applied to the selection of sessions rather than to
the direction of trades.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from futuresres.signals.state_control import (
    UNMATCHED,
    YEAR_RATIO_TOLERANCE,
    ControlMismatch,
    control_pick,
    make_matched_control,
    paired_state_stats,
    session_clustering,
    trailing_vol_quantile,
    verify_control,
)

BARS: int = 78          # 5-minute RTH session
TOD_BUCKETS: int = 13   # 30 minutes each
WARMUP: int = 60        # sessions of trailing volatility history
N_QUANTILES: int = 5


@dataclass(slots=True)
class World:
    """A synthetic market with a known regime structure and a known truth."""

    state: np.ndarray
    session: np.ndarray
    tod: np.ndarray
    vol_q: np.ndarray
    year: np.ndarray
    returns: np.ndarray

    @property
    def log_price(self) -> np.ndarray:
        return np.concatenate([[0.0], np.cumsum(self.returns)])

    @property
    def direction(self) -> np.ndarray:
        return self.state.astype(float)


def _world(n_sessions: int = 600, seed: int = 0, mu: float = 0.5,
           drift: str = "regime", trend: bool = False) -> World:
    """Sessions with trailing-ranked volatility, a drifting regime, and a fake condition.

    `drift="regime"`: the drift sits on the whole (high volatility, near the open) regime,
    so it is a property of WHEN the condition fires, not of the condition.
    `drift="state"`: the drift sits only where the condition fires, so it is genuine.
    `trend=True`: the condition's base rate rises across years, as P01's micro share does.
    """
    rng = np.random.default_rng(seed)
    n = n_sessions * BARS
    session = np.repeat(np.arange(n_sessions), BARS)
    tod = np.tile(np.arange(BARS) // (BARS // TOD_BUCKETS), n_sessions)
    year = 2019 + session // (n_sessions // 6)

    session_vol = rng.lognormal(0.0, 0.5, n_sessions)
    q = trailing_vol_quantile(session_vol, lookback=WARMUP, n_quantiles=N_QUANTILES)
    vol_q = np.repeat(q, BARS)

    regime = (vol_q >= 3) & (tod <= 2)
    if trend:
        # base rate rises with the year: 1-in-6 sessions early, nearly all of them late
        share = (session - session.min()) / max(session.max() - session.min(), 1)
        picked = (session % 6) < np.ceil(1 + 5 * share)
    else:
        picked = session % 2 == 0          # parity: cannot relate to returns
    state = regime & picked

    returns = rng.normal(0.0, 1.0, n) * np.repeat(session_vol, BARS)
    returns += mu * (state if drift == "state" else regime)
    return World(state, session, tod, vol_q, year, returns)


def _controls(w: World, name: str = "fake", match_year: bool = True,
              mode: str = "strict"):
    """(real bar indices, ControlDraw) for the world's condition."""
    real_idx = np.flatnonzero(w.state & (w.vol_q >= 0) & (w.tod >= 0))
    draw = make_matched_control(w.state, w.session, w.tod, w.vol_q, condition_name=name,
                                year=w.year if match_year else None, session_exclusion=mode)
    return real_idx, draw


# ---------------------------------------------------------------------------------------
# The three that decide whether the control is worth having
# ---------------------------------------------------------------------------------------

def test_a_regime_loaded_condition_with_no_information_beats_the_rotation_null() -> None:
    """The danger, demonstrated rather than assumed.

    Session parity carries no information about returns. The condition still separates,
    because rotation moves its firings out of the drifting regime and compares them against
    bars that never had the drift. This is precisely the hole the matched control fills, and
    if this test ever goes green-by-failing, the other two prove nothing.
    """
    from futuresres.signals.stage1 import evaluate_signed_signal

    w = _world(drift="regime")
    res = evaluate_signed_signal(w.direction, w.log_price, horizon=1,
                                 rng=np.random.default_rng(7))
    assert res.n_signals > 1000, res.n_signals
    assert res.separated, (
        f"the regime-loaded fake was supposed to beat the rotation null, and did not "
        f"({res.reason}) - the fault injection is not injecting anything"
    )
    assert res.mean_shift > 0


def test_the_same_condition_does_not_beat_the_matched_control() -> None:
    """§54's claim, verified: matching the regime removes the false positive."""
    w = _world(drift="regime")
    real_idx, draw = _controls(w)
    paired = draw.index != UNMATCHED
    assert paired.mean() > 0.95, f"only {paired.mean():.1%} matched"

    real_r = w.returns[real_idx[paired]]
    ctrl_r = w.returns[draw.index[paired]]
    _, _, diff, lo, hi, n, p = paired_state_stats(
        real_r, ctrl_r, w.session[real_idx[paired]], np.random.default_rng(11))

    assert n > 1000, n
    assert lo <= 0.0 <= hi, (
        f"the matched control was beaten by a condition with no information: "
        f"diff {diff:+.4f}, CI [{lo:+.4f}, {hi:+.4f}], p {p:.4f}"
    )
    assert p > 0.05, p


def test_a_genuine_state_effect_does_beat_the_matched_control() -> None:
    """Power, so the test above cannot pass by the control being null against everything.

    Same world, same regime, same firings - the only change is that the drift now sits on
    the condition rather than on the regime around it.
    """
    w = _world(drift="state")
    real_idx, draw = _controls(w)
    paired = draw.index != UNMATCHED

    real_r = w.returns[real_idx[paired]]
    ctrl_r = w.returns[draw.index[paired]]
    _, _, diff, lo, hi, n, p = paired_state_stats(
        real_r, ctrl_r, w.session[real_idx[paired]], np.random.default_rng(11))

    assert diff > 0 and lo > 0, (
        f"a real state effect failed to beat its control: diff {diff:+.4f}, "
        f"CI [{lo:+.4f}, {hi:+.4f}] - the control is absorbing the signal, not the confound"
    )
    assert p < 0.05, p


def test_bar_mode_also_refuses_the_regime_loaded_fake_and_keeps_a_real_effect() -> None:
    """Bar mode's contamination costs power, not validity - asserted on both sides.

    Its control bars sit in sessions that fire elsewhere, so they are partly in-state. That
    shrinks a real difference; it cannot manufacture one, because the regimes are still
    matched pair by pair. Strict mode is structurally unavailable to a state firing several
    times a session (P03: 7.81/session, 92.6% of sessions touched), so this mode has to carry
    those conditions and its behaviour is pinned rather than argued.
    """
    fake = _world(drift="regime")
    real_idx, draw = _controls(fake, mode="bar")
    paired = draw.index != UNMATCHED
    assert paired.mean() > 0.99
    assert (fake.session[real_idx[paired]] != fake.session[draw.index[paired]]).all(), \
        "bar mode must still draw from a different session"
    assert not fake.state[draw.index[paired]].any(), "a control bar is itself a firing"

    _, _, diff, lo, hi, _, p = paired_state_stats(
        fake.returns[real_idx[paired]], fake.returns[draw.index[paired]],
        fake.session[real_idx[paired]], np.random.default_rng(11))
    assert lo <= 0.0 <= hi, (
        f"bar mode was beaten by a condition with no information: diff {diff:+.4f}, "
        f"CI [{lo:+.4f}, {hi:+.4f}], p {p:.4f}"
    )

    real = _world(drift="state")
    real_idx, draw = _controls(real, mode="bar")
    paired = draw.index != UNMATCHED
    _, _, diff, lo, hi, _, p = paired_state_stats(
        real.returns[real_idx[paired]], real.returns[draw.index[paired]],
        real.session[real_idx[paired]], np.random.default_rng(11))
    assert diff > 0 and lo > 0 and p < 0.05, (
        f"bar mode absorbed a genuine effect: diff {diff:+.4f}, CI [{lo:+.4f}, {hi:+.4f}]"
    )


def test_clustering_report_says_when_strict_mode_is_unavailable() -> None:
    """The mode is chosen on measured evidence, not preference.

    A state touching nearly every session leaves no clean pool to draw from, which is
    arithmetic: at P03's firing rate an INDEPENDENT state would touch ~99.9% of sessions.
    """
    w = _world()
    sparse = session_clustering(w.state, w.session)
    assert sparse.strict_is_available, sparse

    # bar-level and frequent: fires in every session that has a defined volatility rank
    dense = session_clustering((w.vol_q >= 0) & (w.tod <= 8), w.session)
    assert dense.sessions_touched_share > 0.85
    assert not dense.strict_is_available, dense
    assert dense.clean_sessions < sparse.clean_sessions


# ---------------------------------------------------------------------------------------
# The construction's guarantees
# ---------------------------------------------------------------------------------------

def test_controls_never_come_from_a_session_the_state_touches() -> None:
    """§47 measured 0.952 session autocorrelation, so a quiet minute of a firing session is
    contaminated by the state it is meant to stand in for. Excluding whole sessions also
    makes the "different session" requirement automatic rather than a second filter."""
    w = _world()
    _, draw = _controls(w)
    picked = draw.index[draw.index != UNMATCHED]
    assert not w.state[picked].any(), "a control bar is itself a firing"
    touched = set(w.session[w.state].tolist())
    assert not set(w.session[picked].tolist()) & touched, "a control sits in a firing session"


def test_controls_are_drawn_from_the_matched_cell_pair_by_pair() -> None:
    """Not matched on average - matched for every single pair."""
    w = _world()
    real_idx, draw = _controls(w)
    paired = draw.index != UNMATCHED
    r, c = real_idx[paired], draw.index[paired]
    assert (w.tod[r] == w.tod[c]).all(), "time-of-day bucket differs within a pair"
    assert (w.vol_q[r] == w.vol_q[c]).all(), "volatility quantile differs within a pair"


def test_selection_is_deterministic_across_processes() -> None:
    """SHA-256 of (condition, session, bucket, quantile, index), never salted `hash()`.

    The salted-hash bug forced a floor sweep to be discarded and re-run earlier in this
    project; `levels/placebo.py` carries the same discipline for the same reason.
    """
    a = [control_pick("p03", 12, 3, 4, i, 977) for i in range(50)]
    b = [control_pick("p03", 12, 3, 4, i, 977) for i in range(50)]
    assert a == b
    assert a != [control_pick("p01", 12, 3, 4, i, 977) for i in range(50)]
    assert all(0 <= p < 977 for p in a)

    w = _world(n_sessions=200)
    assert np.array_equal(_controls(w)[1].index, _controls(w)[1].index)


def test_trailing_volatility_ranking_is_causal() -> None:
    """A session is ranked against its predecessors only - never itself, never the future."""
    vol = np.arange(200, dtype=float)          # strictly increasing
    q = trailing_vol_quantile(vol, lookback=WARMUP, n_quantiles=N_QUANTILES)
    assert (q[:WARMUP] == -1).all(), "no ranking before the lookback is available"
    assert (q[WARMUP:] == N_QUANTILES - 1).all(), (
        "a strictly rising series must rank top against its own past at every point"
    )
    falling = trailing_vol_quantile(vol[::-1].copy(), lookback=WARMUP,
                                    n_quantiles=N_QUANTILES)
    assert (falling[WARMUP:] == 0).all()

    with pytest.raises(ValueError, match="too few prior sessions"):
        trailing_vol_quantile(vol, lookback=3, n_quantiles=5)


# ---------------------------------------------------------------------------------------
# verify_control: fault injection, the §41/§52 pattern
# ---------------------------------------------------------------------------------------

def test_verify_passes_a_correctly_built_control() -> None:
    w = _world()
    real_idx, draw = _controls(w)
    rep = verify_control("fake", "MNQ", real_idx, draw, w.tod, w.vol_q, w.year)
    assert rep.verdict == "MATCHED", rep.failures
    assert rep.tod_max_ratio_dev == 0.0 and rep.vol_max_ratio_dev == 0.0, (
        "matched by construction means exactly matched, not approximately"
    )


def test_verify_catches_a_control_drawn_from_the_wrong_volatility_regime() -> None:
    """The defect the check exists for: controls in a calmer regime than the real firings.

    Injected by rebuilding the controls against a corrupted volatility array, so the failure
    is produced by a genuinely wrong construction rather than by editing the report.
    """
    w = _world()
    real_idx, _ = _controls(w)
    wrong = np.where(w.vol_q >= 0, 0, -1)      # every bar declared the calmest quantile
    bad = make_matched_control(w.state, w.session, w.tod, wrong, condition_name="fake",
                               year=w.year)
    rep = verify_control("fake", "MNQ", real_idx, bad, w.tod, w.vol_q, w.year, strict=False)
    assert rep.verdict == "FAIL"
    assert any("VOLATILITY MISMATCH" in f for f in rep.failures), rep.failures

    with pytest.raises(ControlMismatch, match="VOLATILITY MISMATCH"):
        verify_control("fake", "MNQ", real_idx, bad, w.tod, w.vol_q, w.year)


def test_verify_catches_a_control_drawn_from_the_wrong_time_of_day() -> None:
    """Same injection on the other designed axis."""
    w = _world()
    real_idx, _ = _controls(w)
    flat_tod = np.zeros_like(w.tod)
    bad = make_matched_control(w.state, w.session, flat_tod, w.vol_q,
                               condition_name="fake", year=w.year)
    rep = verify_control("fake", "MNQ", real_idx, bad, w.tod, w.vol_q, w.year, strict=False)
    assert rep.verdict == "FAIL"
    assert any("TIME-OF-DAY MISMATCH" in f for f in rep.failures), rep.failures


def test_a_trending_state_reports_a_year_mismatch_rather_than_absorbing_it() -> None:
    """P01's shape, and the reason the year is left free.

    A state whose base rate rises across the sample runs out of same-year sessions in its late
    years, so those pairs fall back to the year-blind pool and the fallback rate reports it
    (~28% here, at every sample size tried). The comparison is blocked, which is the honest
    outcome: an adoption curve would otherwise pass as a signal.
    """
    w = _world(trend=True)
    real_idx, draw = _controls(w, name="p01-like")
    rep = verify_control("p01-like", "MNQ", real_idx, draw,
                         w.tod, w.vol_q, w.year, strict=False)
    assert rep.verdict == "FAIL"
    assert any("ERA FALLBACK" in f for f in rep.failures), rep.failures
    assert rep.fallback_rate > 0.2, rep.fallback_rate
    # and the designed axes are still matched - the failure is specifically the era
    assert rep.tod_max_ratio_dev == 0.0 and rep.vol_max_ratio_dev == 0.0


def test_leaving_the_year_free_fails_well_behaved_conditions_at_the_real_sample_shape() -> None:
    """Why the year is matched rather than merely measured. The measurement, pinned.

    The first design left the year free and tested it with the same ratio check as the other
    two axes. That check has a NOISE FLOOR: how many high-volatility sessions land in each
    year is itself random, so a condition with no year trend at all breaches the tolerance at
    ~260 sessions/year over 16 years - the real sample's shape. Widening the tolerance until
    the synthetic world passed would have been fitting the null to the test, which is the
    error `levels/placebo.py` records about its own bounds. The construction changed instead.

    This test fails if anyone reverts to the year-blind draw, and it shows the fix working on
    the same world.
    """
    w = _world(n_sessions=4200)
    w.year[:] = 2010 + (w.session * 16) // 4200          # 16 years, ~262 sessions each
    real_idx, blind = _controls(w, name="free-year", match_year=False)
    free = verify_control("free-year", "MNQ", real_idx, blind,
                          w.tod, w.vol_q, w.year, strict=False)
    assert free.year_max_ratio_dev > YEAR_RATIO_TOLERANCE, (
        f"the year-blind draw was supposed to breach its own tolerance on a condition with "
        f"no year trend, and did not ({free.year_max_ratio_dev:.3f}) - the measurement that "
        f"justified matching the year no longer reproduces"
    )

    real_idx, drawn = _controls(w, name="free-year", match_year=True)
    fixed = verify_control("free-year", "MNQ", real_idx, drawn,
                           w.tod, w.vol_q, w.year, strict=False)
    assert fixed.verdict == "MATCHED", fixed.failures
    assert fixed.year_max_ratio_dev == 0.0 and fixed.fallback_rate == 0.0


def test_a_condition_that_occupies_its_whole_cell_is_degenerate_and_says_so() -> None:
    """No session in the cell is free of the state, so no control exists at all.

    This is a property of the condition - it owns its regime - not a tuning failure, and it
    must surface as its own failure kind rather than as an ordinary mismatch someone later
    tries to fix with a different bucketing. Same distinction §49 drew between DEGENERATE and
    TOUCH-RATE MISMATCH.
    """
    w = _world()
    every = (w.vol_q >= 3) & (w.tod <= 2)      # the whole regime, no parity carve-out
    ctrl = make_matched_control(every, w.session, w.tod, w.vol_q, condition_name="greedy",
                                year=w.year)
    assert (ctrl.index == UNMATCHED).all()
    assert not ctrl.fell_back.any(), "an unmatched pair must not be recorded as a fallback"

    real_idx = np.flatnonzero(every)
    rep = verify_control("greedy", "MNQ", real_idx, ctrl, w.tod, w.vol_q, w.year,
                         strict=False)
    assert rep.verdict == "FAIL"
    assert any("DEGENERATE" in f for f in rep.failures), rep.failures


def test_paired_statistic_matches_the_level_series_implementation() -> None:
    """Pinned against `sweep_stage1.paired_stats` (§38) so the two cannot drift apart.

    The state control reimplements it to avoid importing the level machinery; that is only
    acceptable if it stays identical, which is a fact to assert rather than to intend.
    """
    from futuresres.signals.sweep_stage1 import paired_stats

    rng = np.random.default_rng(3)
    real = rng.normal(0.2, 1.0, 900)
    ctrl = rng.normal(0.0, 1.0, 900)
    rows = np.repeat(np.arange(90), 10)

    a = paired_state_stats(real, ctrl, rows, np.random.default_rng(5))
    b = paired_stats(real, ctrl, rows, np.random.default_rng(5))
    assert np.allclose(np.array(a, dtype=float), np.array(b, dtype=float), equal_nan=True), \
        f"\nstate_control: {a}\nsweep_stage1: {b}"


def test_too_few_events_returns_nan_rather_than_a_number() -> None:
    """§6: under 100 events is no information, and must not look like a measurement."""
    rng = np.random.default_rng(0)
    out = paired_state_stats(rng.normal(size=50), rng.normal(size=50),
                             np.arange(50), np.random.default_rng(1))
    assert out[5] == 50 and np.isnan(out[2])
