"""Tests for §6's statistical machinery: trial log, DSR, PBO via CSCV.

Every expected value here is DERIVED, not recorded from a run. Where a closed form exists
the derivation is in the comment above the assertion, so a reader can confirm the number
without executing anything. Tests that merely pin whatever the code printed would pass
just as happily on a wrong implementation, and this is the code that decides whether a
result is believed.

The three properties most worth breaking on purpose:
  - the trial log must detect that a line was edited or removed
  - the DSR must fall as N rises, and must not treat excess kurtosis as non-excess
  - PBO must report ~0.5 on noise and exactly 1.0 on a constructed overfit
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from futuresres.stats.dsr import (
    EULER_MASCHERONI,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    moments,
    probabilistic_sharpe_ratio,
    sharpe_ratio,
    sharpe_standard_error,
)
from futuresres.stats.pbo import (
    REJECT_ABOVE,
    _ranks_worst_to_best,
    column_sharpe,
    pbo_cscv,
)
from futuresres.stats.trials import STATUSES, Trial, TrialLog, record_hash

pytestmark = pytest.mark.integrity


def make_trial(tid: str = "t00001", **kw) -> Trial:
    base = dict(
        trial_id=tid, hypothesis_id="S03", params={"lookback": 50},
        symbol="BTCUSDT", date_range=("2020-01-01", "2026-08-23"),
        status="completed", timestamp="2026-08-24T18:02:11Z", sharpe=0.4,
    )
    return Trial(**{**base, **kw})


# ══════════════════════════════════════════════════════════════════════════════
# Trial log
# ══════════════════════════════════════════════════════════════════════════════


def test_append_and_read_round_trip(tmp_path):
    log = TrialLog(tmp_path / "trials.jsonl")
    log.append(make_trial("t00001"))
    log.append(make_trial("t00002", status="abandoned", sharpe=None))

    got = log.read_all()
    assert [t.trial_id for t in got] == ["t00001", "t00002"]
    assert got[0].sharpe == 0.4
    assert got[1].sharpe is None
    assert got[0].date_range == ("2020-01-01", "2026-08-23")


def test_file_is_one_json_object_per_line(tmp_path):
    path = tmp_path / "trials.jsonl"
    log = TrialLog(path)
    log.append(make_trial("t00001"))
    log.append(make_trial("t00002"))

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        assert isinstance(json.loads(line), dict)  # each line stands alone


def test_appending_does_not_rewrite_existing_lines(tmp_path):
    """The append-only claim, checked at the byte level.

    A parquet-style rewrite would reproduce the same logical content while touching bytes
    that were already on disk. This asserts the earlier line is left literally untouched.
    """
    path = tmp_path / "trials.jsonl"
    log = TrialLog(path)
    log.append(make_trial("t00001"))
    first_line_before = path.read_bytes().split(b"\n")[0]

    log.append(make_trial("t00002"))
    log.append(make_trial("t00003"))

    assert path.read_bytes().split(b"\n")[0] == first_line_before


def test_duplicate_trial_id_is_refused(tmp_path):
    """Two trials sharing an id makes N ambiguous."""
    log = TrialLog(tmp_path / "trials.jsonl")
    log.append(make_trial("t00001"))
    with pytest.raises(ValueError, match="already in the log"):
        log.append(make_trial("t00001"))


def test_next_id_is_sequential(tmp_path):
    log = TrialLog(tmp_path / "trials.jsonl")
    assert log.next_id() == "t00001"
    log.append(make_trial(log.next_id()))
    assert log.next_id() == "t00002"


def test_unknown_status_is_refused():
    with pytest.raises(ValueError, match="not one of"):
        make_trial(status="abandonded")  # a typo must not create a new category
    assert "abandoned" in STATUSES


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_metric_is_refused(bad):
    """NaN and inf are not JSON; writing them would produce a file we cannot read back."""
    with pytest.raises(ValueError, match="not finite"):
        make_trial(profit_factor=bad)


def test_n_for_deflation_counts_superseded_trials(tmp_path):
    """A trial found to be a bug still consumed a look at the data.

    If this ever drops superseded records, every §6 correction silently gets more
    optimistic — which is the failure this whole module exists to prevent.
    """
    log = TrialLog(tmp_path / "trials.jsonl")
    log.append(make_trial("t00001"))
    log.supersede("t00001", make_trial("t00002", supersedes="t00001"), "wrong date range")

    assert len(log.read_all()) == 2
    assert log.n_for_deflation() == 2  # not 1


def test_supersede_requires_the_replacement_to_name_what_it_replaces(tmp_path):
    log = TrialLog(tmp_path / "trials.jsonl")
    log.append(make_trial("t00001"))
    with pytest.raises(ValueError, match="supersedes"):
        log.supersede("t00001", make_trial("t00002"), "reason")


def test_supersede_refuses_an_unknown_id(tmp_path):
    log = TrialLog(tmp_path / "trials.jsonl")
    with pytest.raises(ValueError, match="not in the log"):
        log.supersede("nope", make_trial("t00002", supersedes="nope"), "reason")


# ── hash chain: the part that must actually catch tampering ──────────────────


def test_chain_verifies_on_an_untouched_log(tmp_path):
    log = TrialLog(tmp_path / "trials.jsonl")
    for i in range(1, 6):
        log.append(make_trial(f"t{i:05d}"))
    result = log.verify_chain()
    assert result.ok and result.n_records == 5


def test_first_record_chains_to_genesis(tmp_path):
    log = TrialLog(tmp_path / "trials.jsonl")
    rec = log.append(make_trial("t00001"))
    assert rec["prev_hash"] == ""  # nothing precedes it


def test_each_record_carries_the_hash_of_the_one_before(tmp_path):
    log = TrialLog(tmp_path / "trials.jsonl")
    first = log.append(make_trial("t00001"))
    second = log.append(make_trial("t00002"))
    assert second["prev_hash"] == record_hash(first)


def test_editing_a_line_breaks_the_chain(tmp_path):
    """Fault injection: change a metric on record 1 of 4 and keep the file valid JSON."""
    path = tmp_path / "trials.jsonl"
    log = TrialLog(path)
    for i in range(1, 5):
        log.append(make_trial(f"t{i:05d}"))
    assert log.verify_chain().ok

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    tampered = json.loads(lines[1])
    tampered["sharpe"] = 9.99  # the edit someone would actually want to make
    lines[1] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = log.verify_chain()
    assert not result.ok
    assert result.broken_at == 2  # the record AFTER the edited one fails to match


def test_deleting_a_line_breaks_the_chain(tmp_path):
    """Removing an unflattering trial is exactly what lowers N."""
    path = tmp_path / "trials.jsonl"
    log = TrialLog(path)
    for i in range(1, 5):
        log.append(make_trial(f"t{i:05d}"))

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    del lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = log.verify_chain()
    assert not result.ok
    assert result.broken_at == 1


def test_reordering_lines_breaks_the_chain(tmp_path):
    path = tmp_path / "trials.jsonl"
    log = TrialLog(path)
    for i in range(1, 5):
        log.append(make_trial(f"t{i:05d}"))

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    lines[1], lines[2] = lines[2], lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert not log.verify_chain().ok


# ══════════════════════════════════════════════════════════════════════════════
# Deflated Sharpe Ratio
# ══════════════════════════════════════════════════════════════════════════════


def test_sharpe_ratio_of_a_hand_computable_series():
    # [0.02, 0.01, 0.02, 0.01]: mean 0.015, deviations ±0.005,
    # var(ddof=1) = 4(0.005²)/3 = 3.3333e-5, sd = 0.00577350269
    # SR = 0.015 / 0.00577350269 = 2.598076211
    assert sharpe_ratio([0.02, 0.01, 0.02, 0.01]) == pytest.approx(2.598076211, abs=1e-9)


def test_moments_uses_non_excess_kurtosis():
    # [1,-1,1,-1]: mean 0, m2 = 1, m3 = 0, m4 = 1
    # skew = 0/1^1.5 = 0 ; kurtosis = 1/1² = 1  (NON-excess; excess would be -2)
    skew, kurt = moments([1.0, -1.0, 1.0, -1.0])
    assert skew == pytest.approx(0.0, abs=1e-12)
    assert kurt == pytest.approx(1.0, abs=1e-12)


def test_moments_of_normal_data_give_kurtosis_near_three_not_zero():
    """The convention check. Excess kurtosis of a normal sample is ~0; non-excess is ~3."""
    rng = np.random.default_rng(20260824)
    skew, kurt = moments(rng.standard_normal(200_000))
    assert abs(skew) < 0.05
    assert kurt == pytest.approx(3.0, abs=0.1)


# ── expected maximum Sharpe ──────────────────────────────────────────────────


def test_expected_max_sharpe_is_zero_for_a_single_trial():
    """One trial is no selection, so there is no bar to clear.

    Also guards the arithmetic: Φ⁻¹(1 − 1/1) = Φ⁻¹(0) = −∞ would poison the formula.
    """
    assert expected_max_sharpe(1, 4.0) == 0.0


def test_expected_max_sharpe_is_zero_when_trials_do_not_disperse():
    assert expected_max_sharpe(100, 0.0) == 0.0


def test_expected_max_sharpe_two_trials_closed_form():
    # SR* = √V·[(1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(Ne))]
    # N=2, V=1:  Φ⁻¹(1 − 1/2) = Φ⁻¹(0.5) = 0 exactly, so the first term vanishes.
    #            1/(2e) = 0.1839397206 → Φ⁻¹(0.8160602794) = 0.9004525966
    #            SR* = γ · 0.9004525966 = 0.5772156649 × 0.9004525966 = 0.5197553443
    assert expected_max_sharpe(2, 1.0) == pytest.approx(0.5197553443, abs=1e-9)


def test_expected_max_sharpe_ten_trials_closed_form():
    # N=10, V=1: Φ⁻¹(0.9) = 1.2815515655, Φ⁻¹(1 − 1/(10e)) = Φ⁻¹(0.9632120559)
    #            = 1.7892417646
    # SR* = (1−0.5772156649)(1.2815515655) + 0.5772156649(1.7892417646) = 1.5745983013
    assert expected_max_sharpe(10, 1.0) == pytest.approx(1.5745983013, abs=1e-9)


def test_expected_max_sharpe_scales_with_the_square_root_of_variance():
    """SR* = √V · (…), so quadrupling V must exactly double the bar."""
    assert expected_max_sharpe(50, 4.0) == pytest.approx(
        2.0 * expected_max_sharpe(50, 1.0), rel=1e-12
    )


def test_expected_max_sharpe_rises_with_the_number_of_trials():
    """More trials, higher best-by-luck. This monotonicity is the whole point."""
    bars = [expected_max_sharpe(n, 1.0) for n in (2, 5, 10, 100, 1000, 10_000)]
    assert all(b < c for b, c in zip(bars, bars[1:]))


def test_euler_mascheroni_constant_is_right():
    assert EULER_MASCHERONI == pytest.approx(0.57721566490153286, abs=1e-15)


# ── standard error ───────────────────────────────────────────────────────────


def test_standard_error_normal_case_is_exact():
    # SE = √((1 − γ₃·SR + (γ₄−1)/4·SR²)/(T−1))
    # SR=0, T=101, skew=0, kurt=3 → √((1 − 0 + 0)/100) = √0.01 = 0.1 exactly
    assert sharpe_standard_error(0.0, 101, 0.0, 3.0) == pytest.approx(0.1, abs=1e-15)


def test_standard_error_with_sharpe_root_two_is_exact():
    # SR=√2, kurt=3: inner = 1 − 0 + (3−1)/4 · 2 = 1 + 1 = 2
    # SE = √(2/100) = 0.1414213562
    assert sharpe_standard_error(math.sqrt(2), 101, 0.0, 3.0) == pytest.approx(
        0.1414213562, abs=1e-9
    )


def test_negative_skew_widens_the_standard_error():
    """−γ₃·SR is positive when skew is negative, so a left tail is penalised.

    This is the correct direction: a strategy that wins often and loses hugely should be
    harder to believe, not easier.
    """
    wide = sharpe_standard_error(0.5, 1001, -2.0, 3.0)
    plain = sharpe_standard_error(0.5, 1001, 0.0, 3.0)
    assert wide > plain


def test_fat_tails_widen_the_standard_error():
    assert sharpe_standard_error(0.5, 1001, 0.0, 9.0) > sharpe_standard_error(
        0.5, 1001, 0.0, 3.0
    )


def test_standard_error_refuses_a_non_positive_variance_term():
    # inner = 1 − γ₃·SR + (γ₄−1)/4·SR² can go negative for extreme skew
    with pytest.raises(ValueError, match="non-positive"):
        sharpe_standard_error(1.0, 101, 5.0, 1.0)


# ── PSR / DSR ────────────────────────────────────────────────────────────────


def test_psr_is_exactly_one_half_when_sharpe_equals_the_benchmark():
    """Φ(0) = 0.5. No preference either way — the cleanest fixed point in the formula."""
    assert probabilistic_sharpe_ratio(0.4, 500, -0.3, 5.0, benchmark=0.4) == pytest.approx(
        0.5, abs=1e-12
    )


def test_psr_closed_form_case():
    # SR=0.1, T=1001, skew=0, kurt=3, benchmark=0
    #   inner = 1 + (3−1)/4 · 0.01 = 1.005
    #   SE    = √(1.005/1000) = 0.0317017350
    #   z     = 0.1 / 0.0317017350 = 3.1544014894
    #   PSR   = Φ(3.1544014894) = 0.9991958617
    assert probabilistic_sharpe_ratio(0.1, 1001, 0.0, 3.0) == pytest.approx(
        0.9991958617, abs=1e-9
    )


def test_passing_excess_kurtosis_by_mistake_inflates_the_result():
    """The trap `moments()` exists to prevent, pinned so a refactor cannot reintroduce it.

    Excess kurtosis of a normal sample is 0 where non-excess is 3. The smaller value
    shrinks the denominator, so the mistake always flatters the strategy.

    Checked at the standard-error level, where both sides are exact:
      SR=0.2, T=101, skew=0
        correct  (γ₄=3): inner = 1 + (3−1)/4 · 0.04 = 1.02 → SE = √0.0102 = 0.1009950494
        mistaken (γ₄=0): inner = 1 + (0−1)/4 · 0.04 = 0.99 → SE = √0.0099 = 0.0994987437
    The PSR comparison is made at these same values rather than at a larger SR, where both
    probabilities round to exactly 1.0 in double precision and the test cannot discriminate.
    """
    se_correct = sharpe_standard_error(0.2, 101, 0.0, 3.0)
    se_mistaken = sharpe_standard_error(0.2, 101, 0.0, 0.0)
    assert se_correct == pytest.approx(0.1009950494, abs=1e-9)
    assert se_mistaken == pytest.approx(0.0994987437, abs=1e-9)
    assert se_mistaken < se_correct

    correct = probabilistic_sharpe_ratio(0.2, 101, 0.0, 3.0)
    mistaken = probabilistic_sharpe_ratio(0.2, 101, 0.0, 0.0)
    assert mistaken > correct


def test_dsr_falls_as_the_trial_count_rises():
    """Same returns, more trials searched: the result must become less believable."""
    rng = np.random.default_rng(7)
    returns = rng.normal(0.001, 0.01, 2000)
    sharpes = rng.normal(0.0, 0.05, 500)

    few = deflated_sharpe_ratio(returns, sharpes[:10], n_trials=10)
    many = deflated_sharpe_ratio(returns, sharpes, n_trials=500)
    assert many.dsr < few.dsr
    assert many.expected_max_sharpe > few.expected_max_sharpe


def test_dsr_never_exceeds_the_undeflated_psr():
    """SR* ≥ 0 always, so deflation can only cost. If this inverts, a sign flipped."""
    rng = np.random.default_rng(11)
    result = deflated_sharpe_ratio(
        rng.normal(0.0008, 0.012, 3000), rng.normal(0.0, 0.08, 250)
    )
    assert result.dsr <= result.psr_vs_zero


def test_dsr_reports_every_intermediate():
    rng = np.random.default_rng(3)
    r = deflated_sharpe_ratio(rng.normal(0.001, 0.01, 1000), rng.normal(0, 0.05, 40))
    assert r.n_obs == 1000 and r.n_trials == 40
    # z is the assembled quantity; check it against its own parts
    assert r.z_score == pytest.approx(
        (r.sharpe - r.expected_max_sharpe) / r.standard_error, rel=1e-12
    )


@pytest.mark.slow
def test_expected_max_sharpe_matches_a_simulated_null():
    """The closed form is checked elsewhere against itself; this checks it against reality.

    N strategies of T iid zero-mean returns, true Sharpe 0 by construction. The formula
    must predict the average maximum Sharpe actually observed. A transcription error would
    pass the closed-form tests and fail here.

    N=2 is deliberately excluded: the Gaussian-maximum approximation is weakest at very
    small N (simulation ≈0.019 vs formula ≈0.013), which is a known property of the
    approximation rather than an implementation fault.
    """
    rng = np.random.default_rng(20260824)
    t_obs, reps = 1000, 120
    for n in (10, 50, 200):
        sim, pred = [], []
        for _ in range(reps):
            panel = rng.standard_normal((t_obs, n))
            sharpes = panel.mean(axis=0) / panel.std(axis=0, ddof=1)
            sim.append(sharpes.max())
            pred.append(expected_max_sharpe(n, float(sharpes.var(ddof=1))))
        assert float(np.mean(sim)) == pytest.approx(float(np.mean(pred)), abs=0.01)


@pytest.mark.slow
def test_dsr_does_not_bless_the_best_of_many_noise_strategies():
    """§7.2 applied to this component: the pipeline must report nothing on noise.

    The undeflated PSR is asserted alongside precisely because it fails this — it calls
    the best of 100 coin flips significant essentially every time. That contrast is the
    entire justification for DSR being the reported metric, so it is pinned here rather
    than left as a claim in a docstring.
    """
    rng = np.random.default_rng(4242)
    t_obs, n, reps = 1000, 100, 100
    deflated_pass = undeflated_pass = 0
    for _ in range(reps):
        panel = rng.standard_normal((t_obs, n)) * 0.01
        sharpes = panel.mean(axis=0) / panel.std(axis=0, ddof=1)
        best = int(np.argmax(sharpes))
        result = deflated_sharpe_ratio(panel[:, best], sharpes)
        deflated_pass += result.passes
        undeflated_pass += result.psr_vs_zero > 0.95

    assert deflated_pass <= 0.05 * reps   # near zero: the correction works
    assert undeflated_pass >= 0.90 * reps  # near all: the bias it removes is real


def test_dsr_refuses_an_empty_trial_record():
    with pytest.raises(ValueError, match="silent trials"):
        deflated_sharpe_ratio([0.01, -0.01, 0.02, 0.0], [])


def test_dsr_refuses_n_smaller_than_the_recorded_trials():
    """N may exceed the recorded sample; it may never be quietly reduced below it."""
    with pytest.raises(ValueError, match="never smaller"):
        deflated_sharpe_ratio([0.01, -0.01, 0.02, 0.0], [0.1, 0.2, 0.3], n_trials=2)


# ══════════════════════════════════════════════════════════════════════════════
# PBO via CSCV
# ══════════════════════════════════════════════════════════════════════════════

GOOD = [0.02, 0.01, 0.02, 0.01]     # sharpe +2.598
BAD = [-0.02, -0.01, -0.02, -0.01]  # sharpe −2.598


def test_ranks_are_worst_to_best_with_ties_averaged():
    assert list(_ranks_worst_to_best(np.array([10.0, 20.0, 30.0]))) == [1.0, 2.0, 3.0]
    # ties share the average of the ranks they span: (1+2)/2 = 1.5
    assert list(_ranks_worst_to_best(np.array([5.0, 5.0, 9.0]))) == [1.5, 1.5, 3.0]


def test_column_sharpe_scores_a_flat_column_as_minus_infinity():
    """A column that never moved must not be able to win a block."""
    block = np.array([[0.01, 0.0], [0.02, 0.0], [0.01, 0.0], [0.02, 0.0]])
    assert column_sharpe(block)[1] == -np.inf


def test_pbo_is_exactly_one_for_a_constructed_overfit():
    """Two configs, each the winner in one block and the loser in the other.

    S=2 gives C(2,1) = 2 splits.
      split {block0} IS: A wins IS (+2.598 vs −2.598); OOS on block1 A is worst
                         → rank 1 of 2 → ω = 1/(2+1) = 1/3 → λ = ln((1/3)/(2/3)) = −ln2
      split {block1} IS: symmetric, B wins IS and is worst OOS → λ = −ln2
    Both λ ≤ 0, so PBO = 2/2 = 1.0 — selection is anti-predictive, exactly as built.
    """
    a = GOOD + BAD
    b = BAD + GOOD
    result = pbo_cscv(np.array([a, b]).T, n_splits=2)

    assert result.n_combinations == 2
    assert result.pbo == 1.0
    assert list(result.relative_ranks) == pytest.approx([1 / 3, 1 / 3])
    assert list(result.lambdas) == pytest.approx([-math.log(2), -math.log(2)])
    assert result.rejects  # 1.0 > 0.5


def test_pbo_is_exactly_zero_when_one_config_dominates_everywhere():
    """A wins in both blocks, so the in-sample pick is also the out-of-sample best.

    rank 2 of 2 → ω = 2/3 → λ = ln((2/3)/(1/3)) = +ln2 > 0, on both splits → PBO = 0.
    """
    result = pbo_cscv(np.array([GOOD + GOOD, BAD + BAD]).T, n_splits=2)

    assert result.pbo == 0.0
    assert list(result.lambdas) == pytest.approx([math.log(2), math.log(2)])
    assert not result.rejects
    assert list(result.is_best_indices) == [0, 0]  # config A won in-sample both times


def test_combination_count_is_s_choose_s_over_two():
    """C(4,2) = 6. The count must be the symmetric one, not an arbitrary train/test cut."""
    rng = np.random.default_rng(1)
    result = pbo_cscv(rng.normal(0, 0.01, (80, 3)), n_splits=4)
    assert result.n_combinations == math.comb(4, 2) == 6


def test_remainder_rows_are_dropped_not_spread_unevenly():
    """9 rows over 2 splits: blocks of 4, one row dropped, so both halves match."""
    rng = np.random.default_rng(2)
    result = pbo_cscv(rng.normal(0, 0.01, (9, 2)), n_splits=2)
    assert result.n_obs_used == 8
    assert result.n_obs_dropped == 1


def test_pbo_is_near_one_half_on_pure_noise():
    """Calibration. With no edge, the in-sample winner is a coin flip out-of-sample.

    A procedure that reported a low PBO here would bless noise, which is the §7.2 failure
    mode applied to this specific component.
    """
    rng = np.random.default_rng(20260824)
    result = pbo_cscv(rng.normal(0, 0.01, (1200, 12)), n_splits=8)
    assert 0.35 < result.pbo < 0.65
    assert abs(result.median_logit) < 0.6


def test_reject_threshold_matches_the_spec():
    assert REJECT_ABOVE == 0.5


@pytest.mark.parametrize(
    "kwargs,match",
    [
        (dict(n_splits=3), "even"),
        (dict(n_splits=0), "even"),
    ],
)
def test_odd_or_degenerate_split_counts_are_refused(kwargs, match):
    rng = np.random.default_rng(4)
    with pytest.raises(ValueError, match=match):
        pbo_cscv(rng.normal(0, 0.01, (100, 3)), **kwargs)


def test_a_single_configuration_is_refused():
    """With one candidate there is no selection, so there is nothing to measure."""
    rng = np.random.default_rng(5)
    with pytest.raises(ValueError, match="no selection"):
        pbo_cscv(rng.normal(0, 0.01, (100, 1)), n_splits=4)


def test_too_few_rows_for_the_requested_splits_is_refused():
    rng = np.random.default_rng(6)
    with pytest.raises(ValueError, match="under 2 rows per block"):
        pbo_cscv(rng.normal(0, 0.01, (10, 3)), n_splits=8)


def test_a_metric_returning_the_wrong_shape_is_refused():
    rng = np.random.default_rng(8)
    with pytest.raises(ValueError, match="one value per configuration"):
        pbo_cscv(rng.normal(0, 0.01, (100, 3)), n_splits=2,
                 metric=lambda block: np.array([1.0, 2.0]))
