"""Vectorised equivalent of crps_upstream.calculate_crps_for_miner for complete (no-NaN) real paths, ~100x faster. decisions.md §1164.
CRPS(ensemble x, obs y) = mean|x - y| - 0.5 * mean|x - x'|, with the pair term from the sorted ensemble: (2/N^2) * sum_i (2i - N - 1) x_(i)."""

from __future__ import annotations

import numpy as np


def crps_cols(ens: np.ndarray, obs: np.ndarray) -> np.ndarray:
    """CRPS per column: ens (N, T), obs (T,)."""
    n = ens.shape[0]
    t1 = np.abs(ens - obs[None, :]).mean(axis=0)
    s = np.sort(ens, axis=0); w = (2 * np.arange(1, n + 1) - n - 1)[:, None]
    pair = 2.0 * (w * s).sum(axis=0) / n ** 2
    return t1 - 0.5 * pair


def changes(p: np.ndarray, steps: int, absolute: bool, gap: bool) -> np.ndarray:
    q = p[:, ::steps]
    if gap:
        q = q[:, :2]
    if absolute:
        return q[:, 1:]
    return np.diff(q, axis=1) / q[:, :-1] * 10_000


def crps_sum(paths: np.ndarray, real: np.ndarray, time_increment: int, intervals: dict[str, int]) -> float:
    real = np.asarray(real, float).reshape(1, -1); total = 0.0
    for name, sec in intervals.items():
        steps = int(sec / time_increment); absolute = name.endswith("_abs"); gap = name.endswith("_gaps")
        if absolute:
            while real[:, ::steps].shape[1] == 1 and steps > 1:
                steps -= 1
        sim = changes(paths, steps, absolute, gap); obs = changes(real, steps, absolute, gap)[0]
        if obs.size == 0:
            continue
        c = crps_cols(sim, obs)
        if absolute:
            c = c / real[0, -1] * 10_000
        total += float(c.sum())
    return total
