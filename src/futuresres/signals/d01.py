"""D01 - silver falls into the London fix: short silver (SI) 11:00 -> 12:00 UTC every weekday. Data-derived (D-series).
hypotheses.yaml D01; decisions.md 129-130. Validated ONCE on the sealed 2018-2026 window under the strict rule.

    python -m futuresres.signals.d01 --inject
    python -m futuresres.signals.d01 --run         # THE TRIAL
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
INJ = ROOT / "reports" / "d01_injection.json"
OUT = ROOT / "reports" / "d01_trial.json"
OUT_MD = ROOT / "reports" / "d01_trial.md"
START = dt.datetime(2018, 1, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
HOUR, COST, COST_SENS = 11, 1.5, 2.0
PRIOR_MEAN, PRIOR_SD = 1.3, 1.5
Z_D_TESTS = 13


def _returns() -> pl.DataFrame:
    from futuresres.reporting.d_discovery import hourly_returns
    r = hourly_returns("xagusd", start=START, end=END)
    assert r["start"].min() >= START, "validation read discovery data"
    return r


def _t(x):
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def injection(reps: int = 2000, seed: int = 130) -> int:
    from futuresres.signals.z_strict import T_CRIT
    r = _returns()
    other = r.filter(pl.col("hour") != HOUR)["bps"].to_numpy()
    n = r.filter(pl.col("hour") == HOUR).height
    rng = np.random.default_rng(seed)
    est = np.empty(reps); passes = 0
    for k in range(reps):
        x = rng.choice(other - other.mean(), size=n, replace=True) + PRIOR_MEAN
        est[k] = x.mean(); passes += _t(x) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"n_events": n, "sought_net_bps": PRIOR_MEAN, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - PRIOR_MEAN) <= 3 * sd / math.sqrt(reps) + 0.1)}
    INJ.write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial() -> int:
    from futuresres.signals.z_strict import T_CRIT
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    r = _returns()
    x = -r.filter(pl.col("hour") == HOUR)["bps"].to_numpy()          # the short's gross return
    net, net2 = x - COST, x - COST_SENS
    t, t2 = _t(net), _t(net2)
    others = {h: float((-r.filter(pl.col("hour") == h)["bps"].to_numpy() - COST).mean()) for h in range(24) if h != HOUR
              and r.filter(pl.col("hour") == h).height >= 30}
    pct = float((np.array(list(others.values())) < net.mean()).mean() * 100)
    p0, p1 = 1 / PRIOR_SD ** 2, 1 / (net.std(ddof=1) ** 2 / len(net))
    post = (PRIOR_MEAN * p0 + net.mean() * p1) / (p0 + p1); post0 = net.mean() * p1 / (p0 + p1)
    st = r.filter(pl.col("hour") == HOUR)["start"].to_list()
    yrs = np.array([s.year for s in st])
    eras = {lab: {"events": int(m.sum()), "net_bps": float(net[m].mean()), "t": _t(net[m])}
            for lab, m in (("2018-21", yrs <= 2021), ("2022-26", yrs >= 2022))}
    c1, c2, c3 = t > T_CRIT, pct >= 95.0, post > 0
    out = {"hypothesis": "D01", "window": [str(st[0].date()), str(st[-1].date())], "events": int(len(net)),
           "gross_short_bps": float(x.mean()), "net_bps": float(net.mean()), "sd_bps": float(x.std(ddof=1)), "t_net": t,
           "net_bps_at_2bp": float(net2.mean()), "t_net_at_2bp": t2, "win_rate_net": float((net > 0).mean()),
           "placebo_other_hours_pct": pct, "other_hours_net_means": others,
           "posterior_bps": {"registered_prior": post, "zero_prior": post0}, "eras": eras,
           "conditions": {"t_gt_1.645": bool(c1), "placebo_ge_95": bool(c2), "posterior_gt_0": bool(c3)},
           "z_d_market_tests": Z_D_TESTS, "decision": "CONFIRM" if (c1 and c2 and c3) else "REJECT", "injection": inj}
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n")
    rows = ["| period | events | net bps | t |", "|---|---|---|---|"] + [f"| {k} | {e['events']} | {e['net_bps']:+.2f} | {e['t']:+.2f} |" for k, e in eras.items()]
    OUT_MD.write_text("\n".join([
        "# D01 — silver falls into the London fix (strict rule): the validation trial", "",
        f"**Decision: {out['decision']}.** {out['events']} weekdays, {out['window'][0]} → {out['window'][1]} (sealed until registration).", "",
        f"- Short 11:00 → 12:00 UTC: gross **{out['gross_short_bps']:+.2f} bps** (SD {out['sd_bps']:.1f}); net at 1.5 bp **{out['net_bps']:+.2f}**, "
        f"t **{t:+.2f}** (needs > 1.645): {c1}; at 2.0 bp {out['net_bps_at_2bp']:+.2f} (t {t2:+.2f}); net win rate {out['win_rate_net']:.0%}.",
        f"- Placebo: the same short in silver's other hours — real at the **{pct:.0f}th** pct (needs ≥ 95): {c2}.",
        f"- Posterior net mean {post:+.2f} bps (zero prior {post0:+.2f}): {c3}.",
        f"- Running count: {Z_D_TESTS} Z and D market-tests. Discovery (2010–17): −5.53 bps, t −7.27.", "", *rows, "",
        f"Outcome injection: {inj['sought_net_bps']} bps planted, recovered {inj['mean_estimate']:.2f} (SD {inj['sd_estimate_bps']:.2f}); "
        f"power of the strict t {inj['power_strict_t']:.0%}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id="D01", symbol="SI", date_range=(out["window"][0], out["window"][1]),
                           status="completed", sharpe=float(net.mean() / net.std(ddof=1)),
                           params={"statistic": "net mean of the 11:00-12:00 UTC silver short, sealed 2018-2026; strict rule",
                                   "net_bps": out["net_bps"], "t_net": t, "placebo_pct": pct, "decision": out["decision"]},
                           note="provenance=native; source=data-derived (D-series discovery 2010-2017, decisions.md 129-130); validated once on sealed data."))
    print(OUT_MD.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d01")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    return injection() if a.inject else run_trial()


if __name__ == "__main__":
    sys.exit(main())
