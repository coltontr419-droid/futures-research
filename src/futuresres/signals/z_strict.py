"""The strict Z rule (decisions.md 119), adopted 2026-10-10 at the user's direction, before any further candidate.

A direction signal s (+1/-1 per session) on window returns r CONFIRMS for a market only if ALL hold:
  1. significance  it beats the plan's current always-long with one-sided t > 1.645 on the per-session difference
                   d = s*r - r (zero on long sessions, -2r on short ones);
  2. placebo       mean(d) exceeds the 95th percentile of the same statistic with s circularly shifted against r
                   (shifts of at least 20 sessions, every 5th);
  3. posterior     > 0 under the registered prior, reported beside the posterior under a zero-mean prior;
  4. count         reported against the running number of Z market-tests and the chance passes expected at 5%.

    python -m futuresres.signals.z_strict          # re-reads Z06-Z08 under this rule (descriptive; no trial)

    z_strict.power(...)                            # pre-registration screen: power at the published effect size
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "z_strict_review.json"
T_CRIT, PLACEBO_PCT, MIN_SHIFT, SHIFT_STEP = 1.645, 95.0, 20, 5


def strict(r: np.ndarray, s: np.ndarray, prior_mean: float, prior_sd: float) -> dict:
    d = s * r - r
    n = len(d)
    t = float(d.mean() / (d.std(ddof=1) / math.sqrt(n)))
    shifts = range(MIN_SHIFT, n - MIN_SHIFT, SHIFT_STEP)
    null = np.array([(np.roll(s, k) * r - r).mean() for k in shifts])
    pct = float((null < d.mean()).mean() * 100)
    x = s * r
    sh = float(x.mean() / x.std(ddof=1) * math.sqrt(252))
    se = 1.0 / math.sqrt(n / 252)                      # SD of an annualised Sharpe estimate: 1 / sqrt(years)
    p0, p1 = 1 / prior_sd ** 2, 1 / se ** 2
    post = (prior_mean * p0 + sh * p1) / (p0 + p1)
    post0 = (sh * p1) / (p0 + p1)
    return {"sessions": n, "t_beats_long": t, "placebo_percentile": pct, "sharpe_signal": sh,
            "posterior_registered_prior": post, "posterior_zero_prior": post0,
            "conditions": {"t_gt_1.645": t > T_CRIT, "placebo_ge_95": pct >= PLACEBO_PCT, "posterior_gt_0": post > 0},
            "strict_confirm": bool(t > T_CRIT and pct >= PLACEBO_PCT and post > 0)}


def power(short_mean_bps: float, short_share: float, long_mean_bps: float, sd_bps: float, n: int,
          reps: int = 4000, seed: int = 0) -> dict:
    """Screen BEFORE registering (decisions.md 121): the strict rule's chance of passing if the published effect is
    exactly right. A short-signal share p of sessions with mean short_mean_bps, the rest long_mean_bps, daily SD
    sd_bps, n sessions; condition (1) only (t > 1.645 on d = s*r - r) - the placebo and posterior can only lower it."""
    rng = np.random.default_rng(seed)
    passes = 0; ts = []
    for _ in range(reps):
        s = np.where(rng.random(n) < short_share, -1.0, 1.0)
        r = rng.standard_normal(n) * sd_bps + np.where(s < 0, short_mean_bps, long_mean_bps)
        d = s * r - r
        tv = d.mean() / (d.std(ddof=1) / math.sqrt(n)); ts.append(tv); passes += tv > T_CRIT
    return {"expected_t": float(np.mean(ts)), "power": passes / reps}


def review() -> dict:
    out = {}
    from futuresres.signals import z06_trial as z6, z07_trial as z7, z08_trial as z8
    from futuresres.signals.z06 import PRIOR_MEAN as P6, PRIOR_SD as S6
    from futuresres.signals.z07 import PRIOR_MEAN as P7, PRIOR_SD as S7
    from futuresres.signals.z08 import PRIOR_MEAN as P8, PRIOR_SD as S8
    for prod in ("MNQ", "MGC"):
        d, r, s = z6._data(prod); out[f"Z06 {prod}"] = strict(r, s, P6, S6)
    d, r, s, _ = z7._data(); out["Z07 MNQ"] = strict(r, s, P7, S7)
    for prod in ("MCL", "MGC"):
        d, r, s = z8._data(prod); out[f"Z08 {prod}"] = strict(r, s, P8, S8)
    # the running count: Z market-tests so far (Z02 MES, Z04 MES, Z05 MGC, Z06 x2, Z07, Z08 x2) = 8
    out["running_count"] = {"z_market_tests": 8, "expected_chance_passes_at_5pct": 0.4}
    return out


def main(argv=None) -> int:
    r = review()
    OUT.write_text(json.dumps(r, indent=1) + "\n")
    for k, v in r.items():
        if k == "running_count":
            print(k, v); continue
        print(f"{k:9}: t(beats long) {v['t_beats_long']:+.2f} | placebo pct {v['placebo_percentile']:5.1f} | Sharpe {v['sharpe_signal']:+.2f} | "
              f"posterior {v['posterior_registered_prior']:+.2f} (zero prior {v['posterior_zero_prior']:+.2f}) | STRICT {'CONFIRM' if v['strict_confirm'] else 'no'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
