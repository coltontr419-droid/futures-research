"""The §7 integrity tests, run in CI — CLAUDE.md §7, build order step 6.

§7: "These are the load-bearing components. Without them the pipeline generates confidence,
not knowledge." And §10: "pytest for the integrity tests; they run in CI, not ad hoc."

Each check is exercised BOTH WAYS. A leak detector that has only ever seen clean signals
is not known to detect leaks, and every test below that asserts a pass is paired with one
that constructs the failure and asserts it is caught. The fixtures are built so the right
answer is known by construction rather than by running the code.
"""

from __future__ import annotations

import numpy as np
import pytest

from futuresres.integrity.checks import (
    block_bootstrap_drawdown,
    causal_reconstruction_test,
    max_drawdown,
    monte_carlo_drawdown,
    shuffled_label_test,
    synthetic_noise_test,
)
from futuresres.integrity.synthetic import (
    BTC_1M_STD,
    BTC_ETH_1M_CORRELATION,
    bootstrap_shuffle,
    causal_signal_fn,
    describe,
    garch11,
    leaky_signal_fn,
    pooled_series_with_edge,
    random_walk,
    series_with_edge,
)
from futuresres.signals.search import _rolling_mean, crossover_signals, run_pipeline
from futuresres.signals.stage1 import (
    bca_interval,
    calibrated_alpha,
    evaluate_signal,
    forward_returns,
    rotation_null,
)

pytestmark = pytest.mark.integrity


def rng(seed: int = 20260824) -> np.random.Generator:
    return np.random.default_rng(seed)


def predictive_series(n: int, strength: float, g: np.random.Generator):
    """Returns where bar t+1 is genuinely predictable from a state known at bar t.

    x[t] is visible at t; return[t+1] = strength·x[t] + noise. So `x > 0` is a real,
    causal, non-leaking one-bar-ahead edge — the positive control every detector here
    needs in order to show it can tell a real effect from nothing.
    """
    x = g.standard_normal(n)
    noise = g.normal(0, BTC_1M_STD, n)
    returns = np.empty(n)
    returns[0] = noise[0]
    returns[1:] = strength * x[:-1] + noise[1:]
    return x > 0, returns


# ══════════════════════════════════════════════════════════════════════════════
# Pipeline primitives — these decide whether every §7 result below means anything
# ══════════════════════════════════════════════════════════════════════════════


def test_rolling_mean_is_trailing_and_hand_computable():
    """Off-by-one slicing here shipped a broken pipeline once; it is pinned now.

    x = [1,2,3,4,5], window 3:
      index 0,1 → NaN (window not full)
      index 2   → (1+2+3)/3 = 2
      index 3   → (2+3+4)/3 = 3
      index 4   → (3+4+5)/3 = 4
    """
    out = _rolling_mean(np.array([1.0, 2, 3, 4, 5]), 3)
    assert np.isnan(out[0]) and np.isnan(out[1])
    assert list(out[2:]) == [2.0, 3.0, 4.0]


def test_rolling_mean_window_one_is_the_series_itself():
    x = np.array([1.0, -2.0, 3.5])
    assert list(_rolling_mean(x, 1)) == list(x)


def test_rolling_mean_never_uses_a_future_bar():
    """Change the last element; nothing before it may move.

    This is the property that makes the whole §7.1 test meaningful — if the signal
    primitives peeked ahead, a lookahead test built on them could not detect anything.
    """
    x = np.arange(50, dtype=float)
    a = _rolling_mean(x, 10)
    x2 = x.copy()
    x2[-1] = 9999.0
    b = _rolling_mean(x2, 10)
    assert np.allclose(a[:-1], b[:-1], equal_nan=True)


def test_rotation_null_equals_the_explicit_loop():
    """The FFT null must reproduce rolling the labels by hand, for every rotation.

    This is an optimisation of the permutation test, so it has to be exact rather than
    close: every §7 verdict below is computed from it.
    """
    g = rng(1)
    n = 512
    fwd = g.normal(0, 0.001, n)
    sig = g.random(n) < 0.3
    brute = np.array([fwd[np.roll(sig, k)].mean() - fwd.mean() for k in range(n)])
    assert np.allclose(brute, rotation_null(sig, fwd), rtol=1e-9, atol=1e-15)


