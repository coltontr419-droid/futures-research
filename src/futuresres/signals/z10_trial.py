"""Z10's data, outcome injection, trial and decision. Called by `python -m futuresres.signals.z10`. decisions.md 122."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

from futuresres.data.fx import is_gotobi, key_points
from futuresres.signals.z10 import COST_BPS, PRIOR_MEAN_BPS, PRIOR_SD_BPS, TEST_END, TEST_START
from futuresres.signals.z_strict import T_CRIT

ROOT = Path(__file__).resolve().parents[3]
INJ = ROOT / "reports" / "z10_injection.json"
OUT = ROOT / "reports" / "z10_trial.json"
OUT_MD = ROOT / "reports" / "z10_trial.md"
Z_MARKET_TESTS = 10


def _frame():
    kp = key_points().filter(pl.col("wd").is_between(2, 5))
    kp = kp.filter(pl.col("jd").is_between(dt.date.fromisoformat(TEST_START), dt.date.fromisoformat(TEST_END)))
    kp = kp.drop_nulls(["p955", "p_reopen"]).with_columns(((pl.col("p955") / pl.col("p_reopen") - 1) * 1e4).alias("bps"),
                                                          ((pl.col("p955") / pl.col("p300") - 1) * 1e4).alias("bps_paper"))
    days = kp["jd"].to_list()
    return kp.with_columns(pl.Series("gotobi", [is_gotobi(d) for d in days])), days


def _t(x):
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def injection(reps: int = 2000, seed: int = 122) -> int:
    """Plant the prior's net mean on gotobi days in bootstrap noise from non-gotobi days; recover it and measure
    the power of condition (1)."""
    kp, _ = _frame()
    other = kp.filter(~pl.col("gotobi"))["bps"].to_numpy(); n = int(kp["gotobi"].sum())
    rng = np.random.default_rng(seed)
    est = np.empty(reps); passes = 0
    for k in range(reps):
        x = rng.choice(other - other.mean(), size=n, replace=True) + PRIOR_MEAN_BPS
        est[k] = x.mean(); passes += _t(x) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"n_events": n, "sought_net_bps": PRIOR_MEAN_BPS, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps,
           "recovered": bool(abs(est.mean() - PRIOR_MEAN_BPS) <= 3 * sd / math.sqrt(reps) + 0.1)}
    INJ.write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial() -> int:
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    kp, days = _frame()
    g = kp.filter(pl.col("gotobi"))
    gross = g["bps"].to_numpy(); net = gross - COST_BPS
    t = _t(net)
    # placebo 1: the gotobi calendar shifted by k business days (k = 1..4, both directions)
    allb = kp["bps"].to_numpy() - COST_BPS; isg = kp["gotobi"].to_numpy()
    shifted = [float(allb[np.roll(isg, k)].mean()) for k in (-4, -3, -2, -1, 1, 2, 3, 4)]
    # placebo 2: random same-size sets of non-gotobi days
    rng = np.random.default_rng(1222)
    other = allb[~isg]
    rand = np.array([rng.choice(other, size=len(net), replace=False).mean() for _ in range(2000)])
    pct_rand = float((rand < net.mean()).mean() * 100)
    pct_shift = float((np.array(shifted) < net.mean()).mean() * 100)
    p0, p1 = 1 / PRIOR_SD_BPS ** 2, 1 / (net.std(ddof=1) ** 2 / len(net))
    post = (PRIOR_MEAN_BPS * p0 + net.mean() * p1) / (p0 + p1); post0 = (net.mean() * p1) / (p0 + p1)
    eras = {}
    for name, lo, hi in (("2021-23", "2021-01-01", "2023-12-31"), ("2024-26", "2024-01-01", "2026-12-31")):
        e = g.filter(pl.col("jd").is_between(dt.date.fromisoformat(lo), dt.date.fromisoformat(hi)))["bps"].to_numpy() - COST_BPS
        eras[name] = {"events": int(len(e)), "net_bps": float(e.mean()), "t": _t(e)}
    c1, c2, c3 = t > T_CRIT, (pct_rand >= 95.0 and pct_shift >= 95.0), post > 0
    out = {"hypothesis": "Z10", "window": [str(days[0]), str(days[-1])], "events": int(len(net)),
           "gross_bps": float(gross.mean()), "net_bps": float(net.mean()), "sd_bps": float(gross.std(ddof=1)), "t_net": t,
           "win_rate_net": float((net > 0).mean()), "other_days_gross_bps": float(kp.filter(~pl.col("gotobi"))["bps"].mean()),
           "paper_window_gross_bps": float(g["bps_paper"].drop_nulls().mean()),
           "placebo_random_pct": pct_rand, "placebo_shift_pct": pct_shift, "shifted_net_means": shifted,
           "posterior_bps": {"registered_prior": post, "zero_prior": post0}, "eras": eras,
           "conditions": {"t_gt_1.645": bool(c1), "placebo_ge_95": bool(c2), "posterior_gt_0": bool(c3)},
           "z_market_tests": Z_MARKET_TESTS, "decision": "CONFIRM" if (c1 and c2 and c3) else "REJECT", "injection": inj}
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n"); OUT_MD.write_text(render(out))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id="Z10", symbol="6J",
                           date_range=(out["window"][0], out["window"][1]), status="completed",
                           sharpe=float(net.mean() / net.std(ddof=1)),
                           params={"statistic": "net mean per gotobi event, 18:00 ET -> 9:55 JST, USD/JPY spot; strict rule",
                                   "net_bps": out["net_bps"], "t_net": t, "placebo_random_pct": pct_rand,
                                   "placebo_shift_pct": pct_shift, "decision": out["decision"]},
                           note="provenance=native; source=external (arXiv 2301.13204, 2018-2020), tested 2021-2026 after its sample; strict rule. decisions.md 122."))
    print(OUT_MD.read_text()); print("logged", rec["trial_id"])
    return 0


def render(s: dict) -> str:
    c = s["conditions"]; i = s["injection"]
    rows = ["| period | events | net bps | t |", "|---|---|---|---|"]
    rows += [f"| {k} | {e['events']} | {e['net_bps']:+.2f} | {e['t']:+.2f} |" for k, e in s["eras"].items()]
    return "\n".join([
        "# Z10 — gotobi: long USD/JPY into the Tokyo fix (strict rule): the trial", "",
        f"**Decision: {s['decision']}.** {s['events']} gotobi events, {s['window'][0]} → {s['window'][1]}.", "",
        f"- 18:00 ET → 9:55 JST: gross **{s['gross_bps']:+.2f} bps**, net {s['net_bps']:+.2f} (SD {s['sd_bps']:.1f}); "
        f"t **{s['t_net']:+.2f}** (needs > 1.645): {c['t_gt_1.645']}; net win rate {s['win_rate_net']:.0%}.",
        f"- Placebo: random non-gotobi sets **{s['placebo_random_pct']:.1f}th** pct; calendar shifted ±1–4 days "
        f"**{s['placebo_shift_pct']:.0f}th** pct (both need ≥ 95): {c['placebo_ge_95']}.",
        f"- Posterior net mean {s['posterior_bps']['registered_prior']:+.2f} bps (zero prior {s['posterior_bps']['zero_prior']:+.2f}): {c['posterior_gt_0']}.",
        f"- Non-gotobi days, same window: {s['other_days_gross_bps']:+.2f} bps gross. The paper's 03:00 JST window "
        f"(not tradable): {s['paper_window_gross_bps']:+.2f} bps gross.",
        f"- Running count: {s['z_market_tests']} Z market-tests.", "", *rows, "",
        f"Outcome injection: {i['sought_net_bps']} bp planted, recovered {i['mean_estimate']:.2f} (SD {i['sd_estimate_bps']:.2f}); "
        f"power of the strict t at that size {i['power_strict_t']:.0%}.", ""])
