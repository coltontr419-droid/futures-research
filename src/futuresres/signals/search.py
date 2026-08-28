"""A complete, small pipeline: search → Stage 1 gate → §6 corrections.

This exists so §7.2 has a *pipeline* to run on noise rather than a single statistic. The
search is the essential part. Evaluating one pre-chosen signal on noise proves almost
nothing — the failure mode §7.2 targets is that **searching** noise reliably produces
something that looks good, and a harness which forgets to count the search will promote it.

The pipeline is deliberately conjunctive. A candidate is promoted only if:

    1. Stage 1 separation holds  (bootstrap CI excludes zero AND permutation p < α)
    2. Deflated Sharpe > 0.95    (deflated by N = every trial run, not the survivors)
    3. PBO ≤ 0.5                 (§6: reject above 0.5)

Every candidate × horizon is a trial and every one is counted. Counting only the survivors
is the exact arithmetic error that makes overfitting invisible.

SIGNAL FAMILY. Moving-average crossovers at round, a-priori lookbacks (§5 Stage 5: "20/50/
200, not 47"). The family is arbitrary and that is fine — the null is that NOTHING should
pass, so the specific rules matter less than that there are many of them and all are
computed only from past bars.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Sequence

import numpy as np

from futuresres.signals.stage1 import Stage1Result, evaluate_signal
from futuresres.stats.dsr import DSRResult, deflated_sharpe_ratio, sharpe_ratio
from futuresres.stats.pbo import PBOResult, pbo_cscv
from futuresres.stats.trials import Trial, TrialLog

#: Round lookbacks per §5 Stage 5.
DEFAULT_FAST: Final[tuple[int, ...]] = (5, 10, 20, 50)
DEFAULT_SLOW: Final[tuple[int, ...]] = (50, 100, 200, 500)
DEFAULT_HORIZONS: Final[tuple[int, ...]] = (10, 60, 240)

DSR_THRESHOLD: Final[float] = 0.95
PBO_THRESHOLD: Final[float] = 0.5


@dataclass(frozen=True, slots=True)
class Candidate:
    name: str
    fast: int
    slow: int


@dataclass(frozen=True, slots=True)
class PipelineResult:
    promoted: list[str]
    n_trials: int
    n_candidates: int
    horizons: tuple[int, ...]
    best_name: str
    best_sharpe: float
    stage1_passes: int
    dsr: DSRResult | None
    pbo: PBOResult | None
    stage1: dict[str, Stage1Result] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def found_nothing(self) -> bool:
        return not self.promoted


def _rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    """Trailing mean over `window` bars ending at t, inclusive. NaN until the window fills.

    Inclusive of bar t and nothing after it. A centred window here would be a lookahead
    bug that §7.1 is designed to catch, so it is ruled out at the source.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    # c[i] is the sum of the first i elements, so the window ending at t is
    # c[t+1] − c[t+1−window]. Both slices then have length n+1−window, which is exactly
    # the number of positions from window−1 to the end. No special case for window == 1.
    c = np.concatenate([[0.0], np.cumsum(x)])
    out = np.full(x.size, np.nan)
    if x.size >= window:
        out[window - 1:] = (c[window:] - c[:-window]) / window
    return out


def crossover_signals(
    returns: np.ndarray,
    fasts: Sequence[int] = DEFAULT_FAST,
    slows: Sequence[int] = DEFAULT_SLOW,
) -> tuple[list[Candidate], np.ndarray]:
    """Build the candidate family. Returns (candidates, T×N boolean signal matrix).

    Signals are computed on the cumulative log-price path from `returns`, using only bars
    up to and including t.
    """
    price = np.cumsum(np.asarray(returns, dtype=float))
    cands: list[Candidate] = []
    cols: list[np.ndarray] = []
    for f in fasts:
        for s in slows:
            if f >= s:
                continue
            fast_ma = _rolling_mean(price, f)
            slow_ma = _rolling_mean(price, s)
            sig = np.zeros(price.size, dtype=bool)
            ok = np.isfinite(fast_ma) & np.isfinite(slow_ma)
            sig[ok] = fast_ma[ok] > slow_ma[ok]
            cands.append(Candidate(f"ma_{f}_{s}", f, s))
            cols.append(sig)
    if not cands:
        raise ValueError("no valid fast/slow pairs — every fast must be below some slow")
    return cands, np.column_stack(cols)


def strategy_returns(signals: np.ndarray, returns: np.ndarray) -> np.ndarray:
    """T×N matrix of per-bar strategy returns: hold when the signal is on, one bar late.

    Position at bar t is decided by the signal at t and earns the return of bar t+1. The
    shift is what keeps the accounting honest; without it the position would earn the very
    bar that produced the signal.
    """
    r = np.asarray(returns, dtype=float)
    nxt = np.concatenate([r[1:], [0.0]])
    return signals.astype(float) * nxt[:, None]


