"""Stage 1 signal-level separation — CLAUDE.md §5 Stage 1.

DELIBERATELY MINIMAL, AND EARLY. The full Stage 1–2 harness is build order step 8. This
exists now because §7's integrity tests have to be integrity-testing *something*, and §7
comes before the backtest engine at step 9. When that engine is built, §7.2 must be re-run
against it — a pipeline that has only ever been noise-tested at Stage 1 has been tested at
Stage 1, not end to end.

Everything here follows the §5 Stage 1 rule added after the data validation: the return
distribution is heavy-tailed (kurtosis ≈200 on BTCUSDT 1m), so inference is
**non-parametric**. Confidence intervals come from a circular block bootstrap and p-values
from a rotation permutation test. There is no t-statistic in this file, by design.

WHY CIRCULAR BLOCKS RATHER THAN IID RESAMPLING. Returns cluster: the squared-return
autocorrelation on real BTCUSDT 1m is 0.36 at one minute and still 0.06 at an hour.
Resampling individual observations would destroy that, shrink the null, and manufacture
significance. Blocks preserve local dependence; rotation preserves it in both series at
once while destroying only their alignment, which is exactly the null we want.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy.stats import norm

#: §6 calibration: "trade count > 200 … < 100 = no information."
MIN_SIGNALS: Final[int] = 100

#: Block length for the circular block bootstrap, in bars. Long enough to carry the
#: volatility clustering measured on real data, short enough to leave many distinct blocks.
DEFAULT_BLOCK: Final[int] = 240

DEFAULT_BOOTSTRAP: Final[int] = 2000
DEFAULT_PERMUTATIONS: Final[int] = 1000
DEFAULT_ALPHA: Final[float] = 0.05


@dataclass(frozen=True, slots=True)
class Stage1Result:
    horizon: int
    n_obs: int
    n_signals: int
    mean_conditional: float
    mean_unconditional: float
    mean_shift: float
    median_shift: float
    hit_rate: float
    ci_low: float
    ci_high: float
    p_value: float
    separated: bool
    reason: str = ""


def forward_returns(returns: np.ndarray, horizon: int) -> np.ndarray:
    """Cumulative return over the next `horizon` bars. NaN where the window runs off the end.

    Bar t's forward return covers t+1 … t+horizon and never includes bar t itself; a
    forward window that starts at t is the most common way to leak one bar of the future.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    r = np.asarray(returns, dtype=float)
    csum = np.concatenate([[0.0], np.nancumsum(r)])
    out = np.full(r.size, np.nan)
    end = r.size - horizon
    if end > 0:
        # sum of r[t+1 .. t+horizon]
        idx = np.arange(end)
        out[:end] = csum[idx + 1 + horizon] - csum[idx + 1]
    return out


#: Nominal α that makes the percentile interval actually cover 95%, measured by
#: resampling real BTCUSDT returns (8,000 replications per cell, both h=45 and h=60, the
#: more conservative of the two taken at each N). The percentile interval under-covers on
#: heavy tails, so hitting a true 95% requires a TIGHTER nominal α than 0.05.
#:
#:     N      coverage at α=0.05     α* for true 95%
#:     50           92.8–93.1%            0.0312
#:     100          93.4%                 0.0359
#:     250          94.0–94.1%            0.0400
#:     500          94.7–94.8%            0.0500 (treated as converged)
#:
#: Above ~500 the shortfall is inside one Monte Carlo standard error, so 0.05 is used
#: directly rather than chasing noise.
#: ==========================================================================================
#: CARRIED OVER FROM CRYPTO AND NOT YET VALID HERE. CLAUDE_FUTURES.md §4, build step 8.
#:
#: These nominal alphas were fitted by resampling REAL BTCUSDT 1m RETURNS so that a
#: percentile interval actually covers 95% on that tail. BTC's measured kurtosis is 199.9
#: at 1m; index futures run an order of magnitude lower. A thinner tail needs a different
#: nominal alpha, and the direction of the error is NOT known in advance — a calibration
#: fitted to a fatter tail can over- or under-cover on a thinner one depending on where the
#: block count lands.
#:
#: RE-MEASURE ON MNQ AND MGC BEFORE QUOTING ANY STAGE 1 RESULT. Do not reason about which
#: way it moves; the crypto project's central lesson is that assumed statistical properties
#: get falsified by measurement.
#: ==========================================================================================
COVERAGE_CALIBRATION: Final[tuple[tuple[int, float], ...]] = (
    (50, 0.0312),
    (100, 0.0359),
    (250, 0.0400),
    (500, 0.0500),
)

