"""Z04 - the macro-announcement premium: long MES on FOMC, jobs-report and CPI days. hypotheses.yaml Z04;
decisions.md 96.

    python -m futuresres.signals.z04 --inject     # outcome injection (real noise, alignment destroyed)
    python -m futuresres.signals.z04 --run        # THE TRIAL

SOURCE: Savor & Wilson (2013, JFQA; 1958-2009): US stocks earn 11.4 bps on days of scheduled inflation,
employment and FOMC announcements against 1.1 bps on other days. Persistence: Ai, Bansal & Guo (2023 NBER,
1961-2023: 10.68 vs 0.93 bps); the FOMC part was low in 2016-2019 (Kurov, Wolfe & Gilbert 2021). A RISK
PREMIUM - compensation for bearing macro risk - not a flow.

FIXED BEFORE ANY RETURN (decisions.md 96):
  event days   FOMC decision days, Employment Situation (NFP) and CPI release days, 2010-2026 - the
               calendar in reports/z_macro_calendar.json (sources there). PPI is not included.
  position     long ES/MES on bar D for each event date D: the UTC-day bar runs 20:00 ET on D-1 to 20:00
               ET on D, so it holds the overnight run-up to an 08:30 release and a 14:00 FOMC decision;
               the account exits at 16:55 ET (the bar's tail is the approximation, decisions.md 74).
               The calendar is published in advance: no look-ahead.
  test window  2010-01-01 to 2026-09-11, after the original sample (ends 2009). NOT wholly independent:
               Ai, Bansal & Guo extended the evidence to 2023.
  decision     CONFIRM only if all three hold: (1) the paper's claim - mean ES return on event days >
               mean on other days (one-sided, Welch t > 1.645); (2) the strategy's net Sharpe > 0; (3) the
               Tradeify EV at the POSTERIOR Sharpe is > 0 with 1 MES. Prior Normal(0.25, 0.35): the
               published annual ~0.5 for an event-only strategy, halved for decay.
  cost         $3.07 per MES round trip per event day (X01).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
CAL = ROOT / "reports" / "z_macro_calendar.json"
TEST_START = "2010-01-01"
PRIOR_MEAN, PRIOR_SD = 0.25, 0.35
MES_MULT, MES_RT = 5.0, 3.07


def event_days() -> np.ndarray:
    c = json.loads(CAL.read_text())
    return np.unique(np.array(c["FOMC"] + c["NFP"] + c["CPI"], dtype="datetime64[D]"))


def weights(dates: np.ndarray) -> np.ndarray:
    """1 on bars dated on an event day, else 0. Positions only - no return is built here."""
    return np.isin(dates, event_days()).astype(float)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.z04")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    from futuresres.signals import z04_trial as zt
    return zt.injection() if a.inject else zt.run_trial()


if __name__ == "__main__":
    sys.exit(main())
