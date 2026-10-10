"""Z02 - front-running institutional rebalancing, the equity leg alone. hypotheses.yaml Z02; decisions.md 86-87.

    python -m futuresres.signals.z02 --check      # construction check: signal properties only, 2010-2023
    python -m futuresres.signals.z02 --inject     # outcome injection (synthetic alignment, real noise)
    python -m futuresres.signals.z02 --run        # THE TRIAL: one record in trials.jsonl

SOURCE: Harvey, Mazzoleni & Melone, "The Unintended Consequences of Rebalancing", NBER w33554 (2025, rev.
2026), Appendix B and Section 4. Every rule below is theirs, copied before any data was touched; the one
reading taken where their text is ambiguous is marked READING.

A SIGNAL MODULE: returns enter only as inputs to the 60/40 drift simulation. The scored series is built in
`portfolio.evaluate_portfolio` (test_signal_module_boundary).

  60/40 DRIFT   w(t+1) = w(t)(1+R_SP) / [w(t)(1+R_SP) + (1-w(t))(1+R_10Y)], target 60%.
  THRESHOLD     for each delta in 0%, 0.1%, ..., 2.5% (26 values): signal(t+1) = drift(w(t); R(t+1)) - 60%;
                the state resets to 60% when that day's drifted weight is >= delta from target (the fund
                rebalances on the breach), else drifts. (B.1)
                READING, calibrated BEFORE any return was computed (decisions.md 87): the PDF text of B.1
                loses its notation, leaving it open whether the breach is judged on the previous day's
                weight or on the day's drifted weight. Against the paper's own published signal property
                (Table C.1, Threshold AR(1) 0.61) on 2010-2023: previous-day reading 0.78 (0.77-0.80 in
                both halves, so not an era effect), drifted-weight reading 0.65. The latter is used.
                The Threshold signal is the average over the 26 deltas. (Eq. 2)
  CALENDAR      signal(t+1) = drift(w(t); R(t+1)) - 60%; the state resets to 60% at t+1 when t is the last
                business day of the month, else drifts. (B.2)
  WEIGHT        average of (-Threshold / 1.5%) and a modified Calendar signal: sign(-Calendar(t)) when t
                is in the last week of the month; on the first business day of a month, sign(Calendar) as
                of four business days before the previous month-end; zero otherwise. (Section 4)
                READING: "last week" = the last 5 business days; "four business days before month-end" =
                the 4th-from-last business day, the last being -1 (the paper's Figure D.2 axis).
  RETURN        weight(t) x R(t+1). Z02 trades the S&P leg alone (on MES); the paper's long/short spread
                (Z01) is not tradable in this account (opposite positions counted as hedging, user
                2026-10-09) and is not run.
"""

from __future__ import annotations

import sys
from typing import Final

import numpy as np

TARGET: Final[float] = 0.60
DELTAS: Final[np.ndarray] = np.round(np.arange(0.0, 0.0251, 0.001), 4)      # 26 values
THRESHOLD_SCALE: Final[float] = 0.015
WEEK4: Final[int] = 5
CAL_LAG: Final[int] = 4


def _drift(w: np.ndarray | float, r_sp: float, r_ty: float):
    a = w * (1 + r_sp)
    return a / (a + (1 - w) * (1 + r_ty))


def threshold_signal(r_sp: np.ndarray, r_ty: np.ndarray) -> np.ndarray:
    """Signal on each day t (after day t's returns), averaged over the 26 deltas."""
    T = len(r_sp)
    w = np.full(len(DELTAS), TARGET)
    out = np.zeros(T)
    for t in range(T):
        d = _drift(w, r_sp[t], r_ty[t])
        out[t] = float((d - TARGET).mean())
        w = np.where(np.abs(d - TARGET) >= DELTAS, TARGET, d)
    return out


def month_positions(dates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(position from month-end, -1 = last business day; is-first-business-day) for each date."""
    m = dates.astype("datetime64[M]")
    pos = np.zeros(len(dates), int); first = np.zeros(len(dates), bool)
    starts = np.flatnonzero(np.r_[True, m[1:] != m[:-1]])
    ends = np.r_[starts[1:], len(dates)]
    for s, e in zip(starts, ends):
        pos[s:e] = np.arange(s - e, 0)          # ..., -3, -2, -1
        first[s] = True
    return pos, first


def calendar_signal(dates: np.ndarray, r_sp: np.ndarray, r_ty: np.ndarray) -> np.ndarray:
    pos, _ = month_positions(dates)
    T = len(r_sp)
    w = TARGET
    out = np.zeros(T)
    for t in range(T):
        d = _drift(w, r_sp[t], r_ty[t])
        out[t] = d - TARGET
        w = TARGET if pos[t] == -1 else d
    return out


def weights(dates: np.ndarray, r_sp: np.ndarray, r_ty: np.ndarray) -> np.ndarray:
    """weight(t): the position for the return of day t+1. NOT yet shifted."""
    thr = threshold_signal(r_sp, r_ty)
    cal = calendar_signal(dates, r_sp, r_ty)
    pos, first = month_positions(dates)
    mod = np.zeros(len(dates))
    week4 = pos >= -WEEK4
    mod[week4] = np.sign(-cal[week4])
    # first business day: sign of the Calendar signal at the previous month's 4th-from-last business day
    lag_idx = np.flatnonzero(pos == -CAL_LAG)
    for t in np.flatnonzero(first):
        prev = lag_idx[lag_idx < t]
        if len(prev):
            mod[t] = np.sign(cal[prev[-1]])
    return 0.5 * (-thr / THRESHOLD_SCALE) + 0.5 * mod


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.z02")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--inject", action="store_true")
    g.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    from futuresres.signals import z02_trial as zt
    if args.check:
        return zt.construction_check()
    if args.inject:
        return zt.injection()
    return zt.run_trial()


if __name__ == "__main__":
    sys.exit(main())