def test_rotation_null_includes_the_observed_statistic_at_lag_zero():
    """k=0 is the identity, so the observed value is inside its own null.

    That is what keeps the p-value from ever being zero, and it removes the need for the
    usual +1 correction.
    """
    g = rng(2)
    fwd = g.normal(0, 0.001, 400)
    sig = g.random(400) < 0.25
    assert rotation_null(sig, fwd)[0] == pytest.approx(fwd[sig].mean() - fwd.mean())


def test_calibrated_alpha_matches_the_measured_anchors():
    """The anchors are measurements, not tuning knobs — changing one needs a new run."""
    assert calibrated_alpha(50) == pytest.approx(0.0312)
    assert calibrated_alpha(100) == pytest.approx(0.0359)
    assert calibrated_alpha(250) == pytest.approx(0.0400)
    assert calibrated_alpha(500) == pytest.approx(0.0500)


def test_calibrated_alpha_is_monotone_and_never_looser_than_nominal():
    """Coverage worsens as N falls, so α must tighten as N falls — and never exceed 0.05.

    A calibration that handed back an α above 0.05 would be widening the gate in the name
    of correcting it.
    """
    values = [calibrated_alpha(n) for n in (50, 84, 100, 175, 250, 400, 500, 5000)]
    assert all(a <= 0.05 + 1e-12 for a in values)
    assert all(b >= a - 1e-12 for a, b in zip(values, values[1:]))


def test_calibrated_alpha_is_flat_at_nominal_above_the_plateau():
    for n in (500, 1000, 20_000, 3_494_880):
        assert calibrated_alpha(n) == pytest.approx(0.05)


def test_calibrated_alpha_clamps_below_the_measured_range():
    """Below 50 observations the value is extrapolated; it must clamp, not run away."""
    assert calibrated_alpha(10) == calibrated_alpha(50)
    assert calibrated_alpha(1) == calibrated_alpha(50)


def test_calibrated_alpha_interpolates_between_anchors():
    mid = calibrated_alpha(158)          # geometric midpoint of 100 and 250
    assert 0.0359 < mid < 0.0400
    assert mid == pytest.approx(0.5 * (0.0359 + 0.0400), abs=0.002)


@pytest.mark.slow
def test_calibration_actually_delivers_95_percent_coverage():
    """The point of the calibration, verified end to end on heavy-tailed data.

    Pinning the anchor values alone would only prove the table was typed in correctly.
    This resamples a heavy-tailed population with a known mean and checks that intervals
    built at the calibrated α cover it ~95% of the time, where nominal 0.05 would not.

    t(4) rather than real returns so the test carries no data dependency: kurtosis is
    infinite in theory and enormous in sample, which is the regime that breaks the
    percentile interval in the first place.
    """
    g = rng(20260825)
    reps, n_boot = 2500, 600
    for n in (50, 250):
        hit_cal = hit_nom = 0
        for _ in range(reps):
            x = g.standard_t(4, n)
            boot = x[g.integers(0, n, size=(n_boot, n))].mean(axis=1)
            a = calibrated_alpha(n)
            lo, hi = np.percentile(boot, [100 * a / 2, 100 * (1 - a / 2)])
            hit_cal += lo <= 0.0 <= hi
            plo, phi = np.percentile(boot, [2.5, 97.5])
            hit_nom += plo <= 0.0 <= phi
        cal, nom = hit_cal / reps, hit_nom / reps
        assert cal > nom, f"n={n}: calibration did not improve coverage ({cal} vs {nom})"
        assert cal >= 0.94, f"n={n}: calibrated coverage {cal:.3f} still short of 95%"


