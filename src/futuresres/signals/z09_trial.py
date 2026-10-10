"""Z09's data, outcome injection, trial and decision (strict Z rule). Called by `python -m futuresres.signals.z09`.
decisions.md 120."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from futuresres.signals.z09 import PRIOR_MEAN, PRIOR_SD, ROLL_DAYS, TEST_END, TEST_START, roll_sign
from futuresres.signals.z_strict import T_CRIT, strict

ROOT = Path(__file__).resolve().parents[3]
INJ = ROOT / "reports" / "z09_injection.json"
OUT = ROOT / "reports" / "z09_trial.json"
OUT_MD = ROOT / "reports" / "z09_trial.md"
Z_MARKET_TESTS = 9


def _data():
    from futuresres.data.daily_bars import load_market
    mk = load_market("CL")
    d_all = mk.dates.astype("datetime64[D]")
    s_all = roll_sign(d_all)                                   # trading-day count on the full calendar, before filtering
    m = (d_all >= np.datetime64(TEST_START)) & (d_all <= np.datetime64(TEST_END)) & ~mk.crossover & (mk.ret != 0)
    ym = d_all.astype("datetime64[M]")
    nth = np.zeros(len(d_all), int)
    for mo in np.unique(ym):
        idx = np.flatnonzero(ym == mo); nth[idx] = np.arange(1, len(idx) + 1)
    return d_all[m], mk.ret[m], s_all[m], nth[m]


def injection(reps: int = 2000, seed: int = 120) -> int:
    """Plant an edge of the prior's size on the roll days (crude lower there), bootstrap the noise, and measure both
    the recovered Sharpe and the strict rule's power (t > 1.645) at that size."""
    d, r, s, _ = _data()
    rng = np.random.default_rng(seed)
    x0 = s * r; n = len(r)
    mu = PRIOR_MEAN / math.sqrt(252) * float(x0.std())
    est = np.empty(reps); passes = 0
    base = r - r.mean()
    for k in range(reps):
        e = rng.choice(base, size=n, replace=True) + s * mu          # roll days lower, others higher: E[s*e] = mu
        x = s * e
        est[k] = x.mean() / x.std(ddof=1) * math.sqrt(252)
        dd = x - e
        passes += (dd.mean() / (dd.std(ddof=1) / math.sqrt(n))) > T_CRIT
    res = {"n_sessions": n, "sought_sharpe": PRIOR_MEAN, "mean_estimate": float(est.mean()), "sd_estimate": float(est.std(ddof=1)),
           "power_sharpe_gt_0": float((est > 0).mean()), "power_strict_t": passes / reps,
           "recovered": bool(abs(est.mean() - PRIOR_MEAN) <= 3 * est.std(ddof=1) / math.sqrt(reps) + 0.05)}
    INJ.write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial() -> int:
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    d, r, s, nth = _data()
    v = strict(r, s, PRIOR_MEAN, PRIOR_SD)
    roll, other = r[s < 0], r[s > 0]
    eras = {}
    for name, lo, hi in (("2010-15", "2010-01-01", "2015-12-31"), ("2016-20", "2016-01-01", "2020-12-31"), ("2021-26", "2021-01-01", "2026-12-31")):
        mm = (d >= np.datetime64(lo)) & (d <= np.datetime64(hi))
        eras[name] = {"sessions": int(mm.sum()), "roll_bps": float(r[mm & (s < 0)].mean() * 1e4),
                      "other_bps": float(r[mm & (s > 0)].mean() * 1e4), "strict_t": strict(r[mm], s[mm], PRIOR_MEAN, PRIOR_SD)["t_beats_long"]}
    by_day = {int(k): float(r[nth == k].mean() * 1e4) for k in ROLL_DAYS}
    out = {"hypothesis": "Z09", "window": [str(d[0]), str(d[-1])], **v,
           "roll_day_bps": float(roll.mean() * 1e4), "other_day_bps": float(other.mean() * 1e4),
           "roll_sessions": int((s < 0).sum()), "eras": eras, "bps_by_trading_day": by_day,
           "z_market_tests": Z_MARKET_TESTS, "expected_chance_passes_at_5pct": round(0.05 * Z_MARKET_TESTS, 2),
           "decision": "CONFIRM" if v["strict_confirm"] else "REJECT", "injection": inj}
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n"); OUT_MD.write_text(render(out))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id="Z09", symbol="MCL",
                           date_range=(out["window"][0], out["window"][1]), status="completed", sharpe=v["sharpe_signal"] / math.sqrt(252),
                           params={"statistic": "strict Z rule: t of per-session advantage over always-long; roll-calendar placebo",
                                   "t_beats_long": v["t_beats_long"], "placebo_percentile": v["placebo_percentile"],
                                   "roll_day_bps": out["roll_day_bps"], "other_day_bps": out["other_day_bps"], "decision": out["decision"]},
                           note="provenance=native; source=external (Mou 2011), tested 2010-2026 after the paper's sample; strict rule. decisions.md 120."))
    print(OUT_MD.read_text()); print("logged", rec["trial_id"])
    return 0


def render(s: dict) -> str:
    c = s["conditions"]; i = s["injection"]
    rows = ["| period | sessions | roll-day bps | other-day bps | t (beats long) |", "|---|---|---|---|---|"]
    rows += [f"| {k} | {e['sessions']} | {e['roll_bps']:+.2f} | {e['other_bps']:+.2f} | {e['strict_t']:+.2f} |" for k, e in s["eras"].items()]
    return "\n".join([
        "# Z09 — short crude on the index roll days: the trial (strict rule)", "",
        f"**Decision: {s['decision']}.** {s['sessions']} sessions, {s['window'][0]} → {s['window'][1]}; {s['roll_sessions']} roll-day sessions.", "",
        f"- Crude on roll days (5th–9th) **{s['roll_day_bps']:+.2f} bps** vs other days {s['other_day_bps']:+.2f} bps.",
        f"- Advantage over always-long: t **{s['t_beats_long']:+.2f}** (needs > 1.645): {c['t_gt_1.645']}.",
        f"- Placebo (roll calendar shifted): real at the **{s['placebo_percentile']:.1f}th** percentile (needs ≥ 95): {c['placebo_ge_95']}.",
        f"- Posterior {s['posterior_registered_prior']:+.2f} (zero-mean prior {s['posterior_zero_prior']:+.2f}): {c['posterior_gt_0']}.",
        f"- Running count: {s['z_market_tests']} Z market-tests; {s['expected_chance_passes_at_5pct']} chance passes expected at 5%.", "",
        "By trading day (bps): " + ", ".join(f"day {k} {v:+.1f}" for k, v in s["bps_by_trading_day"].items()), "",
        *rows, "",
        f"Outcome injection: {i['sought_sharpe']} planted, recovered {i['mean_estimate']:.2f} (SD {i['sd_estimate']:.2f}); "
        f"power at that size: P(Sharpe > 0) {i['power_sharpe_gt_0']:.0%}, P(strict t) {i['power_strict_t']:.0%}.", ""])
