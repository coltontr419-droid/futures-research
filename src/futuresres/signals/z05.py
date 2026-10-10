"""Z05 - gold: long overnight, short during the New York day session (MGC). hypotheses.yaml Z05; decisions.md 99.

    python -m futuresres.signals.z05 --inject
    python -m futuresres.signals.z05 --run         # THE TRIAL

SOURCE: Blose, Gondhalekar & Kort, "Overnight versus day returns in gold and gold related assets", Journal
of Economics and Finance (2018): in the COMEX gold front futures contract (and London spot, miners, gold
funds and ETFs), overnight returns are significantly positive and day returns significantly negative, in
rising and falling markets; economically important after costs. Sample 1985-2012 (per a follow-up retest).
The paper's tables could not be read (publisher blocks automated access), so its MAGNITUDES are unknown
here; the specification follows its stated claim and the prior is labelled an assumption.

FIXED BEFORE ANY RETURN (decisions.md 99):
  sessions     the COMEX day session 08:20-13:30 ET; overnight 13:30 ET to the next 08:20 ET.
  position     long 18:00-08:20 ET, SHORT 08:20-13:30 ET, long 13:30-16:55 ET, flat 16:55-18:00 (the account's
               rule); never long and short at once. 1 MGC; three round trips a day at $3.32.
  data         MGC 1-minute bars (data/continuous), complete sessions only (decisions.md 67's rule).
  test window  2013-01-01 to 2026-08-27, after the paper's sample.
  decision     CONFIRM only if all hold: (1) mean(overnight) - mean(day) > 0 with Welch t > 1.645, AND
               overnight mean > 0 AND day mean < 0 (the published signs); (2) the strategy's net Sharpe > 0;
               (3) the Tradeify EV at the posterior Sharpe > 0 with 1 MGC. Prior Normal(0.25, 0.35) - an
               ASSUMPTION (the published size was not readable), the same prior as Z04.
"""

from __future__ import annotations

import sys

M_0820, M_1330, M_1655 = 860, 1170, 1375          # minutes after 18:00 ET
TEST_START = "2013-01-01"
PRIOR_MEAN, PRIOR_SD = 0.25, 0.35
MGC_RT = 3.32
ROUND_TRIPS = 3


def position_profile():
    """+1 / -1 by minute of the session: long to 08:20, short to 13:30, long to 16:55. Positions only."""
    import numpy as np
    pos = np.ones(M_1655)
    pos[M_0820:M_1330] = -1.0
    return pos


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.z05")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    from futuresres.signals import z05_trial as zt
    return zt.injection() if a.inject else zt.run_trial()


if __name__ == "__main__":
    sys.exit(main())