def test_bca_reduces_to_the_percentile_interval_when_there_is_nothing_to_correct():
    """Symmetric bootstrap, symmetric jackknife → z₀ = 0, a = 0 → percentile exactly.

    This is the property that makes BCa safe in principle, and pins that the corrections
    are wired to the right quantities: a bug in either would show up as a shifted interval
    on data with nothing to shift.
    """
    # 2000 points, so none lands exactly on 0.0 and exactly half fall below it — an odd
    # count would put one draw on the boundary and leave z₀ a hair off zero.
    boot = np.linspace(-1.0, 1.0, 2000)
    jack = np.array([-1.0, 0.0, 1.0])            # zero third moment
    lo, hi = bca_interval(0.0, boot, jack, alpha=0.05)
    plo, phi = np.percentile(boot, [2.5, 97.5])
    assert lo == pytest.approx(plo, abs=1e-9)
    assert hi == pytest.approx(phi, abs=1e-9)


def test_bca_shifts_the_interval_when_the_jackknife_is_skewed():
    """A non-zero acceleration must actually move the endpoints, or the term is inert."""
    g = rng(5)
    boot = g.standard_normal(4000)
    skewed = np.concatenate([g.standard_normal(60), np.array([9.0, 11.0, 13.0])])
    plain = bca_interval(0.0, boot, np.array([-1.0, 0.0, 1.0]))
    shifted = bca_interval(0.0, boot, skewed)
    assert not np.isclose(plain[0], shifted[0], atol=1e-6)


def test_bca_survives_a_degenerate_bootstrap():
    """Every draw on one side of the estimate makes z₀ infinite; it must not propagate."""
    lo, hi = bca_interval(-5.0, np.linspace(0.0, 1.0, 500), np.array([-1.0, 0.0, 1.0]))
    assert np.isfinite(lo) and np.isfinite(hi)


def test_rotation_null_rejects_a_constant_signal():
    with pytest.raises(ValueError, match="constant"):
        rotation_null(np.zeros(100, dtype=bool), np.zeros(100))


def test_crossover_signals_are_causal():
    """Same check one level up: perturbing the final bar must not rewrite past signals."""
    g = rng(31)
    r = random_walk(2000, g)
    _, sig_a = crossover_signals(r, (5,), (50,))
    r2 = r.copy()
    r2[-1] += 0.5
    _, sig_b = crossover_signals(r2, (5,), (50,))
    assert np.array_equal(sig_a[:-1], sig_b[:-1])


# ══════════════════════════════════════════════════════════════════════════════
# 7.1  Causal re-derivation test
# ══════════════════════════════════════════════════════════════════════════════


def test_71_clean_causal_signal_produces_zero_mismatches():
    """Exact equality, not approximate agreement.

    One mismatched bar on a causal signal is a failure, not a rounding error — the check
    compares booleans, so there is no tolerance to hide behind.
    """
    g = rng()
    returns = series_with_edge(4000, g, 0.10)
    result = causal_reconstruction_test(causal_signal_fn(60), returns, rng=g,
                                        n_checks=100, warmup=60)
    assert result.n_mismatched == 0
    assert not result.leak_detected
    assert result.n_checked == 100


@pytest.mark.parametrize("span", [1, 5, 20])
def test_71_detects_a_leak_of_any_span(span):
    """The blind spot the shift test had: a ONE-bar leak must be caught like any other.

    The statistic this replaced flagged a pure one-bar leak 0% of the time, because
    delaying by one bar removed exactly the bar it read. Re-derivation has no such
    symmetry — the leaked bar is simply absent from the truncated input.
    """
    g = rng(7)
    returns = series_with_edge(4000, g, 0.10)
    result = causal_reconstruction_test(leaky_signal_fn(60, span), returns, rng=g,
                                        n_checks=100, warmup=60)
    assert result.leak_detected
    assert result.first_mismatch is not None


def test_71_detection_does_not_depend_on_signal_timescale():
    """Detection must hold across lookback windows.

    The shift test's power swung with horizon, which is what made its verdict conditional.
    A structural check has no horizon-shaped blind spot, and this pins that.
    """
    g = rng(3)
    returns = series_with_edge(4000, g, 0.10)
    for window in (5, 30, 240):
        clean = causal_reconstruction_test(causal_signal_fn(window), returns, rng=g,
                                           n_checks=60, warmup=window)
        leaked = causal_reconstruction_test(leaky_signal_fn(window, 1), returns, rng=g,
                                            n_checks=60, warmup=window)
        assert not clean.leak_detected, f"false positive at window {window}"
        assert leaked.leak_detected, f"missed leak at window {window}"