def run_pipeline(
    returns: np.ndarray,
    *,
    rng: np.random.Generator,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    fasts: Sequence[int] = DEFAULT_FAST,
    slows: Sequence[int] = DEFAULT_SLOW,
    n_bootstrap: int = 500,
    n_permutations: int = 500,
    n_splits: int = 8,
    trial_log: TrialLog | None = None,
    hypothesis_id: str = "SEARCH",
    symbol: str = "SYNTHETIC",
    date_range: tuple[str, str] = ("", ""),
) -> PipelineResult:
    """Search the family, gate at Stage 1, then apply the §6 corrections.

    Returns a PipelineResult whose `found_nothing` is what §7.2 asserts on a null series.

    TRIAL LOGGING. When `trial_log` is supplied, one record is appended per candidate ×
    horizon — including every configuration that FAILS the Stage 1 gate, per the §6
    resolution that Stage 1 selects on the same data and so enters N. It defaults to None
    only so the §7.2 noise tests can run thousands of synthetic pipelines without writing
    them into the real trial log; any run against real data must pass one.

    KNOWN ASYMMETRY, and it is deliberate rather than an oversight. There are
    `candidates × horizons` TRIALS but only `candidates` distinct strategy Sharpes,
    because horizon enters the Stage 1 statistic while `strategy_returns` holds a position
    for one bar regardless. So N counts trials (the wider, correct number for the
    deflation) while V is estimated from the distinct Sharpes (repeating a value three
    times would understate the dispersion). Making horizon change the return series would
    align them at the cost of invalidating the detection floor in
    `reports/pipeline_power.md`, which was measured under this model — worth doing, but as
    a deliberate re-measurement rather than a side effect.
    """
    cands, signals = crossover_signals(returns, fasts, slows)
    strat = strategy_returns(signals, returns)
    notes: list[str] = []

    # Sharpes for EVERY configuration, computed before any gate is applied. §6: the DSR
    # needs both N and V, and V estimated over survivors alone repeats the selection bias
    # the correction exists to remove.
    sharpes = np.array([
        sharpe_ratio(strat[:, i]) if strat[:, i].std(ddof=1) > 0 else 0.0
        for i in range(strat.shape[1])
    ])
    best = int(np.argmax(sharpes))
    best_name = cands[best].name

    # Every candidate × horizon is a trial, counted and LOGGED whether or not it passes.
    stage1: dict[str, Stage1Result] = {}
    passes: list[str] = []
    for i, cand in enumerate(cands):
        for h in horizons:
            res = evaluate_signal(
                signals[:, i], returns, h, rng=rng,
                n_bootstrap=n_bootstrap, n_permutations=n_permutations,
            )
            stage1[f"{cand.name}@{h}"] = res
            if res.separated:
                passes.append(f"{cand.name}@{h}")
            if trial_log is not None:
                trial_log.append(Trial(
                    trial_id=trial_log.next_id(),
                    hypothesis_id=hypothesis_id,
                    params={"fast": cand.fast, "slow": cand.slow, "horizon": h},
                    symbol=symbol,
                    date_range=date_range,
                    status="completed",
                    sharpe=float(sharpes[i]),
                    trade_count=int(res.n_signals) if res.n_signals else None,
                    note=("stage1 pass" if res.separated else f"stage1 fail: {res.reason}")
                         + f" · p={res.p_value:.4f}"
                         if np.isfinite(res.p_value) else "stage1 not evaluable",
                ))

    n_trials = len(cands) * len(horizons)

    dsr: DSRResult | None = None
    pbo: PBOResult | None = None

    if not passes:
        notes.append(
            f"No candidate cleared Stage 1 at any horizon ({n_trials} trials). "
            f"§5 Stage 1: if there is no separation at the signal level, STOP."
        )
    else:
        notes.append(f"{len(passes)} of {n_trials} trials cleared Stage 1: {passes[:5]}")

    # DSR and PBO are computed regardless, because "Stage 1 passed but the corrections
    # killed it" and "nothing passed Stage 1" are different findings worth telling apart.
    try:
        dsr = deflated_sharpe_ratio(strat[:, best], sharpes, n_trials=n_trials)
    except ValueError as exc:
        notes.append(f"DSR not computable: {exc}")
    try:
        pbo = pbo_cscv(strat, n_splits=n_splits)
    except ValueError as exc:
        notes.append(f"PBO not computable: {exc}")

    promoted: list[str] = []
    if passes and dsr is not None and pbo is not None:
        if dsr.dsr > DSR_THRESHOLD and pbo.pbo <= PBO_THRESHOLD:
            promoted = passes
        else:
            notes.append(
                f"Stage 1 survivors killed by §6: DSR={dsr.dsr:.4f} "
                f"(need > {DSR_THRESHOLD}), PBO={pbo.pbo:.4f} (need ≤ {PBO_THRESHOLD})"
            )

    return PipelineResult(
        promoted=promoted, n_trials=n_trials, n_candidates=len(cands),
        horizons=tuple(horizons), best_name=best_name,
        best_sharpe=float(sharpes[best]), stage1_passes=len(passes),
        dsr=dsr, pbo=pbo, stage1=stage1, notes=notes,
    )
