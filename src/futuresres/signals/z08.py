"""Z08 - commercial hedgers' weekly flow (CFTC COT) sets the crude and gold staking brackets' direction.
hypotheses.yaml Z08; decisions.md 117.

    python -m futuresres.signals.z08 --inject
    python -m futuresres.signals.z08 --run         # THE TRIAL
    python -m futuresres.signals.z08 --direction   # gold's direction for the coming week (downloads this year's COT)

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


def direction() -> int:
    """Refresh this year's CFTC legacy file and print gold's side for the sessions of the week after the latest
    release (decisions.md 117: confirmed for MGC only; crude and MNQ stay long)."""
    import datetime as dt
    import urllib.request
    import numpy as np
    from futuresres.data.cot import COT_DIR, commercial_flow
    y = dt.date.today().year
    COT_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(f"https://www.cftc.gov/files/dea/history/deacot{y}.zip", headers={"User-Agent": "Mozilla/5.0"})
    (COT_DIR / f"deacot{y}.zip").write_bytes(urllib.request.urlopen(req, timeout=120).read())
    tu, q = commercial_flow("GC", years=range(y - 1, y + 1))
    k = int(np.flatnonzero(np.isfinite(q))[-1])
    t0 = tu[k]
    side = "long" if q[k] >= 0 else "short"
    print(f"Latest COT report: positions as of {t0} (released {t0 + np.timedelta64(3, 'D')}). Gold commercials' net change "
          f"{q[k] * 100:+.2f}% of open interest -> {side.upper()} gold for the sessions dated "
          f"{t0 + np.timedelta64(6, 'D')} to {t0 + np.timedelta64(10, 'D')}.")
    print(f"Use: python -m futuresres.reporting.a06_playbook eval|funded --product MGC --side {side} ...")
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.z08")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    g.add_argument("--direction", action="store_true")
    a = ap.parse_args(argv)
    if a.direction:
        return direction()
    from futuresres.signals import z08_trial as zt
    return zt.injection() if a.inject else zt.run_trial()


if __name__ == "__main__":
    sys.exit(main())
