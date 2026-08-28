"""The four integrity tests — CLAUDE.md §7, build order step 6.

§7: "These are the load-bearing components. Without them the pipeline generates confidence,
not knowledge." They are implemented here as ordinary functions and exercised from
`tests/test_integrity.py` so they run in CI rather than ad hoc.

    7.1  causal_reconstruction_test  re-derive from data through t; require exact equality
    7.2  synthetic_noise_test        run the pipeline on a null; it must find nothing
    7.3  shuffled_label_test         break the alignment; the effect must vanish
    7.4  monte_carlo_drawdown        realized max DD is one draw, not a property

§7.1 WAS REPLACED, NOT TUNED. The original specification — shift the signal forward one
bar and expect the edge to degrade — was calibrated in `reports/pipeline_power.md` and
found to have NEGATIVE discrimination at every horizon: clean persistent signals were
flagged 96–100% of the time while a pure one-bar leak was flagged 0%. Delaying by one bar
removes exactly the bar such a leak read, so the leak collapses and looks clean, while a
legitimately persistent signal barely moves and looks guilty. That statistic measures
persistence, not lookahead. The re-derivation check replaces it and is calibrated the same
way in the same report.

Each returns a result object with a boolean verdict and the numbers behind it. None of them
raises on failure: a failed integrity test is a finding to report and act on, not an
exception to swallow, and the caller needs the magnitudes to know how bad it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Final, Sequence

import numpy as np

from futuresres.signals.stage1 import evaluate_signal

#: §7.1 — how many bars to re-derive. Every bar could be checked at O(n²) cost; sampling
#: is what makes it affordable on a full series. A leak that touches most bars is caught
#: by the first few checks, so this is generous rather than tight.
DEFAULT_RECONSTRUCTION_CHECKS: Final[int] = 200

#: §7.3 — |shuffled effect| must fall to at most this fraction of the observed effect.
SHUFFLE_COLLAPSE_CEILING: Final[float] = 0.25

#: §7.4 — "Report the 95th percentile drawdown, and size against that."
DD_PERCENTILE: Final[float] = 95.0
DEFAULT_MC_ITERATIONS: Final[int] = 10_000


# ══════════════════════════════════════════════════════════════════════════════
# 7.1  Lookahead shift test
# ══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ReconstructionResult:
    n_checked: int
    n_mismatched: int
    first_mismatch: int | None
    leak_detected: bool
    mismatch_indices: tuple[int, ...]
    detail: str


def causal_reconstruction_test(
    signal_fn: Callable[[np.ndarray], np.ndarray],
    returns: np.ndarray,
    *,
    rng: np.random.Generator,
    n_checks: int = DEFAULT_RECONSTRUCTION_CHECKS,
    warmup: int = 0,
    tolerance: float = 0.0,
) -> ReconstructionResult:
    """§7.1: re-derive each signal from data through bar t only, and require exact equality.

    A causal function's value at bar t depends on nothing after bar t. So truncating its
    input immediately after t must not change that value:

        signal_fn(returns[:t+1])[t]  ==  signal_fn(returns)[t]

    If the vectorized path peeked forward — a centred window, a full-series mean used for
    standardisation, a `mode="same"` convolution, an off-by-one forward shift — the two
    disagree, and the index of the first disagreement points straight at the bar where it
    happened. This is a structural check with no statistics in it: no effect size, no
    horizon, no power to run out of.

    INDEPENDENCE IS STRUCTURAL, NOT DUPLICATED. The obvious way to build this — write a
    second, loop-based implementation of each signal and compare — fails for the reason
    two implementations by the same author usually agree: a shared misunderstanding
    cancels out and the test passes while both are wrong. Feeding a *prefix* to the same
    function tests the property directly instead, and needs no second implementation to be
    kept in sync.

    COST is O(n · checks) because each re-derivation recomputes from the start. `n_checks`
    bars are sampled rather than all n. A leak that touches most bars is caught by the
    first check; the sampling only matters for a leak confined to a handful of bars, and
    the returned `n_checked` says how hard anyone looked.

    `tolerance` is 0.0 by default, which is right for the boolean and integer signals the
    pipeline uses. Float-valued signals can differ in the last bits for legitimate reasons
    if an implementation's summation order depends on array length, and those need a small
    tolerance — a difference of 1e-16 is not a lookahead bug.
    """
    r = np.asarray(returns, dtype=float)
    n = r.size
    full = np.asarray(signal_fn(r))
    if full.ndim != 1 or full.size != n:
        raise ValueError(
            f"signal_fn must return one value per bar: got shape {full.shape} for "
            f"{n} returns"
        )
    if warmup >= n:
        raise ValueError(f"warmup {warmup} leaves no bars to check in a series of {n}")

    candidates = np.arange(warmup, n)
    take = min(n_checks, candidates.size)
    idx = np.sort(rng.choice(candidates, size=take, replace=False))

    mismatches: list[int] = []
    for t in idx:
        redone = np.asarray(signal_fn(r[: t + 1]))
        if redone.size != t + 1:
            raise ValueError(
                f"signal_fn returned {redone.size} values for a {t + 1}-bar prefix; it "
                f"must be length-preserving for this check to mean anything"
            )
        a, b = full[t], redone[t]
        if full.dtype == bool or tolerance == 0.0:
            differs = bool(a != b)
        else:
            differs = not (
                (np.isnan(a) and np.isnan(b)) or abs(float(a) - float(b)) <= tolerance
            )
        if differs:
            mismatches.append(int(t))

    detected = bool(mismatches)
    if detected:
        detail = (
            f"LOOKAHEAD DETECTED — {len(mismatches)} of {take} re-derived bars disagree "
            f"with the vectorized path; first at bar {mismatches[0]}. The signal at that "
            f"bar changes when data after it is removed, so it is reading the future."
        )
    else:
        detail = (
            f"clean — all {take} re-derived bars matched exactly. Every checked bar is "
            f"unchanged when the series is truncated immediately after it."
        )
    return ReconstructionResult(
        n_checked=take, n_mismatched=len(mismatches),
        first_mismatch=mismatches[0] if mismatches else None,
        leak_detected=detected, mismatch_indices=tuple(mismatches), detail=detail,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 7.2  Synthetic noise test
# ══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class NoiseTestResult:
    generator: str
    n_replications: int
    n_promoted: int
    n_stage1_passes: int
    trials_per_run: int
    promotion_rate: float
    stage1_pass_rate: float
    detail: str
    per_run: list[dict] = field(default_factory=list)

    @property
    def found_nothing(self) -> bool:
        return self.n_promoted == 0


def synthetic_noise_test(
    generate: Callable[[np.random.Generator], np.ndarray],
    pipeline: Callable[[np.ndarray, np.random.Generator], object],
    *,
    name: str,
    n_replications: int,
    rng: np.random.Generator,
) -> NoiseTestResult:
    """§7.2: run the complete pipeline on data with no edge by construction.

    "The pipeline must report 'nothing found.' If it promotes a strategy on synthetic
    noise, the pipeline is broken and every result it has ever produced is void."

    `pipeline` must return an object exposing `promoted`, `stage1_passes` and `n_trials`.
    Stage 1 passes are counted separately from promotions: a Stage 1 pass that the §6
    corrections then kill is the machinery working, whereas a promotion is a failure.
    """
    promoted = 0
    stage1 = 0
    trials = 0
    per_run: list[dict] = []
    for i in range(n_replications):
        series = generate(rng)
        result = pipeline(series, rng)
        n_prom = len(getattr(result, "promoted", []))
        n_s1 = int(getattr(result, "stage1_passes", 0))
        trials = int(getattr(result, "n_trials", 0))
        promoted += bool(n_prom)
        stage1 += n_s1
        per_run.append({
            "run": i + 1, "promoted": n_prom, "stage1_passes": n_s1,
            "dsr": getattr(getattr(result, "dsr", None), "dsr", float("nan")),
            "pbo": getattr(getattr(result, "pbo", None), "pbo", float("nan")),
            "best_sharpe": float(getattr(result, "best_sharpe", float("nan"))),
        })

    rate = promoted / n_replications if n_replications else float("nan")
    detail = (
        f"{name}: {promoted}/{n_replications} runs promoted a strategy "
        f"({trials} trials each). "
        + ("Nothing found, as required." if promoted == 0 else
           "PIPELINE IS BROKEN — §7.2: every result it has produced is void.")
    )
    return NoiseTestResult(
        generator=name, n_replications=n_replications, n_promoted=promoted,
        n_stage1_passes=stage1, trials_per_run=trials, promotion_rate=rate,
        stage1_pass_rate=stage1 / max(n_replications * max(trials, 1), 1),
        detail=detail, per_run=per_run,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 7.3  Shuffled-label test
# ══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ShuffleResult:
    observed_effect: float
    mean_shuffled_effect: float
    max_abs_shuffled: float
    ratio: float
    p_value: float
    collapsed: bool
    n_permutations: int
    detail: str


def shuffled_label_test(
    signal: np.ndarray,
    returns: np.ndarray,
    horizon: int,
    *,
    rng: np.random.Generator,
    n_permutations: int = 1000,
    ceiling: float = SHUFFLE_COLLAPSE_CEILING,
) -> ShuffleResult:
    """§7.3: permute the condition flags against the returns. Effect must collapse to zero.

    Labels are rotated circularly rather than resampled independently. Rotation preserves
    the autocorrelation of BOTH series and the clustering of the signal itself, destroying
    only their alignment. An iid shuffle would additionally destroy the signal's own
    structure, which narrows the null and makes almost anything look significant.
    """
    from futuresres.signals.stage1 import forward_returns

    sig = np.asarray(signal, dtype=bool)
    fwd = forward_returns(returns, horizon)
    valid = np.isfinite(fwd)
    sig, fwd = sig[valid], fwd[valid]
    n = fwd.size
    if sig.sum() == 0 or sig.all():
        raise ValueError("signal is constant — there is nothing to shuffle against")

    baseline = float(fwd.mean())
    observed = float(fwd[sig].mean() - baseline)

    null = np.empty(n_permutations)
    for i in range(n_permutations):
        rolled = np.roll(sig, int(rng.integers(1, n)))
        null[i] = fwd[rolled].mean() - baseline

    mean_null = float(np.mean(null))
    max_null = float(np.max(np.abs(null)))
    ratio = abs(mean_null) / abs(observed) if observed != 0 else np.nan
    p = float((np.sum(np.abs(null) >= abs(observed)) + 1) / (n_permutations + 1))
    collapsed = bool(np.isfinite(ratio) and ratio <= ceiling)

    return ShuffleResult(
        observed_effect=observed, mean_shuffled_effect=mean_null,
        max_abs_shuffled=max_null, ratio=float(ratio), p_value=p,
        collapsed=collapsed, n_permutations=n_permutations,
        detail=(f"observed {observed:+.3e}; shuffled mean {mean_null:+.3e} "
                f"({ratio:.1%} of observed); permutation p = {p:.4f}"),
    )


# ══════════════════════════════════════════════════════════════════════════════
# 7.4  Monte Carlo drawdown distribution
# ══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class DrawdownResult:
    realized: float
    median: float
    p95: float
    p99: float
    worst: float
    n_iterations: int
    method: str
    understatement: float

    @property
    def detail(self) -> str:
        return (
            f"{self.method}: realized {self.realized:,.4f}, median {self.median:,.4f}, "
            f"95th pct {self.p95:,.4f}, 99th {self.p99:,.4f}, worst {self.worst:,.4f}. "
            f"Realized understates the 95th percentile by {self.understatement:.1%}."
        )


def max_drawdown(pnl: Sequence[float] | np.ndarray) -> float:
    """Largest peak-to-trough decline of the cumulative sum. Returned POSITIVE.

    The running peak starts at zero, so a strategy that is under water from the first
    trade has a drawdown equal to its loss rather than zero.
    """
    x = np.asarray(pnl, dtype=float)
    if x.size == 0:
        return 0.0
    equity = np.cumsum(x)
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    return float(np.max(peak - equity))


def monte_carlo_drawdown(
    trade_pnl: Sequence[float] | np.ndarray,
    *,
    rng: np.random.Generator,
    n_iterations: int = DEFAULT_MC_ITERATIONS,
) -> DrawdownResult:
    """§7.4: trade-order shuffle. The realized max DD is one draw from this distribution.

    Same trades, same total P&L, different order. The spread this produces is the honest
    uncertainty in the drawdown figure, and §7.4 says to size against the 95th percentile
    rather than the one ordering history happened to deal.
    """
    x = np.asarray(trade_pnl, dtype=float)
    if x.size == 0:
        raise ValueError("no trades to shuffle")

    realized = max_drawdown(x)
    draws = np.empty(n_iterations)
    for i in range(n_iterations):
        draws[i] = max_drawdown(rng.permutation(x))

    p95 = float(np.percentile(draws, DD_PERCENTILE))
    return DrawdownResult(
        realized=realized, median=float(np.median(draws)), p95=p95,
        p99=float(np.percentile(draws, 99)), worst=float(draws.max()),
        n_iterations=n_iterations, method="trade-order shuffle",
        understatement=float(1.0 - realized / p95) if p95 > 0 else 0.0,
    )


def block_bootstrap_drawdown(
    daily_returns: Sequence[float] | np.ndarray,
    *,
    rng: np.random.Generator,
    block: int = 20,
    n_iterations: int = DEFAULT_MC_ITERATIONS,
) -> DrawdownResult:
    """§7.4: block bootstrap on daily returns.

    The trade-order shuffle assumes trades are exchangeable, which throws away the fact
    that bad days cluster. Resampling contiguous blocks keeps that clustering, and it
    generally produces a WIDER drawdown distribution than the shuffle — which is the more
    honest one to size against.
    """
    x = np.asarray(daily_returns, dtype=float)
    if x.size < block:
        raise ValueError(f"need at least {block} observations for block size {block}")

    realized = max_drawdown(x)
    n_blocks = int(np.ceil(x.size / block))
    draws = np.empty(n_iterations)
    for i in range(n_iterations):
        starts = rng.integers(0, x.size - block + 1, size=n_blocks)
        sample = np.concatenate([x[s:s + block] for s in starts])[:x.size]
        draws[i] = max_drawdown(sample)

    p95 = float(np.percentile(draws, DD_PERCENTILE))
    return DrawdownResult(
        realized=realized, median=float(np.median(draws)), p95=p95,
        p99=float(np.percentile(draws, 99)), worst=float(draws.max()),
        n_iterations=n_iterations, method=f"block bootstrap (block={block})",
        understatement=float(1.0 - realized / p95) if p95 > 0 else 0.0,
    )