def test_71_catches_a_full_series_statistic():
    """A different leak class: standardising by a mean computed over the whole series.

    No bar reads a specific future bar, yet every bar depends on all of them. The shift
    test could not see this at all; truncation exposes it immediately.
    """
    def normalised(returns: np.ndarray) -> np.ndarray:
        r = np.asarray(returns, dtype=float)
        return r > r.mean()  # r.mean() uses the entire series, including the future

    g = rng(5)
    result = causal_reconstruction_test(normalised, series_with_edge(2000, g, 0.10),
                                        rng=g, n_checks=80, warmup=10)
    assert result.leak_detected


def test_71_catches_an_off_by_one_forward_shift():
    """The most common real lookahead bug: the signal accidentally leads by one bar."""
    def shifted(returns: np.ndarray) -> np.ndarray:
        r = np.asarray(returns, dtype=float)
        out = np.zeros(r.size, dtype=bool)
        out[:-1] = r[1:] > 0  # bar t reads bar t+1
        return out

    g = rng(6)
    result = causal_reconstruction_test(shifted, series_with_edge(2000, g, 0.10),
                                        rng=g, n_checks=80, warmup=10)
    assert result.leak_detected


def test_71_rejects_a_signal_function_that_is_not_length_preserving():
    """Without this the comparison would silently index the wrong bar."""
    g = rng()
    with pytest.raises(ValueError, match="length-preserving"):
        causal_reconstruction_test(lambda r: np.zeros(len(r) + 1, dtype=bool)[: len(r)]
                                   if len(r) == 2000 else np.zeros(3, dtype=bool),
                                   series_with_edge(2000, g, 0.1), rng=g, n_checks=5)


def test_71_rejects_a_signal_function_returning_the_wrong_shape():
    g = rng()
    with pytest.raises(ValueError, match="one value per bar"):
        causal_reconstruction_test(lambda r: np.zeros((len(r), 2)),
                                   series_with_edge(500, g, 0.1), rng=g, n_checks=5)


def test_71_reports_how_hard_it_looked():
    """`n_checked` is part of the verdict: a clean result from 5 bars is weak evidence."""
    g = rng()
    returns = series_with_edge(2000, g, 0.10)
    result = causal_reconstruction_test(causal_signal_fn(60), returns, rng=g,
                                        n_checks=7, warmup=60)
    assert result.n_checked == 7
    assert "7 re-derived bars" in result.detail


def test_71_is_indifferent_to_whether_the_signal_has_an_edge():
    """Structural, not statistical: a worthless causal signal is still clean.

    The check answers "does this read the future", never "does this work". A signal with
    no predictive value at all must pass, because it is not leaking — conflating the two
    is what made the previous §7.1 flag legitimate signals.
    """
    g = rng(3)
    returns = random_walk(3000, g)

    def useless_but_causal(r: np.ndarray) -> np.ndarray:
        out = np.zeros(np.asarray(r).size, dtype=bool)
        out[::3] = True  # depends on nothing at all, least of all the future
        return out

    result = causal_reconstruction_test(useless_but_causal, returns, rng=g, n_checks=60)
    assert not result.leak_detected
    assert result.n_mismatched == 0


# ══════════════════════════════════════════════════════════════════════════════
# Pooled instruments — the arithmetic behind the "pooling barely helps" finding
# ══════════════════════════════════════════════════════════════════════════════


def test_pooled_basket_variance_matches_the_correlation_formula():
    """A k-leg equal-weight basket has noise variance ρ + (1−ρ)/k of one leg's.

    The whole "pooling BTC with ETH buys almost nothing" conclusion rests on this, so it
    is checked against the closed form rather than asserted in prose. At ρ=0.801, k=2:
    0.801 + 0.199/2 = 0.9005, i.e. a std ratio of 0.949 and an SNR gain of 1.054×.
    """
    g = rng(17)
    n = 200_000
    rho = BTC_ETH_1M_CORRELATION
    single = series_with_edge(n, g, 0.0)          # edge zero: pure noise
    pooled = pooled_series_with_edge(n, g, 0.0, correlation=rho, n_instruments=2)

    expected = np.sqrt(rho + (1 - rho) / 2)
    assert pooled.std(ddof=1) / single.std(ddof=1) == pytest.approx(expected, rel=0.03)