#: Below this the calibration is EXTRAPOLATED, not measured.
CALIBRATION_MIN_N: Final[int] = 50
#: At and above this, nominal 0.05 is already correct.
CALIBRATION_PLATEAU_N: Final[int] = 500


def calibrated_alpha(n_effective: int) -> float:
    """Nominal α giving true 95% coverage at `n_effective` independent observations.

    Log-linear interpolation between the measured anchors, flat at 0.05 from 500 up.
    `n_effective` is the number of INDEPENDENT units the bootstrap resamples — event
    count for an event hypothesis, block count for the block bootstrap over bars. Passing
    a bar count where blocks are meant would overstate the sample by the block length and
    hand back an α that is too loose.

    Defined for a 95% target only, because that is what was measured. A different target
    needs its own calibration run; there is no principled way to rescale this one.

    BELOW 50 THE VALUE IS CLAMPED, NOT MEASURED. Coverage keeps degrading as N falls, so
    the clamp is optimistic there — an interval built on fewer than 50 observations is
    looser than it claims by an unmeasured amount.
    """
    if n_effective >= CALIBRATION_PLATEAU_N:
        return COVERAGE_CALIBRATION[-1][1]
    if n_effective <= CALIBRATION_MIN_N:
        return COVERAGE_CALIBRATION[0][1]

    ln = math.log(n_effective)
    for (n0, a0), (n1, a1) in zip(COVERAGE_CALIBRATION, COVERAGE_CALIBRATION[1:]):
        if n0 <= n_effective <= n1:
            w = (ln - math.log(n0)) / (math.log(n1) - math.log(n0))
            return a0 + w * (a1 - a0)
    return COVERAGE_CALIBRATION[-1][1]


def bca_interval(
    observed: float,
    boot: np.ndarray,
    jackknife: np.ndarray,
    alpha: float = DEFAULT_ALPHA,
) -> tuple[float, float]:
    """Bias-corrected and accelerated bootstrap interval (Efron 1987).

    NOT USED BY `evaluate_signal`, DELIBERATELY. Kept because it is correct, validated,
    and the measurement that rejected it is worth preserving.

    BCa exists to fix exactly the faults these returns have — skew −0.89, and a bootstrap
    distribution that is neither centred nor symmetric. It corrects them with `z₀` (how
    far the bootstrap median sits from the estimate) and `a` (acceleration, from a
    jackknife; for a mean it is skew/(6√n)). On paper it is second-order accurate where
    the percentile method is first-order.

    MEASURED ON REAL BTCUSDT HOURLY RETURNS IT IS WORSE, and so is the studentised
    interval. Coverage against a nominal 95%, 4,000 replications:

        N        percentile      BCa      studentised
        50          92.7%       89.6%        91.6%
        100         93.7%       91.3%        92.6%
        250         94.2%       92.8%        93.3%

    The implementation is not at fault: on exponential(1) — skew 2, kurtosis 9 — BCa beats
    percentile as the theory says, and it degrades monotonically as kurtosis rises through
    t(10), t(5), t(3). The mechanism is that both refinements have to estimate an extra
    moment from the sample — a third moment for the acceleration, a per-resample variance
    for the studentised pivot — and at kurtosis 67 those estimates are dominated by a
    handful of observations. Their asymptotic advantage assumes well-estimated moments,
    which is precisely what a heavy tail denies. The percentile method estimates nothing
    beyond the mean, so it has less to get wrong.

    The general lesson is worth more than the specific choice: a higher-order refinement
    is only an improvement where its own inputs are estimable, and on this data that has
    to be checked rather than assumed.
    """
    b = np.asarray(boot, dtype=float)
    b = b[np.isfinite(b)]
    if b.size < 2:
        return (np.nan, np.nan)

    # ── z₀: bias correction. Clipped off 0 and 1, where Φ⁻¹ is infinite; that happens
    # when every bootstrap draw falls on one side of the estimate, which is real
    # information but not representable as a finite correction.
    prop = float(np.mean(b < observed))
    prop = min(max(prop, 0.5 / b.size), 1.0 - 0.5 / b.size)
    z0 = float(norm.ppf(prop))

    # ── a: acceleration from the jackknife.
    jk = np.asarray(jackknife, dtype=float)
    jk = jk[np.isfinite(jk)]
    a = 0.0
    if jk.size >= 3:
        dev = jk.mean() - jk
        denom = 6.0 * float(np.sum(dev ** 2)) ** 1.5
        if denom > 0:
            a = float(np.sum(dev ** 3) / denom)

    z = norm.ppf([alpha / 2.0, 1.0 - alpha / 2.0])
    shifted = z0 + z
    scale = 1.0 - a * shifted
    # A non-positive scale means the correction has run away — fall back to the
    # uncorrected percentile rather than returning a nonsense endpoint.
    if np.any(scale <= 0):
        return tuple(np.percentile(b, [100 * alpha / 2, 100 * (1 - alpha / 2)]))
    adjusted = norm.cdf(z0 + shifted / scale)
    adjusted = np.clip(adjusted, 1.0 / b.size, 1.0 - 1.0 / b.size)
    lo, hi = np.percentile(b, 100.0 * adjusted)
    return (float(lo), float(hi))


