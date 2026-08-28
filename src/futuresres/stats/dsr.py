"""Probabilistic and Deflated Sharpe Ratio — CLAUDE.md §6, build order step 5.

Bailey & López de Prado, *The Deflated Sharpe Ratio: Correcting for Selection Bias,
Backtest Overfitting and Non-Normality* (Journal of Portfolio Management, 2014).

The question DSR answers: given that we ran N trials and kept the best, how likely is it
that this strategy's true Sharpe is above zero? It corrects for three things at once —
the number of trials, the dispersion among them, and the non-normality of the returns.

    PSR(SR*) = Φ( (SR − SR*)·√(T−1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²) )

    DSR      = PSR(SR*) where SR* = E[max Sharpe across N trials under the null]

    SR*      = √V · [ (1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)) ]

with V the cross-sectional variance of the N trial Sharpes and γ the Euler-Mascheroni
constant. This is §5 Stage 1's rule applied to our own headline metric: γ₃ and γ₄ enter
precisely because the returns are not normal, and on the tails measured in
`reports/data_quality.md` that correction is not a rounding detail.

TWO UNITS TRAPS, BOTH OF WHICH SILENTLY INFLATE THE ANSWER

1. **SR here is PER-OBSERVATION, never annualized.** Feeding an annualized Sharpe with a
   per-observation T overstates the numerator by √periods_per_year and turns a mediocre
   strategy into a certainty. Nothing in the formula can detect the mistake, so
   `deflated_sharpe_ratio` takes returns rather than a bare number wherever it can, and
   `annualize=` exists only for reporting.

2. **γ₄ is NON-EXCESS kurtosis: 3 for a normal distribution, not 0.** `scipy.stats.kurtosis`
   returns excess by default. Passing excess kurtosis makes the denominator too small and
   the DSR too high. `moments()` returns the right convention; use it.

ACCURACY OF SR*. Checked against simulation of the null it describes (see
`test_expected_max_sharpe_matches_a_simulated_null`): for N ≥ 5 the formula tracks the
observed mean maximum Sharpe to within ~0.001. At N = 2 the Gaussian-maximum approximation
runs low — simulation ≈0.019 against a predicted ≈0.013 — so a DSR computed from a
two-trial search is mildly optimistic. It is a property of the approximation, not a bug,
and it does not matter at any N worth deflating for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Sequence

import numpy as np
from scipy.stats import norm

#: Euler-Mascheroni constant, the γ in the expected-maximum formula.
EULER_MASCHERONI: Final[float] = 0.5772156649015328606


@dataclass(frozen=True, slots=True)
class DSRResult:
    """Every intermediate is kept: a DSR that surprises you is usually one of these."""

    dsr: float
    psr_vs_zero: float
    sharpe: float
    expected_max_sharpe: float
    standard_error: float
    z_score: float
    n_trials: int
    n_obs: int
    skew: float
    kurtosis: float
    trial_sharpe_variance: float

    @property
    def passes(self) -> bool:
        """Conventional 95% threshold. DSR is a probability, not a test statistic."""
        return self.dsr > 0.95


def sharpe_ratio(returns: Sequence[float] | np.ndarray, ddof: int = 1) -> float:
    """Per-observation Sharpe. NOT annualized — see the units trap in the module docstring."""
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        raise ValueError(f"need at least 2 returns, got {r.size}")
    sd = r.std(ddof=ddof)
    if sd == 0:
        raise ValueError("zero return variance — Sharpe is undefined")
    return float(r.mean() / sd)


def moments(returns: Sequence[float] | np.ndarray) -> tuple[float, float]:
    """(skew, NON-excess kurtosis). Normal returns give (0, 3), not (0, 0).

    Written out rather than delegated to scipy so the convention is visible at the point
    of use — the excess-vs-non-excess mix-up is the single easiest way to overstate a DSR.
    """
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        raise ValueError(f"need at least 2 returns, got {r.size}")
    centred = r - r.mean()
    m2 = float((centred ** 2).mean())
    if m2 == 0:
        raise ValueError("zero variance — skew and kurtosis are undefined")
    m3 = float((centred ** 3).mean())
    m4 = float((centred ** 4).mean())
    return m3 / m2 ** 1.5, m4 / m2 ** 2


def expected_max_sharpe(n_trials: int, trial_sharpe_variance: float) -> float:
    """E[max SR] over N independent trials whose true Sharpe is zero.

    This is the bar the observed Sharpe has to clear. With N=1 there is no selection, so
    the bar is zero; with V=0 every trial scored identically and picking the best conveys
    nothing, so again zero. Both are returned exactly rather than as a limit, because
    Φ⁻¹(1 − 1/N) is −∞ at N=1 and would poison the arithmetic.
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")
    if trial_sharpe_variance < 0:
        raise ValueError(f"variance must be >= 0, got {trial_sharpe_variance}")
    if n_trials == 1 or trial_sharpe_variance == 0:
        return 0.0
    n = float(n_trials)
    g = EULER_MASCHERONI
    return float(
        math.sqrt(trial_sharpe_variance)
        * ((1.0 - g) * norm.ppf(1.0 - 1.0 / n) + g * norm.ppf(1.0 - 1.0 / (n * math.e)))
    )


