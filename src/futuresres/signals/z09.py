"""Z09 - index roll selling: the crude plan shorts on the GSCI roll days (5th-9th trading days), long otherwise.
hypotheses.yaml Z09; decisions.md 120. Decided by the STRICT Z rule (signals/z_strict.py, decisions.md 119).

    python -m futuresres.signals.z09 --inject
    python -m futuresres.signals.z09 --run         # THE TRIAL

SOURCE: Mou (2011), front-running the Goldman roll; sample 2000 to March 2010 (published as a spread).
FIXED BEFORE ANY RETURN (decisions.md 120): s = -1 on the 5th-9th trading days of each month (the owned daily CL
calendar), +1 otherwise; r = the held front's session return (data/daily_bars.py, crossover sessions dropped);
2010-06-01 to 2026-08-27. Prior Normal(0.2, 0.3), an ASSUMPTION.
"""

from __future__ import annotations

import sys

TEST_START, TEST_END = "2010-06-01", "2026-08-27"
PRIOR_MEAN, PRIOR_SD = 0.2, 0.3
ROLL_DAYS = (5, 6, 7, 8, 9)


def roll_sign(dates):
    """-1 on trading days 5-9 of each month (counted on the series' own calendar), +1 otherwise."""
    import numpy as np
    ym = dates.astype("datetime64[M]")
    s = np.ones(len(dates))
    for m in np.unique(ym):
        idx = np.flatnonzero(ym == m)
        s[idx[[k - 1 for k in ROLL_DAYS if k - 1 < len(idx)]]] = -1.0
    return s


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.z09")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    from futuresres.signals import z09_trial as zt
    return zt.injection() if a.inject else zt.run_trial()


if __name__ == "__main__":
    sys.exit(main())
