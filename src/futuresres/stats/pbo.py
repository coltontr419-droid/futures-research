"""Probability of Backtest Overfitting via CSCV — CLAUDE.md §6, build order step 5.

Bailey, Borwein, López de Prado & Zhu, *The Probability of Backtest Overfitting*
(Journal of Computational Finance, 2015).

The question PBO answers: when we pick the best-performing configuration in-sample, how
often does it land in the bottom half out-of-sample? If that happens more than half the
time, the selection procedure is worse than useless — §6: **reject if PBO > 0.5.**

THE ALGORITHM

Given a T×N matrix of per-period returns (T periods, N candidate configurations):

  1. Split the rows into S equal contiguous blocks, preserving time order inside each.
  2. For every one of the C(S, S/2) ways to choose S/2 blocks as in-sample, the remaining
     blocks are out-of-sample. This is what makes it *combinatorially symmetric*: each
     split and its complement both appear, so no single arbitrary train/test cut decides
     the answer.
  3. In-sample, pick the best configuration n*. Out-of-sample, find where n* ranks among
     all N configurations — rank 1 is worst, N is best.
  4. ω = rank/(N+1) is its relative rank; λ = log(ω/(1−ω)) is the logit of that.
  5. PBO = fraction of splits with λ ≤ 0, i.e. where the in-sample winner came out below
     the out-of-sample median.

WHY CONTIGUOUS BLOCKS. Rows are not exchangeable — returns have volatility clustering and
serial dependence. Shuffling individual rows into the two halves would leak the structure
of one across into the other and drive PBO down for the wrong reason.

WHAT PBO IS NOT. It measures the *selection procedure*, not a single configuration. A low
PBO says that picking the in-sample best tends to survive out-of-sample; it does not say
the survivor is profitable, and it does not replace the holdout in §5 Stage 8.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Callable, Final

import numpy as np

#: §6: "PBO via CSCV — reject if > 0.5."
REJECT_ABOVE: Final[float] = 0.5

#: The paper's default. Even, and C(16,8) = 12,870 splits.
DEFAULT_SPLITS: Final[int] = 16

Metric = Callable[[np.ndarray], np.ndarray]


@dataclass(frozen=True, slots=True)
class PBOResult:
    pbo: float
    lambdas: np.ndarray
    relative_ranks: np.ndarray
    n_splits: int
    n_combinations: int
    n_configs: int
    n_obs_used: int
    n_obs_dropped: int
    is_best_indices: np.ndarray

    @property
    def rejects(self) -> bool:
        return self.pbo > REJECT_ABOVE

    @property
    def median_logit(self) -> float:
        return float(np.median(self.lambdas))


def column_sharpe(block: np.ndarray) -> np.ndarray:
    """Per-observation Sharpe of each column. The default CSCV performance metric.

    Columns with zero variance score −inf: a configuration that never moved cannot be
    "best in-sample", and giving it 0.0 would let a flat line win a quiet block.
    """
    if block.shape[0] < 2:
        raise ValueError(f"need >= 2 rows to score a block, got {block.shape[0]}")
    sd = block.std(axis=0, ddof=1)
    mean = block.mean(axis=0)
    out = np.full(block.shape[1], -np.inf, dtype=float)
    np.divide(mean, sd, out=out, where=sd > 0)
    return out


def _ranks_worst_to_best(values: np.ndarray) -> np.ndarray:
    """1 = worst … N = best, ties averaged.

    Ties matter: two identical configurations should share a rank rather than have their
    order decided by argsort, which would make PBO depend on column ordering.
    """
    n = values.size
    order = np.argsort(values, kind="stable")
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(1, n + 1, dtype=float)
    # average tied groups
    unique, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    for idx in np.flatnonzero(counts > 1):
        mask = inverse == idx
        ranks[mask] = ranks[mask].mean()
    return ranks


def pbo_cscv(
    matrix: np.ndarray,
    n_splits: int = DEFAULT_SPLITS,
    metric: Metric = column_sharpe,
) -> PBOResult:
    """Run CSCV over a T×N matrix of per-period returns.

    Rows are time, columns are candidate configurations. Every configuration tried during
    the search belongs here — feeding only the survivors is the exact selection bias this
    procedure exists to measure.
    """
    m = np.asarray(matrix, dtype=float)
    if m.ndim != 2:
        raise ValueError(f"expected a 2-D T×N matrix, got shape {m.shape}")
    n_obs, n_configs = m.shape
    if n_configs < 2:
        raise ValueError(
            f"need >= 2 configurations to rank, got {n_configs}. With one configuration "
            f"there is no selection, so there is nothing to measure."
        )
    if n_splits < 2 or n_splits % 2 != 0:
        raise ValueError(f"n_splits must be even and >= 2, got {n_splits}")
    if n_obs < n_splits * 2:
        raise ValueError(
            f"{n_obs} rows across {n_splits} splits leaves under 2 rows per block; "
            f"a Sharpe needs at least 2. Use fewer splits or more data."
        )

    # Equal blocks. The remainder is dropped from the END rather than spread unevenly:
    # unequal blocks would give some combinations more data than others and quietly
    # weight the splits.
    block_len = n_obs // n_splits
    used = block_len * n_splits
    blocks = [np.arange(i * block_len, (i + 1) * block_len) for i in range(n_splits)]

    all_idx = set(range(n_splits))
    lambdas: list[float] = []
    omegas: list[float] = []
    best: list[int] = []

    for is_blocks in combinations(range(n_splits), n_splits // 2):
        oos_blocks = sorted(all_idx - set(is_blocks))
        is_rows = np.concatenate([blocks[b] for b in sorted(is_blocks)])
        oos_rows = np.concatenate([blocks[b] for b in oos_blocks])

        is_perf = np.asarray(metric(m[is_rows]), dtype=float)
        oos_perf = np.asarray(metric(m[oos_rows]), dtype=float)
        if is_perf.shape != (n_configs,) or oos_perf.shape != (n_configs,):
            raise ValueError(
                f"metric must return one value per configuration ({n_configs}), got "
                f"{is_perf.shape} and {oos_perf.shape}"
            )

        n_star = int(np.argmax(is_perf))
        rank = float(_ranks_worst_to_best(oos_perf)[n_star])
        omega = rank / (n_configs + 1.0)
        lambdas.append(math.log(omega / (1.0 - omega)))
        omegas.append(omega)
        best.append(n_star)

    lam = np.asarray(lambdas, dtype=float)
    return PBOResult(
        # λ ≤ 0 rather than < 0: with an odd N the in-sample winner can land exactly on
        # the out-of-sample median, and "no better than the median" is not evidence the
        # selection worked.
        pbo=float(np.mean(lam <= 0.0)),
        lambdas=lam,
        relative_ranks=np.asarray(omegas, dtype=float),
        n_splits=n_splits,
        n_combinations=lam.size,
        n_configs=n_configs,
        n_obs_used=used,
        n_obs_dropped=n_obs - used,
        is_best_indices=np.asarray(best, dtype=int),
    )