def sharpe_standard_error(sharpe: float, n_obs: int, skew: float, kurtosis: float) -> float:
    """Standard error of the Sharpe estimator under non-normal returns (Mertens; Lo 2002).

        SE = √( (1 − γ₃·SR + (γ₄−1)/4·SR²) / (T−1) )

    `kurtosis` is NON-excess (3 for normal), which makes the normal case reduce to the
    familiar √((1 + SR²/2)/(T−1)).
    """
    if n_obs < 2:
        raise ValueError(f"n_obs must be >= 2, got {n_obs}")
    inner = 1.0 - skew * sharpe + ((kurtosis - 1.0) / 4.0) * sharpe ** 2
    if inner <= 0:
        raise ValueError(
            f"variance term {inner:.6g} is non-positive for SR={sharpe:.4g}, "
            f"skew={skew:.4g}, kurtosis={kurtosis:.4g}. The estimator is not defined "
            f"here; report the inputs rather than a probability."
        )
    return math.sqrt(inner / (n_obs - 1))


def probabilistic_sharpe_ratio(
    sharpe: float, n_obs: int, skew: float, kurtosis: float, benchmark: float = 0.0
) -> float:
    """P(true Sharpe > benchmark). DSR is this with benchmark = E[max SR]."""
    se = sharpe_standard_error(sharpe, n_obs, skew, kurtosis)
    return float(norm.cdf((sharpe - benchmark) / se))


def deflated_sharpe_ratio(
    returns: Sequence[float] | np.ndarray,
    trial_sharpes: Sequence[float] | np.ndarray,
    *,
    n_trials: int | None = None,
) -> DSRResult:
    """DSR for `returns`, deflated by the dispersion and count of `trial_sharpes`.

    `trial_sharpes` is every Sharpe produced during the search — from `trials.jsonl`, not
    a hand-picked subset. `n_trials` defaults to len(trial_sharpes) and should be
    overridden only when trials were run whose Sharpe was not recorded, in which case N
    is larger than the sample and the deflation must use the larger number.

    All Sharpes, observed and trial, must be in the same per-observation units.
    """
    r = np.asarray(returns, dtype=float)
    trials = np.asarray(trial_sharpes, dtype=float)
    if trials.size == 0:
        raise ValueError(
            "trial_sharpes is empty. A DSR with no trial record is just a Sharpe with "
            "extra steps — §6: silent trials invalidate the math."
        )

    n = int(n_trials if n_trials is not None else trials.size)
    if n < trials.size:
        raise ValueError(
            f"n_trials={n} is fewer than the {trials.size} trial Sharpes supplied. N may "
            f"be larger than the recorded sample, never smaller."
        )

    sr = sharpe_ratio(r)
    skew, kurt = moments(r)
    variance = float(trials.var(ddof=1)) if trials.size > 1 else 0.0
    sr_star = expected_max_sharpe(n, variance)
    se = sharpe_standard_error(sr, r.size, skew, kurt)
    z = (sr - sr_star) / se

    return DSRResult(
        dsr=float(norm.cdf(z)),
        psr_vs_zero=float(norm.cdf(sr / se)),
        sharpe=sr,
        expected_max_sharpe=sr_star,
        standard_error=se,
        z_score=float(z),
        n_trials=n,
        n_obs=int(r.size),
        skew=skew,
        kurtosis=kurt,
        trial_sharpe_variance=variance,
    )
