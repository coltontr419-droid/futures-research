"""Z12's data, outcome injection, trial and decision. Called by `python -m futuresres.signals.z12`. decisions.md 128."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from futuresres.data.fx_fix import hourly_utc
from futuresres.signals.z12 import LEG_COST_BPS, PRIOR_SD, PRIOR_SHARPE, TEST_END, TEST_START
from futuresres.signals.z_strict import T_CRIT

ROOT = Path(__file__).resolve().parents[3]
INJ = ROOT / "reports" / "z12_injection.json"
OUT = ROOT / "reports" / "z12_trial.json"
OUT_MD = ROOT / "reports" / "z12_trial.md"
Z_MARKET_TESTS = 12
LDN, NY, UTC = ZoneInfo("Europe/London"), ZoneInfo("America/New_York"), dt.timezone.utc


def _prices() -> dict:
    h = hourly_utc("eurusd")
    return {u.replace(tzinfo=UTC): c for u, c in zip(h["utc"].to_list(), h["c"].to_list())}


def _schedule(day: dt.date, shift_h: int = 0):
    t1 = dt.datetime.combine(day, dt.time(7, 0), LDN).astimezone(UTC)
    t2 = dt.datetime.combine(day, dt.time(8, 0), NY).astimezone(UTC)
    t3 = dt.datetime.combine(day, dt.time(16, 0), NY).astimezone(UTC)
    s = dt.timedelta(hours=shift_h)
    return t1 + s, t2 + s, t3 + s


def _days():
    d, end = dt.date.fromisoformat(TEST_START), dt.date.fromisoformat(TEST_END)
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def legs(px: dict, shift_h: int = 0):
    """(dates, morning return bps, afternoon return bps) for every weekday with all three prices."""
    D, M, A = [], [], []
    for day in _days():
        t1, t2, t3 = _schedule(day, shift_h)
        if t1 in px and t2 in px and t3 in px:
            D.append(day); M.append((px[t2] / px[t1] - 1) * 1e4); A.append((px[t3] / px[t2] - 1) * 1e4)
    return np.array(D), np.array(M), np.array(A)


def _sharpe(x) -> float:
    return float(x.mean() / x.std(ddof=1) * math.sqrt(252))


def injection(reps: int = 2000, seed: int = 128) -> int:
    px = _prices()
    d, m, a = legs(px)
    base = (-m + a) - (-m + a).mean() - 2 * LEG_COST_BPS
    mu = PRIOR_SHARPE / math.sqrt(252) * float(base.std()) + 2 * LEG_COST_BPS      # gross drift giving the prior's NET Sharpe
    rng = np.random.default_rng(seed)
    est = np.empty(reps); passes = 0
    for k in range(reps):
        x = rng.choice(base, size=len(base), replace=True) + mu
        est[k] = _sharpe(x); passes += (x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) > T_CRIT
    res = {"n_days": int(len(d)), "sought_net_sharpe": PRIOR_SHARPE, "mean_estimate": float(est.mean()),
           "sd_estimate": float(est.std(ddof=1)), "power_strict_t": passes / reps,
           "recovered": bool(abs(est.mean() - PRIOR_SHARPE) <= 3 * est.std(ddof=1) / math.sqrt(reps) + 0.05)}
    INJ.write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial() -> int:
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    px = _prices()
    d, m, a = legs(px)
    net = -m + a - 2 * LEG_COST_BPS
    t = float(net.mean() / (net.std(ddof=1) / math.sqrt(len(net))))
    sh = _sharpe(net)
    shifted = {}
    for k in range(1, 24):
        _, mk, ak = legs(px, k)
        shifted[k] = float((-mk + ak - 2 * LEG_COST_BPS).mean())
    pct = float((np.array(list(shifted.values())) < net.mean()).mean() * 100)
    se = 1 / math.sqrt(len(net) / 252)
    p0, p1 = 1 / PRIOR_SD ** 2, 1 / se ** 2
    post = (PRIOR_SHARPE * p0 + sh * p1) / (p0 + p1); post0 = sh * p1 / (p0 + p1)
    eras = {}
    for name, lo, hi in (("2010-17", dt.date(2010, 1, 1), dt.date(2017, 12, 31)), ("2018-26", dt.date(2018, 1, 1), dt.date(2026, 12, 31))):
        mm = (d >= lo) & (d <= hi)
        eras[name] = {"days": int(mm.sum()), "net_bps": float(net[mm].mean()), "sharpe": _sharpe(net[mm]),
                      "morning_short_bps": float((-m[mm]).mean()), "afternoon_long_bps": float(a[mm].mean())}
    c1, c2, c3 = t > T_CRIT, pct >= 95.0, post > 0
    out = {"hypothesis": "Z12", "window": [str(d[0]), str(d[-1])], "days": int(len(d)),
           "morning_short_gross_bps": float((-m).mean()), "afternoon_long_gross_bps": float(a.mean()),
           "net_bps": float(net.mean()), "sd_bps": float(net.std(ddof=1)), "t_net": t, "sharpe_net": sh,
           "sharpe_morning_net": _sharpe(-m - LEG_COST_BPS), "sharpe_afternoon_net": _sharpe(a - LEG_COST_BPS),
           "placebo_shift_pct": pct, "shifted_means": shifted,
           "posterior_sharpe": {"registered_prior": post, "zero_prior": post0}, "eras": eras,
           "conditions": {"t_gt_1.645": bool(c1), "placebo_ge_95": bool(c2), "posterior_gt_0": bool(c3)},
           "z_market_tests": Z_MARKET_TESTS, "decision": "CONFIRM" if (c1 and c2 and c3) else "REJECT", "injection": inj}
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n"); OUT_MD.write_text(render(out))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id="Z12", symbol="6E",
                           date_range=(out["window"][0], out["window"][1]), status="completed", sharpe=sh / math.sqrt(252),
                           params={"statistic": "daily net P&L, EUR/USD short 07:00 LDN->08:00 NY, long 08:00->16:00 NY; strict rule",
                                   "net_bps": out["net_bps"], "t_net": t, "sharpe_net": sh, "placebo_shift_pct": pct,
                                   "decision": out["decision"]},
                           note="provenance=native; source=external (Breedon & Ranaldo 2013), tested 2010-2026 after its sample; strict rule. decisions.md 128."))
    print(OUT_MD.read_text()); print("logged", rec["trial_id"])
    return 0


def render(s: dict) -> str:
    c = s["conditions"]; i = s["injection"]
    rows = ["| period | days | net bps/day | net Sharpe | morning short gross | afternoon long gross |", "|---|---|---|---|---|---|"]
    rows += [f"| {k} | {e['days']} | {e['net_bps']:+.2f} | {e['sharpe']:+.2f} | {e['morning_short_bps']:+.2f} | {e['afternoon_long_bps']:+.2f} |"
             for k, e in s["eras"].items()]
    return "\n".join([
        "# Z12 — EUR/USD: short in European hours, long in US hours (strict rule): the trial", "",
        f"**Decision: {s['decision']}.** {s['days']} weekdays, {s['window'][0]} → {s['window'][1]}.", "",
        f"- Morning short (07:00 LDN → 08:00 NY) gross {s['morning_short_gross_bps']:+.2f} bps; afternoon long (08:00 → 16:00 NY) "
        f"gross {s['afternoon_long_gross_bps']:+.2f} bps; legs' net Sharpe {s['sharpe_morning_net']:+.2f} / {s['sharpe_afternoon_net']:+.2f}.",
        f"- Day, net of 1.6 bps: **{s['net_bps']:+.2f} bps** (SD {s['sd_bps']:.1f}); t **{s['t_net']:+.2f}** (needs > 1.645): {c['t_gt_1.645']}; "
        f"annual net Sharpe {s['sharpe_net']:+.2f}.",
        f"- Placebo: the schedule shifted by each other hour: real at the **{s['placebo_shift_pct']:.0f}th** pct (needs ≥ 95): {c['placebo_ge_95']}.",
        f"- Posterior Sharpe {s['posterior_sharpe']['registered_prior']:+.2f} (zero prior {s['posterior_sharpe']['zero_prior']:+.2f}): {c['posterior_gt_0']}.",
        f"- Running count: {s['z_market_tests']} Z market-tests.", "", *rows, "",
        f"Outcome injection: net Sharpe {i['sought_net_sharpe']} planted, recovered {i['mean_estimate']:.2f} (SD {i['sd_estimate']:.2f}); "
        f"power of the strict t at that size {i['power_strict_t']:.0%}.", ""])
