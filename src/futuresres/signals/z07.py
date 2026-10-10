"""Z07 - index-level reversal (MAC(5)) sets the MNQ staking plan's bracket direction. hypotheses.yaml Z07;
decisions.md 111.

    python -m futuresres.signals.z07 --inject
    python -m futuresres.signals.z07 --run         # THE TRIAL

SOURCE: Baltussen, van Bekkum & Da (2019, JFE 132(1)): index returns negatively autocorrelated after ~1999; a
strategy against MAC(5) = r_t (4 r_t-1 + 3 r_t-2 + 2 r_t-3 + r_t-4) / (5 sigma^2) earned Sharpe 0.67 on the S&P
500 after March 1999; sample to 2016-12-31.

FIXED BEFORE ANY RETURN (decisions.md 111):
  signal       S_t = 4 r1 + 3 r2 + 2 r3 + r4 on the four most recent roll-correct NQ daily returns dated before
               session t (data/daily_bars.py); SHORT the window if S_t > 0, LONG if S_t <= 0.
  window       MNQ 09:30-16:00 ET, real return (drift kept), complete sessions only.
  test window  sessions 2017-01-01 to 2026-08-27.
  decision     (1) Sharpe of direction x r > 0; (2) mean beats always-long; (3) posterior > 0.
               Prior Normal(0.3, 0.3), an ASSUMPTION (the published 0.67 is close-to-close, continuous weights).
"""

from __future__ import annotations

import sys

TEST_START, TEST_END = "2017-01-01", "2026-08-27"
PRIOR_MEAN, PRIOR_SD = 0.3, 0.3
WEIGHTS = (4.0, 3.0, 2.0, 1.0)                    # r1 (most recent) .. r4


def direction(session_dates, daily_dates, daily_ret):
    """+1 (long) / -1 (short) per session from the four daily returns dated strictly before it; nan if < 4."""
    import numpy as np
    out = np.full(len(session_dates), np.nan)
    pos = np.searchsorted(daily_dates, session_dates, side="left")   # daily bars with date < session date
    for i, k in enumerate(pos):
        if k < 4:
            continue
        r = daily_ret[k - 4:k][::-1]                                 # r1 = most recent
        s = float(sum(w * x for w, x in zip(WEIGHTS, r)))
        out[i] = -1.0 if s > 0 else 1.0
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.z07")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    from futuresres.signals import z07_trial as zt
    return zt.injection() if a.inject else zt.run_trial()


if __name__ == "__main__":
    sys.exit(main())
