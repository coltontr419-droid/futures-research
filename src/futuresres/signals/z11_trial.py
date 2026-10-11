"""Z11's data, outcome injection, trial and decision. Called by `python -m futuresres.signals.z11`. decisions.md 127."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

from futuresres.data.fx_fix import daily_close, fix_points
from futuresres.signals.z11 import COST_BPS, PRIOR_MEAN_BPS, PRIOR_SD_BPS, TEST_END, TEST_START
from futuresres.signals.z_strict import T_CRIT

ROOT = Path(__file__).resolve().parents[3]
INJ = ROOT / "reports" / "z11_injection.json"
OUT = ROOT / "reports" / "z11_trial.json"
OUT_MD = ROOT / "reports" / "z11_trial.md"
Z_MARKET_TESTS = 11


def _month_ret(dc: pl.DataFrame) -> dict:
    d = dc.with_columns(pl.col("date").dt.strftime("%Y-%m").alias("ym")).sort("date")
    out = {}
    for (ym,), g in d.group_by(["ym"], maintain_order=True):
        c = g["close"].to_list()
        if len(c) >= 3:
            out[ym] = c[-2] / c[0] - 1
    return out


def _data():
    """Per month in the test window: the last weekday's signed fix-hour return and the 5 weekdays before it (placebo)."""
    us, de = _month_ret(daily_close("spxusd")), _month_ret(daily_close("grxeur"))
    fp = fix_points("eurusd").drop_nulls().filter(pl.col("date").dt.weekday() <= 5)
    fp = fp.with_columns(pl.col("date").dt.strftime("%Y-%m").alias("ym"), ((pl.col("p1600") / pl.col("p1500") - 1) * 1e4).alias("bps"))
    lo, hi = dt.date.fromisoformat(TEST_START), dt.date.fromisoformat(TEST_END)
    ev = []
    for (ym,), g in fp.sort("date").group_by(["ym"], maintain_order=True):
        g = g.sort("date")
        last = g["date"][-1]
        if not (lo <= last <= hi) or ym not in us or ym not in de:
            continue
        # the month's last weekday must actually be present (a missing final day would shift the event)
        exp_last = last
        nxt = last + dt.timedelta(days=1)
        while nxt.month == last.month:
            if nxt.weekday() < 5:
                exp_last = None; break
            nxt += dt.timedelta(days=1)
        if exp_last is None:
            continue
        rel = us[ym] - de[ym]
        s = 1.0 if rel > 0 else -1.0
        b = g["bps"].to_list()
        ev.append({"date": str(last), "rel": rel, "s": s, "bps": b[-1], "pre": b[-6:-1] if len(b) >= 6 else []})
    return ev


