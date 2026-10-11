"""Z12 - EUR/USD short in European hours (07:00 London -> 08:00 New York), long in US hours (08:00 -> 16:00 New York),
every weekday. hypotheses.yaml Z12; decisions.md 128. Strict Z rule.

    python -m futuresres.signals.z12 --inject
    python -m futuresres.signals.z12 --run         # THE TRIAL

SOURCE: Breedon & Ranaldo (2013, JMCB), EBS 1997-2007: currencies depreciate in their own trading hours; for EUR/USD the
morning short and afternoon long earned after-cost Sharpe ratios of 1.3 and 0.9. FIXED BEFORE ANY RETURN (decisions.md 128):
the two legs above, each net of 0.8 bp; daily P&L = -r_morning + r_afternoon - 1.6 bps; 2010-01-04 to 2026-09-30;
prior annual net Sharpe Normal(0.6, 0.4), an ASSUMPTION.
"""

from __future__ import annotations

import sys

TEST_START, TEST_END = "2010-01-04", "2026-09-30"
LEG_COST_BPS = 0.8
PRIOR_SHARPE, PRIOR_SD = 0.6, 0.4


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.z12")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    from futuresres.signals import z12_trial as zt
    return zt.injection() if a.inject else zt.run_trial()


if __name__ == "__main__":
    sys.exit(main())
