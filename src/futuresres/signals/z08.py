"""Z08 - commercial hedgers' weekly flow (CFTC COT) sets the crude and gold staking brackets' direction.
hypotheses.yaml Z08; decisions.md 117.

    python -m futuresres.signals.z08 --inject
    python -m futuresres.signals.z08 --run         # THE TRIAL

SOURCE: Kang, Rouwenhorst & Tang (2020, JF 75(1)): prices rise after hedgers buy, fall after they sell; 1994-2014.

FIXED BEFORE ANY POST-2014 RETURN (decisions.md 117):
  signal       Q = weekly change in commercials' net long / previous open interest (data/cot.py); the five sessions of
               the week after the Friday release take sign(Q).
  windows      crude: the full session, roll-correct daily CL bars (data/daily_bars.py, crossover sessions dropped);
               gold: London 03:00-11:30 ET, MGC 1-minute real window returns (signals/z06_trial.window_returns).
  test window  2015-01-01 to 2026-08-27.
  decision     per product: (1) Sharpe of sign x r > 0; (2) mean beats always-long; (3) posterior > 0.
               Prior Normal(0.3, 0.3), an ASSUMPTION.
"""

from __future__ import annotations

import sys

TEST_START, TEST_END = "2015-01-01", "2026-08-27"
PRIOR_MEAN, PRIOR_SD = 0.3, 0.3
PRODUCTS = {"MCL": "CL", "MGC": "GC"}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.z08")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    from futuresres.signals import z08_trial as zt
    return zt.injection() if a.inject else zt.run_trial()


if __name__ == "__main__":
    sys.exit(main())