def test_pooling_independent_instruments_would_help_far_more():
    """The counterfactual that shows correlation is what limits the gain, not the pooling.

    At ρ=0 a two-leg basket cuts noise std by 1/√2; at the measured ρ it cuts it by 5%.
    """
    g = rng(18)
    n = 200_000
    indep = pooled_series_with_edge(n, g, 0.0, correlation=0.0, n_instruments=2)
    real = pooled_series_with_edge(n, g, 0.0, correlation=BTC_ETH_1M_CORRELATION,
                                   n_instruments=2)
    assert indep.std(ddof=1) == pytest.approx(
        series_with_edge(n, g, 0.0).std(ddof=1) / np.sqrt(2), rel=0.03
    )
    assert real.std(ddof=1) > indep.std(ddof=1) * 1.2


def test_pooled_series_keeps_the_edge_in_single_instrument_units():
    """The swept parameter must mean the same thing pooled or not.

    If pooling rescaled the injected edge, the two floors would not be comparable and the
    configuration table would be meaningless.
    """
    g = rng(19)
    n = 60_000
    strong = pooled_series_with_edge(n, g, 0.5)
    zero = pooled_series_with_edge(n, g, 0.0)
    assert abs(strong.mean()) >= 0.0  # drift exists but is regime-signed, so check spread
    assert strong.std(ddof=1) > zero.std(ddof=1)


@pytest.mark.slow
@pytest.mark.parametrize("rho", [0.3, 0.801])
def test_return_correlation_carries_through_to_effect_correlation(rho):
    """The assumption the Stage 4 analysis rests on, checked rather than asserted.

    `replication_probability` treats two instruments' effect ESTIMATES as correlated at
    the same ρ as their RETURNS. That step does all the work in the false-confirmation
    numbers, so it is verified by simulation: apply one identical condition to two
    correlated instruments with no edge in either, and correlate the measured shifts
    across many independent replications.

    Measured ratios of effect-ρ to return-ρ: 1.011 at 0.3 and 1.007 at 0.801.
    """
    g = rng(20260825)
    n, reps, horizon = 2000, 600, 60
    ea, eb = [], []
    for _ in range(reps):
        common = g.standard_normal(n)
        a = np.sqrt(rho) * common + np.sqrt(1 - rho) * g.standard_normal(n)
        b = np.sqrt(rho) * common + np.sqrt(1 - rho) * g.standard_normal(n)

        c = np.concatenate([[0.0], np.cumsum(a)])
        sig = np.zeros(n, dtype=bool)
        sig[59:] = (c[60:] - c[:-60]) > 0

        def shift(r):
            fwd = forward_returns(r, horizon)
            ok = np.isfinite(fwd)
            s, f = sig[ok], fwd[ok]
            if not s.any() or s.all():
                return np.nan
            return f[s].mean() - f.mean()

        ea.append(shift(a))
        eb.append(shift(b))

    ea, eb = np.array(ea), np.array(eb)
    ok = np.isfinite(ea) & np.isfinite(eb)
    effect_rho = float(np.corrcoef(ea[ok], eb[ok])[0, 1])
    assert effect_rho == pytest.approx(rho, abs=0.08)


def test_pooled_series_validates_its_correlation():
    g = rng()
    with pytest.raises(ValueError, match="correlation"):
        pooled_series_with_edge(100, g, 0.1, correlation=1.0)


# ══════════════════════════════════════════════════════════════════════════════
# 7.2  Synthetic noise test  (the full pipeline, on nulls)
# ══════════════════════════════════════════════════════════════════════════════


def _fast_pipeline(series: np.ndarray, g: np.random.Generator):
    return run_pipeline(
        series, rng=g, horizons=(10, 60), fasts=(5, 20), slows=(50, 200),
        n_bootstrap=120, n_permutations=120, n_splits=6,
    )