def _block_jackknife_shifts(
    sig: np.ndarray, fwd: np.ndarray, block: int
) -> np.ndarray:
    """Delete-one-BLOCK jackknife of the mean shift.

    Deleting single observations would understate the acceleration on serially dependent
    data, for the same reason an iid bootstrap understates the variance: neighbouring bars
    are not separate pieces of evidence. Blocks match the resampling unit.
    """
    n = fwd.size
    length = min(block, n)
    n_blocks = max(int(np.ceil(n / length)), 2)
    out = np.empty(n_blocks)
    for i in range(n_blocks):
        keep = np.ones(n, dtype=bool)
        keep[i * length:(i + 1) * length] = False
        s, f = sig[keep], fwd[keep]
        out[i] = f[s].mean() - f.mean() if s.any() and not s.all() else np.nan
    return out


def rotation_null(signal: np.ndarray, forward: np.ndarray) -> np.ndarray:
    """Mean shift under EVERY circular rotation of the labels, computed exactly.

    The permutation null used here is a circular rotation, and there are only n of them —
    so rather than sampling rotations, all n are evaluated at once. For rotation k the
    conditional sum is

        c[k] = Σ_t forward[t] · signal[(t−k) mod n] = Σ_u signal[u] · forward[(u+k) mod n]

    which is a circular cross-correlation, available for all k in one FFT pair. This is not
    an approximation of the sampled test — it is the exact test the sampling was estimating,
    and it costs O(n log n) instead of O(n · permutations).

    The number of firing bars is identical under every rotation, so each null draw has the
    same signal count as the observed statistic. Rotations near k=0 are near-copies of the
    observed alignment and mildly fatten the null, which makes the resulting p-value
    slightly conservative — the safe direction.
    """
    sig = np.asarray(signal, dtype=bool)
    fwd = np.asarray(forward, dtype=float)
    n = fwd.size
    n_sig = int(sig.sum())
    if n_sig == 0 or n_sig == n:
        raise ValueError("signal is constant — every rotation gives the same set")
    corr = np.fft.irfft(
        np.conj(np.fft.rfft(sig.astype(float))) * np.fft.rfft(fwd), n=n
    )
    return corr / n_sig - fwd.mean()