def _t(x):
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def injection(reps: int = 2000, seed: int = 127) -> int:
    ev = _data()
    noise = np.array([v for e in ev for v in e["pre"]])                 # fix-hour returns on non-month-end weekdays
    n = len(ev)
    rng = np.random.default_rng(seed)
    est = np.empty(reps); passes = 0
    for k in range(reps):
        x = rng.choice(noise - noise.mean(), size=n, replace=True) + PRIOR_MEAN_BPS
        est[k] = x.mean(); passes += _t(x) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"n_events": n, "sought_net_bps": PRIOR_MEAN_BPS, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - PRIOR_MEAN_BPS) <= 3 * sd / math.sqrt(reps) + 0.1)}
    INJ.write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial() -> int:
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    ev = _data()
    s = np.array([e["s"] for e in ev]); r = np.array([e["bps"] for e in ev]); rel = np.array([e["rel"] for e in ev])
    gross = s * r; net = gross - COST_BPS
    t = _t(net)
    pre = [np.array([e["s"] * v - COST_BPS for e in ev for v in ([e["pre"][k]] if len(e["pre"]) == 5 else [])]) for k in range(5)]
    pre_means = [float(p.mean()) for p in pre if len(p)]
    pct_pre = float((np.array(pre_means) < net.mean()).mean() * 100)
    rng = np.random.default_rng(1272)
    perm = np.array([(rng.permutation(s) * r - COST_BPS).mean() for _ in range(2000)])
    pct_perm = float((perm < net.mean()).mean() * 100)
    p0, p1 = 1 / PRIOR_SD_BPS ** 2, 1 / (net.std(ddof=1) ** 2 / len(net))
    post = (PRIOR_MEAN_BPS * p0 + net.mean() * p1) / (p0 + p1); post0 = (net.mean() * p1) / (p0 + p1)
    dates = np.array([e["date"] for e in ev])
    eras = {}
    for name, lo, hi in (("2013-19", "2013-01-01", "2019-12-31"), ("2020-26", "2020-01-01", "2026-12-31")):
        m = (dates >= lo) & (dates <= hi)
        eras[name] = {"events": int(m.sum()), "net_bps": float(net[m].mean()), "t": _t(net[m])}
    slope = float(np.polyfit(rel * 100, r, 1)[0])                         # bps per 1% of S&P - DAX
    c1, c2, c3 = t > T_CRIT, (pct_pre >= 95.0 and pct_perm >= 95.0), post > 0
    out = {"hypothesis": "Z11", "window": [ev[0]["date"], ev[-1]["date"]], "events": int(len(ev)),
           "gross_bps": float(gross.mean()), "net_bps": float(net.mean()), "sd_bps": float(r.std(ddof=1)), "t_net": t,
           "win_rate_net": float((net > 0).mean()), "slope_bps_per_pct": slope,
           "placebo_pre_days_pct": pct_pre, "pre_day_net_means": pre_means, "placebo_perm_pct": pct_perm,
           "posterior_bps": {"registered_prior": post, "zero_prior": post0}, "eras": eras,
           "conditions": {"t_gt_1.645": bool(c1), "placebo_ge_95": bool(c2), "posterior_gt_0": bool(c3)},
           "z_market_tests": Z_MARKET_TESTS, "decision": "CONFIRM" if (c1 and c2 and c3) else "REJECT", "injection": inj}
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n"); OUT_MD.write_text(render(out))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id="Z11", symbol="6E",
                           date_range=(out["window"][0], out["window"][1]), status="completed", sharpe=float(net.mean() / net.std(ddof=1)),
                           params={"statistic": "net mean per month-end, EUR/USD 15:00-16:00 London signed by S&P - DAX; strict rule",
                                   "net_bps": out["net_bps"], "t_net": t, "placebo_pre_days_pct": pct_pre,
                                   "placebo_perm_pct": pct_perm, "decision": out["decision"]},
                           note="provenance=native; source=external (Melvin & Prins 2015), tested 2013-2026 after its sample; strict rule. decisions.md 127."))
    print(OUT_MD.read_text()); print("logged", rec["trial_id"])
    return 0


def render(s: dict) -> str:
    c = s["conditions"]; i = s["injection"]
    rows = ["| period | events | net bps | t |", "|---|---|---|---|"]
    rows += [f"| {k} | {e['events']} | {e['net_bps']:+.2f} | {e['t']:+.2f} |" for k, e in s["eras"].items()]
    return "\n".join([
        "# Z11 — month-end FX hedge rebalancing at the London fix, EUR/USD (strict rule): the trial", "",
        f"**Decision: {s['decision']}.** {s['events']} month-ends, {s['window'][0]} → {s['window'][1]}.", "",
        f"- 15:00 → 16:00 London, signed by S&P − DAX: gross **{s['gross_bps']:+.2f} bps**, net {s['net_bps']:+.2f} (SD {s['sd_bps']:.1f}); "
        f"t **{s['t_net']:+.2f}** (needs > 1.645): {c['t_gt_1.645']}; net win rate {s['win_rate_net']:.0%}; slope {s['slope_bps_per_pct']:+.2f} bps per 1%.",
        f"- Placebos: the 5 weekdays before month-end **{s['placebo_pre_days_pct']:.0f}th** pct; signal permuted across months "
        f"**{s['placebo_perm_pct']:.1f}th** pct (both need ≥ 95): {c['placebo_ge_95']}.",
        f"- Posterior net mean {s['posterior_bps']['registered_prior']:+.2f} bps (zero prior {s['posterior_bps']['zero_prior']:+.2f}): {c['posterior_gt_0']}.",
        f"- Running count: {s['z_market_tests']} Z market-tests.", "", *rows, "",
        f"Outcome injection: {i['sought_net_bps']} bps planted, recovered {i['mean_estimate']:.2f} (SD {i['sd_estimate_bps']:.2f}); "
        f"power of the strict t at that size {i['power_strict_t']:.0%}.", ""])
