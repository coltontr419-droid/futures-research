"""D02 - AUD rises into the Tokyo fix at month-end: long AUD/USD 09:25 -> 09:55 JST on the last weekday of the month.
Data-derived (D-series family 2). hypotheses.yaml D02; decisions.md 132-134. Validated ONCE on sealed 2018-2026 data.

    python -m futuresres.signals.d02 --inject
    python -m futuresres.signals.d02 --run         # THE TRIAL
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
INJ = ROOT / "reports" / "d02_injection.json"
OUT = ROOT / "reports" / "d02_trial.json"
OUT_MD = ROOT / "reports" / "d02_trial.md"
VAL = (dt.date(2018, 1, 1), dt.date(2026, 9, 30))
PAIR, COST = "audusd", 0.8
PRIOR_MEAN, PRIOR_SD = 0.64, 1.0
Z_D_TESTS = 14


def _series(win_label: str, before: bool, dayset: str):
    import futuresres.reporting.d2_discovery as d2
    from futuresres.data.fx_fix import quarter_marks
    win = [w for w in d2.windows() if w["pair"] == PAIR and w["label"].startswith(win_label) and w["before"] == before][0]
    days, r = d2.returns(win, quarter_marks(PAIR), *VAL)
    assert not days or min(days) >= VAL[0], "validation read discovery data"
    if dayset == "month-end":
        me = d2._last_weekdays(*VAL)
        m = np.array([d in me for d in days]); days = [d for d, k in zip(days, m) if k]; r = r[m]
    return days, r


def _t(x):
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def injection(reps: int = 2000, seed: int = 134) -> int:
    from futuresres.signals.z_strict import T_CRIT
    _, allr = _series("Tokyo 09:55 fix", True, "all weekdays")
    _, me = _series("Tokyo 09:55 fix", True, "month-end")
    noise = allr - allr.mean(); n = len(me)
    rng = np.random.default_rng(seed); est = np.empty(reps); passes = 0
    for k in range(reps):
        x = rng.choice(noise, size=n, replace=True) + PRIOR_MEAN
        est[k] = x.mean(); passes += _t(x) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"n_events": n, "sought_net_bps": PRIOR_MEAN, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - PRIOR_MEAN) <= 3 * sd / math.sqrt(reps) + 0.1)}
    INJ.write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial() -> int:
    import futuresres.reporting.d2_discovery as d2
    from futuresres.signals.z_strict import T_CRIT
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    days, r = _series("Tokyo 09:55 fix", True, "month-end")
    net = r - COST
    t = _t(net)
    others = {}
    for w in d2.windows():
        if w["pair"] != PAIR or (w["label"].startswith("Tokyo 09:55 fix") and w["before"]):
            continue
        _, x = _series(w["label"].rsplit(" ", 1)[0], w["before"], "month-end")
        if len(x) >= 30:
            others[w["label"]] = float((x - COST).mean())
    pct = float((np.array(list(others.values())) < net.mean()).mean() * 100) if others else float("nan")
    p0, p1 = 1 / PRIOR_SD ** 2, 1 / (net.std(ddof=1) ** 2 / len(net))
    post = (PRIOR_MEAN * p0 + net.mean() * p1) / (p0 + p1); post0 = net.mean() * p1 / (p0 + p1)
    yrs = np.array([d.year for d in days])
    eras = {lab: {"events": int(m.sum()), "net_bps": float(net[m].mean()), "t": _t(net[m])}
            for lab, m in (("2018-21", yrs <= 2021), ("2022-26", yrs >= 2022))}
    _, allr = _series("Tokyo 09:55 fix", True, "all weekdays")
    c1, c2, c3 = t > T_CRIT, pct >= 95.0, post > 0
    tier = "CONFIRM" if (c1 and c2 and c3) else ("WATCHLIST" if net.mean() > 0 else "REJECT")
    out = {"hypothesis": "D02", "window": [str(days[0]), str(days[-1])], "events": int(len(net)), "gross_bps": float(r.mean()),
           "net_bps": float(net.mean()), "sd_bps": float(r.std(ddof=1)), "t_net": t, "win_rate_net": float((net > 0).mean()),
           "placebo_other_windows_pct": pct, "other_windows_net": others, "all_weekdays_gross_bps": float(allr.mean()),
           "posterior_bps": {"registered_prior": post, "zero_prior": post0}, "eras": eras,
           "conditions": {"t_gt_1.645": bool(c1), "placebo_ge_95": bool(c2), "posterior_gt_0": bool(c3)},
           "z_d_market_tests": Z_D_TESTS, "decision": tier, "injection": inj}
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n")
    rows = ["| period | events | net bps | t |", "|---|---|---|---|"] + [f"| {k} | {e['events']} | {e['net_bps']:+.2f} | {e['t']:+.2f} |" for k, e in eras.items()]
    OUT_MD.write_text("\n".join([
        "# D02 — AUD rises into the Tokyo fix at month-end: the validation trial", "",
        f"**Decision: {tier}.** {len(net)} month-ends, {out['window'][0]} → {out['window'][1]} (sealed until registration).", "",
        f"- Long AUD/USD 09:25 → 09:55 JST: gross **{out['gross_bps']:+.2f} bps** (SD {out['sd_bps']:.1f}); net **{out['net_bps']:+.2f}**, "
        f"t **{t:+.2f}** (needs > 1.645): {c1}; net win rate {out['win_rate_net']:.0%}.",
        f"- Placebo: AUD/USD's other family-2 windows on month-ends — real at the **{pct:.0f}th** pct (needs ≥ 95): {c2}.",
        f"- Posterior net mean {post:+.2f} bps (zero prior {post0:+.2f}): {c3}. Same window on all weekdays: {out['all_weekdays_gross_bps']:+.2f} bps gross.",
        f"- Discovery (2010–17): +2.88 bps, t +3.25, n 88. Running count: {Z_D_TESTS} Z and D market-tests.", "", *rows, "",
        f"Outcome injection: {inj['sought_net_bps']} bp planted, recovered {inj['mean_estimate']:.2f} (SD {inj['sd_estimate_bps']:.2f}); "
        f"power of the strict t {inj['power_strict_t']:.0%}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id="D02", symbol="6A", date_range=(out["window"][0], out["window"][1]),
                           status="completed", sharpe=float(net.mean() / net.std(ddof=1)),
                           params={"statistic": "net mean, long AUD/USD 09:25-09:55 JST at month-end, sealed 2018-2026; strict rule + tiers",
                                   "net_bps": out["net_bps"], "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 2, decisions.md 132-134); validated once on sealed data."))
    print(OUT_MD.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d02")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    return injection() if a.inject else run_trial()


if __name__ == "__main__":
    sys.exit(main())