def _block_bootstrap_shifts(
    sig: np.ndarray,
    fwd: np.ndarray,
    n_bootstrap: int,
    block: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Circular block bootstrap of the mean shift.

    A resample is a sum over whole blocks, and a block's contribution does not depend on
    which resample it lands in — so every block's three sums (conditional total, firing
    count, overall total) are precomputed once for all n possible start positions via
    prefix sums. A resample then costs O(blocks) lookups instead of O(n) gathers, which is
    the difference between this dominating the runtime and being free.

    Resamples are a whole number of blocks, so their length is n rounded UP to a multiple
    of `block` rather than exactly n. That is the standard circular block bootstrap; the
    alternative — truncating the last block — biases against observations that can only
    appear near a block end.
    """
    n = fwd.size
    length = min(block, n)
    n_blocks = int(np.ceil(n / length))

    # Doubled arrays so a block starting near the end wraps without special-casing.
    f2 = np.concatenate([fwd, fwd])
    s2 = np.concatenate([sig, sig]).astype(float)
    p_all = np.concatenate([[0.0], np.cumsum(f2)])
    p_cond = np.concatenate([[0.0], np.cumsum(np.where(s2 > 0, f2, 0.0))])
    p_count = np.concatenate([[0.0], np.cumsum(s2)])

    starts = np.arange(n)
    blk_all = p_all[starts + length] - p_all[starts]
    blk_cond = p_cond[starts + length] - p_cond[starts]
    blk_count = p_count[starts + length] - p_count[starts]

    pick = rng.integers(0, n, size=(n_bootstrap, n_blocks))
    total_all = blk_all[pick].sum(axis=1)
    total_cond = blk_cond[pick].sum(axis=1)
    total_count = blk_count[pick].sum(axis=1)

    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(
            total_count > 0, total_cond / np.maximum(total_count, 1.0), np.nan
        ) - total_all / (n_blocks * length)


def evaluate_signal(
    signal: np.ndarray,
    returns: np.ndarray,
    horizon: int,
    *,
    rng: np.random.Generator,
    n_bootstrap: int = DEFAULT_BOOTSTRAP,
    n_permutations: int = DEFAULT_PERMUTATIONS,
    block: int = DEFAULT_BLOCK,
    alpha: float = DEFAULT_ALPHA,
    min_signals: int = MIN_SIGNALS,
    calibrate: bool = True,
) -> Stage1Result:
    """Conditional vs unconditional forward returns, with non-parametric inference.

    The gate is deliberately conjunctive: enough signals, a bootstrap interval on the mean
    shift that excludes zero, AND a rotation-permutation p-value below alpha. Any one of
    them alone is easy to clear by accident on 3.5M bars.

    **CONSTANT-EXPOSURE SIGNALS ONLY.** This compares the conditional mean of `returns`
    against the unconditional mean of the same series, which is the right comparison only
    when the exposure is the same on both sides — a long-only entry mask on raw returns,
    as `search.py` uses it.

    **For a long/short signal, use `evaluate_signed_signal` instead.** Orienting a return
    series by direction and passing it here makes the unconditional side a long-only
    baseline while the conditional side is a long/short mix; the gap between the two
    exposures is the asset's drift, and it is charged to the signal. That was a live
    defect until 2026-08-27 and it measured 0.180 false positives against a nominal 0.05
    on a drifting null. `tests/test_signal_module_boundary.py` enforces the split
    structurally so it cannot be reintroduced by a module building the series inline.
    """
    sig = np.asarray(signal, dtype=bool)
    fwd = forward_returns(returns, horizon)
    valid = np.isfinite(fwd)
    sig, fwd = sig[valid], fwd[valid]
    n = fwd.size
    n_sig = int(sig.sum())

    if n_sig < min_signals:
        return Stage1Result(
            horizon, n, n_sig, np.nan, float(np.mean(fwd)) if n else np.nan,
            np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, False,
            f"only {n_sig} signals; §6 calls under {min_signals} no information",
        )
    if n_sig == n:
        return Stage1Result(
            horizon, n, n_sig, float(fwd.mean()), float(fwd.mean()), 0.0, 0.0,
            float((fwd > 0).mean()), np.nan, np.nan, np.nan, False,
            "signal fires on every bar — it is not a condition",
        )

    cond = fwd[sig]
    uncond_mean = float(fwd.mean())
    shift = float(cond.mean() - uncond_mean)

    # ── bootstrap CI on the mean shift, preserving serial dependence ──
    # PERCENTILE, and that is a measured choice rather than the lazy default. BCa and the
    # studentised interval were both implemented and both made coverage WORSE on real
    # returns — see the note on `bca_interval`.
    #
    # The nominal α is CALIBRATED against the effective sample size, which for a block
    # bootstrap is the number of blocks rather than the number of bars. At 20,000 bars and
    # a 240-bar block that is 84 units, not 20,000, and using the bar count would ask for
    # an α the data cannot support.
    n_blocks = max(int(np.ceil(n / min(block, n))), 2)
    effective_alpha = calibrated_alpha(n_blocks) if calibrate else alpha
    boot = _block_bootstrap_shifts(sig, fwd, n_bootstrap, block, rng)
    lo, hi = np.nanpercentile(
        boot, [100 * effective_alpha / 2, 100 * (1 - effective_alpha / 2)]
    )

    # ── permutation p-value: every rotation of the labels, exactly ──
    # n_permutations is accepted for API compatibility but no longer samples: the full
    # rotation null is cheaper than a subset of it. k=0 reproduces the observed statistic,
    # so p is never zero and needs no +1 correction.
    null = rotation_null(sig, fwd)
    p = float(np.mean(np.abs(null) >= abs(shift)))

    ci_excludes_zero = bool(lo > 0 or hi < 0)
    separated = ci_excludes_zero and p < alpha
    reason = ""
    if not ci_excludes_zero:
        reason = f"bootstrap CI [{lo:+.3e}, {hi:+.3e}] contains zero"
    elif p >= alpha:
        reason = f"permutation p = {p:.4f} >= {alpha}"

    return Stage1Result(
        horizon=horizon, n_obs=n, n_signals=n_sig,
        mean_conditional=float(cond.mean()), mean_unconditional=uncond_mean,
        mean_shift=shift,
        median_shift=float(np.median(cond) - np.median(fwd)),
        hit_rate=float((cond > 0).mean()),
        ci_low=float(lo), ci_high=float(hi), p_value=p,
        separated=separated, reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════════════
# SIGNED-EXPOSURE STAGE 1
#
# `evaluate_signal` above compares a signal's conditional forward return against the
# UNCONDITIONAL mean of the same return series. That is correct when the series being
# averaged has a single, constant exposure. It is NOT correct for the way `evaluate_cell`
# uses it on a long/short signal.
#
# evaluate_cell builds its return series as `oriented * r1` with off-event bars set to
# +1 (long). So the unconditional mean is the asset's LONG-ONLY drift, while the observed
# statistic is the signal's own long/short mix at event times. The difference between
# those two exposures is the asset's drift, and a market-neutral signal is charged for a
# drift it never earns. Measured on S09/SOL pct20 k1.5 h60: per-event +4.76 bps, statistic
# +2.34 bps, the +2.84 bps gap being SOL's 60-minute drift. On BTC the same cell reads
# +0.05 bps per-event but -1.24 bps as a statistic. The bias runs NEGATIVE for a neutral
# signal in a rising market, which is not the safe direction — it manufactures apparent
# short edges.
#
# THE FIX. Rotate the SIGNED indicator against the raw forward return, so the null is
# "the same sequence of long/short decisions, taken at shifted times":
#
#     stat[k] = (1/n_sig) · Σ_t d[t]·F[(t+k) mod n],   d ∈ {-1,0,+1}
#
# k = 0 is the observed per-event mean by construction, so the point estimate and the null
# are the same quantity at different alignments — which is what makes the null the right
# comparison for it. The null's centre is (Σd/n_sig)·mean(F), i.e. exactly what the
# signal's net exposure earns from drift, so subtracting it removes the drift charge
# rather than assuming it away.
#
# Cost is one FFT pair, the same as `rotation_null`.
# ══════════════════════════════════════════════════════════════════════════════


def signed_forward(log_price: np.ndarray, horizon: int) -> np.ndarray:
    """F[t] = log_price[t+horizon] − log_price[t], truncated where the window runs off.

    Entry is at the CLOSE of bar t and exit at the close of bar t+horizon, so bar t's own
    return is not part of the window being predicted — it is already realised when the
    position is opened. This is the identical quantity `forward_returns` produces from
    one-bar differences; it is written directly here because the signed path never needs
    the per-bar series.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    lp = np.asarray(log_price, dtype=float)
    if lp.size <= horizon:
        return np.empty(0)
    return lp[horizon:] - lp[:-horizon]