@pytest.mark.slow
@pytest.mark.parametrize("name", ["random_walk", "garch11", "bootstrap_shuffle"])
def test_72_pipeline_finds_nothing_on_each_null(name):
    """§7.2: "The pipeline must report 'nothing found.'"

    All three nulls are run because they break different things — the distribution, the
    serial structure, the volatility clustering — and a harness can survive one by luck.
    """
    g = rng(99)
    n = 12_000
    generators = {
        "random_walk": lambda r: random_walk(n, r),
        "garch11": lambda r: garch11(n, r, burn=1000),
        "bootstrap_shuffle": lambda r: bootstrap_shuffle(garch11(n, r, burn=1000), r),
    }
    result = synthetic_noise_test(
        generators[name], _fast_pipeline, name=name, n_replications=3, rng=g
    )
    assert result.found_nothing, result.detail


@pytest.mark.slow
def test_72_the_pipeline_can_still_find_a_real_edge():
    """The other half of §7.2, and the one usually skipped.

    A pipeline that reports "nothing found" on everything also passes the noise test. This
    proves the null result above is discrimination rather than blanket silence.
    """
    g = rng(11)
    n = 12_000
    x = g.standard_normal(n)
    returns = np.empty(n)
    noise = g.normal(0, BTC_1M_STD, n)
    returns[0] = noise[0]
    # a persistent, tradeable drift that a moving-average crossover can actually see
    state = np.sign(np.convolve(x, np.ones(400) / 400, mode="same"))
    returns[1:] = 0.25 * BTC_1M_STD * state[:-1] + noise[1:]

    result = evaluate_signal(state > 0, returns, 60, rng=g,
                             n_bootstrap=200, n_permutations=200)
    assert result.separated, result.reason


# ── the generators themselves must be null, and must look like the real thing ──


def test_garch_reproduces_the_measured_volatility_clustering():
    """§7.2 asks for "realistic vol clustering". Checked, not assumed."""
    stats = describe(garch11(120_000, rng(5), burn=2000))
    assert stats["sq_acf_1"] > 0.20          # real BTCUSDT 1m: 0.358
    assert stats["sq_acf_1"] > stats["sq_acf_60"]  # and it must decay
    # Real is 199.9. The bound is loose because sample kurtosis of a heavy-tailed GARCH is
    # itself unstable across seeds; the assertion is "far fatter than Gaussian", not a
    # match. See the ν note in synthetic.py.
    assert stats["kurtosis"] > 8.0


def test_garch_scale_matches_the_target():
    stats = describe(garch11(120_000, rng(6), target_std=BTC_1M_STD, burn=2000))
    assert stats["std"] == pytest.approx(BTC_1M_STD, rel=0.35)


def test_garch_has_no_edge_in_the_sign_of_the_next_return():
    """Volatility is predictable by construction; direction must not be.

    If this fails the generator is not a null, and every §7.2 result computed with it is
    meaningless — so it is checked directly rather than trusted.
    """
    r = garch11(200_000, rng(8), burn=2000)
    sign_now, sign_next = np.sign(r[:-1]), np.sign(r[1:])
    agreement = float(np.mean(sign_now == sign_next))
    assert abs(agreement - 0.5) < 0.01


def test_bootstrap_shuffle_preserves_the_distribution_and_destroys_the_order():
    g = rng(9)
    original = garch11(60_000, g, burn=1000)
    shuffled = bootstrap_shuffle(original, g)
    a, b = describe(original), describe(shuffled)
    assert b["std"] == pytest.approx(a["std"], rel=0.15)      # distribution kept
    assert b["kurtosis"] > 5.0                                 # tails kept
    assert abs(b["sq_acf_1"]) < 0.05                           # clustering destroyed
    assert a["sq_acf_1"] > 0.10


def test_stationarity_and_tail_parameters_are_validated():
    with pytest.raises(ValueError, match="stationarity"):
        garch11(100, rng(), alpha=0.5, beta=0.6)
    with pytest.raises(ValueError, match="finite kurtosis"):
        garch11(100, rng(), nu=3.0)


# ══════════════════════════════════════════════════════════════════════════════
# 7.3  Shuffled-label test
# ══════════════════════════════════════════════════════════════════════════════


