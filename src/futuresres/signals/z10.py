"""Z10 - gotobi: long USD/JPY (short 6J) from the 18:00 ET reopen to the 9:55 JST fix on gotobi days.
hypotheses.yaml Z10; decisions.md 122. Strict Z rule adapted to a standalone trade.

    python -m futuresres.signals.z10 --inject
    python -m futuresres.signals.z10 --run         # THE TRIAL

FIXED BEFORE ANY 2021-2026 RETURN (decisions.md 122): event = a JST business day Tue-Fri that is the 5th/10th/
15th/20th/25th/30th or the last business day before a weekend one (data/fx.is_gotobi); return = p955 / p_reopen - 1
(USD/JPY spot, data/fx.key_points), net of 1.0 bp; test 2021-01-01 to 2026-09-30. Prior on the net mean
Normal(+0.8 bp, 1.0 bp), an ASSUMPTION.
"""

from __future__ import annotations

import sys

TEST_START, TEST_END = "2021-01-01", "2026-09-30"
COST_BPS = 1.0
PRIOR_MEAN_BPS, PRIOR_SD_BPS = 0.8, 1.0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.z10")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    from futuresres.signals import z10_trial as zt
    return zt.injection() if a.inject else zt.run_trial()


if __name__ == "__main__":
    sys.exit(main())