def signed_rotation_null(d: np.ndarray, F: np.ndarray) -> np.ndarray:
    """Mean signed return under EVERY circular rotation, computed exactly by FFT.

    Returns the raw per-rotation means, NOT centred — the caller subtracts the centre so
    that the observed statistic and the null are treated identically.
    """
    d = np.asarray(d, dtype=float)
    F = np.asarray(F, dtype=float)
    n_sig = int(np.count_nonzero(d))
    if n_sig == 0:
        raise ValueError("no signed events — every rotation gives the same empty set")
    if n_sig == d.size:
        raise ValueError("signal fires on every bar — it is not a condition")
    corr = np.fft.irfft(np.conj(np.fft.rfft(d)) * np.fft.rfft(F), n=F.size)
    return corr / n_sig


def _block_bootstrap_signed(
    d: np.ndarray,
    F: np.ndarray,
    n_bootstrap: int,
    block: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Circular block bootstrap of the signed shift, via prefix sums over whole blocks.

    Four running totals are needed rather than three: the signed product, the signed
    count, the absolute count, and the return total — because the drift benchmark being
    subtracted depends on the resample's own net exposure, not on the full sample's.
    """
    n = F.size
    length = min(block, n)
    n_blocks = int(np.ceil(n / length))

    d2 = np.concatenate([d, d])
    f2 = np.concatenate([F, F])
    p_df = np.concatenate([[0.0], np.cumsum(d2 * f2)])
    p_d = np.concatenate([[0.0], np.cumsum(d2)])
    p_abs = np.concatenate([[0.0], np.cumsum(np.abs(d2))])
    p_f = np.concatenate([[0.0], np.cumsum(f2)])

    starts = np.arange(n)
    blk_df = p_df[starts + length] - p_df[starts]
    blk_d = p_d[starts + length] - p_d[starts]
    blk_abs = p_abs[starts + length] - p_abs[starts]
    blk_f = p_f[starts + length] - p_f[starts]

    pick = rng.integers(0, n, size=(n_bootstrap, n_blocks))
    t_df = blk_df[pick].sum(axis=1)
    t_d = blk_d[pick].sum(axis=1)
    t_abs = blk_abs[pick].sum(axis=1)
    t_f = blk_f[pick].sum(axis=1)

    with np.errstate(invalid="ignore", divide="ignore"):
        per_event = t_df / np.maximum(t_abs, 1.0)
        net_exposure = t_d / np.maximum(t_abs, 1.0)
        drift = t_f / (n_blocks * length)
        return np.where(t_abs > 0, per_event - net_exposure * drift, np.nan)


def evaluate_signed_signal(
    direction: np.ndarray,
    log_price: np.ndarray,
    horizon: int,
    *,
    rng: np.random.Generator,
    n_bootstrap: int = DEFAULT_BOOTSTRAP,
    block: int = DEFAULT_BLOCK,
    alpha: float = DEFAULT_ALPHA,
    min_signals: int = MIN_SIGNALS,
    calibrate: bool = True,
) -> Stage1Result:
    """Stage 1 for a long/short signal, scored against its OWN exposure.

    `direction` is a full-length array carrying -1, 0 or +1 at every bar. The gate stays
    conjunctive exactly as in `evaluate_signal`: enough events, a bootstrap interval
    excluding zero, AND a rotation p-value below alpha.
    """
    F = signed_forward(log_price, horizon)
    d = np.asarray(direction, dtype=float)[: F.size].copy()
    n = F.size
    n_sig = int(np.count_nonzero(d))

    if n_sig < min_signals:
        return Stage1Result(
            horizon, n, n_sig, np.nan, np.nan, np.nan, np.nan, np.nan,
            np.nan, np.nan, np.nan, False,
            f"only {n_sig} signals; §6 calls under {min_signals} no information",
        )
    if n_sig == n:
        return Stage1Result(
            horizon, n, n_sig, np.nan, np.nan, np.nan, np.nan, np.nan,
            np.nan, np.nan, np.nan, False,
            "signal fires on every bar — it is not a condition",
        )

    events = np.flatnonzero(d)
    per_event = d[events] * F[events]
    net_exposure = float(d.sum() / n_sig)
    drift_benchmark = net_exposure * float(F.mean())
    shift = float(per_event.mean()) - drift_benchmark

    n_blocks = max(int(np.ceil(n / min(block, n))), 2)
    effective_alpha = calibrated_alpha(n_blocks) if calibrate else alpha
    boot = _block_bootstrap_signed(d, F, n_bootstrap, block, rng)
    lo, hi = np.nanpercentile(
        boot, [100 * effective_alpha / 2, 100 * (1 - effective_alpha / 2)]
    )

    null = signed_rotation_null(d, F)
    centre = float(null.mean())
    p = float(np.mean(np.abs(null - centre) >= abs(float(null[0]) - centre)))

    ci_excludes_zero = bool(lo > 0 or hi < 0)
    separated = ci_excludes_zero and p < alpha
    reason = ""
    if not ci_excludes_zero:
        reason = f"bootstrap CI [{lo:+.3e}, {hi:+.3e}] contains zero"
    elif p >= alpha:
        reason = f"permutation p = {p:.4f} >= {alpha}"

    return Stage1Result(
        horizon=horizon, n_obs=n, n_signals=n_sig,
        mean_conditional=float(per_event.mean()),
        mean_unconditional=drift_benchmark,
        mean_shift=shift,
        median_shift=float(np.median(per_event) - net_exposure * float(np.median(F))),
        hit_rate=float((per_event > 0).mean()),
        ci_low=float(lo), ci_high=float(hi), p_value=p,
        separated=separated, reason=reason,
    )