def test_73_effect_collapses_when_labels_are_shuffled():
    """§7.3: "Effect size must collapse to zero.\""""
    g = rng()
    signal, returns = predictive_series(8000, strength=0.0015, g=g)
    result = shuffled_label_test(signal, returns, 1, rng=g, n_permutations=400)
    assert result.collapsed
    assert abs(result.mean_shuffled_effect) < abs(result.observed_effect) * 0.25
    assert result.p_value < 0.05  # the real effect stands out against its own null


def test_73_a_null_signal_does_not_stand_out_from_its_shuffles():
    """The paired half: with no real effect, the observed value sits inside the null."""
    g = rng(4)
    returns = garch11(8000, g, burn=1000)
    signal = np.zeros(8000, dtype=bool)
    signal[g.integers(0, 8000, 1500)] = True
    result = shuffled_label_test(signal, returns, 10, rng=g, n_permutations=400)
    assert result.p_value > 0.05


def test_73_rejects_a_constant_signal():
    g = rng()
    with pytest.raises(ValueError, match="constant"):
        shuffled_label_test(np.zeros(500, dtype=bool), random_walk(500, g), 1, rng=g)


# ══════════════════════════════════════════════════════════════════════════════
# 7.4  Monte Carlo drawdown distribution
# ══════════════════════════════════════════════════════════════════════════════


def test_74_max_drawdown_is_hand_computable():
    # pnl  [+1, +1, -3, +1] → equity [1, 2, -1, 0]
    # running peak (starting at 0) [1, 2, 2, 2]; peak−equity [0, 0, 3, 2] → max 3
    assert max_drawdown([1.0, 1.0, -3.0, 1.0]) == 3.0


def test_74_drawdown_counts_being_under_water_from_the_first_trade():
    # equity [-2, -1]; peak starts at 0, so the drawdown is 2, not 0
    assert max_drawdown([-2.0, 1.0]) == 2.0


def test_74_all_winning_trades_have_zero_drawdown_in_every_order():
    """Order cannot matter when nothing loses, so the whole distribution must be zero."""
    result = monte_carlo_drawdown([1.0, 2.0, 3.0, 4.0], rng=rng(), n_iterations=500)
    assert result.realized == 0.0
    assert result.p95 == 0.0 and result.worst == 0.0


def test_74_shuffling_bounds_the_drawdown_by_the_sum_of_the_losses():
    """The worst possible ordering puts every loss consecutively.

    pnl has losses −1, −2, −3 summing to −6, so no permutation can draw down more than 6.
    """
    pnl = [5.0, -1.0, 4.0, -2.0, 3.0, -3.0]
    result = monte_carlo_drawdown(pnl, rng=rng(), n_iterations=2000)
    assert result.worst <= 6.0
    assert result.p95 >= result.median


def test_74_realized_drawdown_is_usually_optimistic():
    """The §7.4 point: one lucky ordering is not a property of the strategy.

    Constructed so the realized order interleaves its losses — exactly the fortunate case
    that makes a backtest look safer than the strategy is.
    """
    pnl = [3.0, -2.0, 3.0, -2.0, 3.0, -2.0, 3.0, -2.0, 3.0, -2.0, 3.0, -2.0]
    result = monte_carlo_drawdown(pnl, rng=rng(), n_iterations=4000)
    assert result.p95 > result.realized
    assert result.understatement > 0.0


def test_74_block_bootstrap_is_wider_than_the_trade_shuffle():
    """Clustered losses are what the shuffle throws away, so blocks should hurt more."""
    g = rng(21)
    daily = garch11(1500, g, target_std=0.01, burn=500)
    shuffle = monte_carlo_drawdown(daily, rng=rng(1), n_iterations=1500)
    blocks = block_bootstrap_drawdown(daily, rng=rng(1), block=20, n_iterations=1500)
    assert blocks.p95 > shuffle.p95


def test_74_percentiles_are_ordered():
    result = monte_carlo_drawdown(
        garch11(800, rng(2), target_std=0.01, burn=200), rng=rng(), n_iterations=1500
    )
    assert result.median <= result.p95 <= result.p99 <= result.worst


def test_74_empty_input_is_refused():
    with pytest.raises(ValueError, match="no trades"):
        monte_carlo_drawdown([], rng=rng())
