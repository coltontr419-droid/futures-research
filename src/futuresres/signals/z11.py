"""Z11 - month-end FX hedge rebalancing at the London 4 p.m. fix: EUR/USD (6E) 15:00 -> 16:00 London on the month's last
weekday, long if the S&P 500 outperformed the DAX month to date, short otherwise. hypotheses.yaml Z11; decisions.md 127.

    python -m futuresres.signals.z11 --inject
    python -m futuresres.signals.z11 --run         # THE TRIAL

FIXED BEFORE ANY 2013-2026 RETURN (decisions.md 127): event = last weekday (Mon-Fri) of each month; signal = sign of
(S&P 500 - DAX) return from the first to the second-last New York trading day of the month (close to close, data/fx_fix
daily closes); return = p1600 / p1500 - 1 (EUR/USD, London time), net of 1.0 bp. Test 2013-01-01 to 2026-09-30.
Prior on the net mean Normal(+3 bps, 3 bps), an ASSUMPTION.
"""

from __future__ import annotations

import sys

TEST_START, TEST_END = "2013-01-01", "2026-09-30"
COST_BPS = 1.0
PRIOR_MEAN_BPS, PRIOR_SD_BPS = 3.0, 3.0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.z11")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    from futuresres.signals import z11_trial as zt
    return zt.injection() if a.inject else zt.run_trial()


if __name__ == "__main__":
    sys.exit(main())
