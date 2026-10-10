"""Z06 - the 12-month trend sign sets the staking plans' bracket direction (MNQ 09:30-16:00, MGC 03:00-11:30 ET).
hypotheses.yaml Z06; decisions.md 110.

    python -m futuresres.signals.z06 --inject
    python -m futuresres.signals.z06 --run         # THE TRIAL

SOURCE: Moskowitz, Ooi & Pedersen (2012, JFE): sign of the past 12-month excess return predicts the next month,
58 futures, 1985-2009. A follow-on to W04 (decisions.md 72-76).

FIXED BEFORE ANY RETURN (decisions.md 110):
  signal       at each month end M, sign of the held return compounded over the 12 calendar months ending at M
               (data/daily_bars.py, roll-correct, NQ and GC); applied to every session dated in the month after M.
               A daily bar of date M closes 00:00 UTC on M+1 - before any window of a session dated after M opens.
  windows      MNQ 09:30-16:00 ET, MGC 03:00-11:30 ET; real window return (drift kept), complete sessions only.
  test window  sessions 2011-07-01 to 2026-08-27.
  decision     per product: (1) Sharpe of sign x window return > 0; (2) mean(sign x r) > mean(r) - beats always-
               long; (3) posterior > 0 (=> plan EV at posterior > zero-edge EV by A11, decisions.md 109).
               Prior Normal(0.2, 0.3), an ASSUMPTION (published per-instrument sizes are only charted).
"""

from __future__ import annotations

import sys

TEST_START, TEST_END = "2011-07-01", "2026-08-27"
PRIOR_MEAN, PRIOR_SD = 0.2, 0.3
PLANS = {"MNQ": {"daily": "NQ", "window": "rth_0930_1600"}, "MGC": {"daily": "GC", "window": "london_0300_1130"}}


def monthly_sign(dates, ret):
    """{(year, month): +1/-1} for the month AFTER each month end, from the trailing 12 calendar months."""
    import numpy as np
    d = dates.astype("datetime64[M]")
    months = np.unique(d)
    out = {}
    for m in months:
        lo = m - np.timedelta64(11, "M")
        sel = (d >= lo) & (d <= m)
        if (d < lo).sum() == 0:                  # need a full 12 months of history before the first signal
            continue
        r12 = float(np.prod(1.0 + ret[sel]) - 1.0)
        nxt = m + np.timedelta64(1, "M")
        out[str(nxt)] = 1.0 if r12 > 0 else -1.0
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.z06")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    from futuresres.signals import z06_trial as zt
    return zt.injection() if a.inject else zt.run_trial()


if __name__ == "__main__":
    sys.exit(main())
