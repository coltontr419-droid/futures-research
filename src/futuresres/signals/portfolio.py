"""The one place a PORTFOLIO's positions meet returns. W04's evaluator (decisions.md 73).

`stage1.evaluate_signed_signal` scores an intraday event signal against its own unconditional
baseline; a daily portfolio rule has no events and no baseline, and is judged by the absolute Sharpe
of its net daily return against the multiple-testing bar. This module is that scorer. It takes the
positions a signal module produced (sleeves, already timed to the bars they are held on) and the
per-market held returns the data layer produced, and builds the scored series itself: no caller
hands it a return series of its own construction.

Its control is the rotation null of decisions.md 54, adapted: each sleeve's position series is
rotated circularly by its own random offset (at least one year), keeping that sleeve's persistence,
exposure and long/short balance and destroying its alignment with returns. Drift an always-long book
would earn survives rotation, so a rule that only rode drift sits inside its own null.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

ANNUAL: Final[int] = 252
MIN_SHIFT: Final[int] = 252


def _sharpe(x: np.ndarray) -> float:
    sd = x.std(ddof=1)
    return float(x.mean() / sd * math.sqrt(ANNUAL)) if sd > 0 else float("nan")


def _series(sleeves: list[np.ndarray], rets: np.ndarray, cost: np.ndarray
            ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    w = np.sum(sleeves, axis=0)
    gross = np.sum(w * rets, axis=1)
    charge = np.sum(np.abs(w) * cost, axis=1)
    return gross, gross - charge, w


def evaluate_portfolio(dates: np.ndarray, sleeves: list[np.ndarray], rets: np.ndarray,
                       cost: np.ndarray, era_break: str, n_rotations: int = 500,
                       seed: int = 54) -> dict:
    """Gross and net daily portfolio returns; Sharpe by era; rotation null on the net Sharpe.

    Bars before the first held position are excluded (the warm-up is not a flat strategy)."""
    gross, net, w = _series(sleeves, rets, cost)
    live = np.flatnonzero(np.any(w != 0, axis=1))
    first = int(live[0]) if len(live) else len(dates)
    post = dates >= np.datetime64(era_break)
    eras = {"full": np.arange(len(dates)) >= first, "post_2021": post & (np.arange(len(dates)) >= first),
            "pre_2021": ~post & (np.arange(len(dates)) >= first)}
    out: dict = {"first_held": str(dates[first]) if first < len(dates) else None}
    for name, mask in eras.items():
        n = int(mask.sum())
        out[name] = {"t": n,
                     "sharpe_gross": _sharpe(gross[mask]) if n > 2 else float("nan"),
                     "sharpe_net": _sharpe(net[mask]) if n > 2 else float("nan"),
                     "mean_daily_net": float(net[mask].mean()) if n else float("nan"),
                     "sd_daily_net": float(net[mask].std(ddof=1)) if n > 2 else float("nan"),
                     "cost_share_of_gross_mean": (float((gross[mask] - net[mask]).mean()
                                                  / gross[mask].mean()) if n and gross[mask].mean() else None)}
    if n_rotations:
        rng = np.random.default_rng(seed)
        t = len(dates)
        null = np.empty(n_rotations)
        m = eras["post_2021"]
        for k in range(n_rotations):
            rot = [np.roll(s, int(rng.integers(MIN_SHIFT, t - MIN_SHIFT))) for s in sleeves]
            _, nn, _ = _series(rot, rets, cost)
            null[k] = _sharpe(nn[m])
        real = out["post_2021"]["sharpe_net"]
        out["rotation_null_post_2021"] = {
            "n": n_rotations, "mean": float(null.mean()), "p95": float(np.quantile(null, 0.95)),
            "share_at_or_above_real": float((null >= real).mean()),
        }
    out["_net"] = net
    out["_weights"] = w
    return out
