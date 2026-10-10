"""Z05's data, outcome injection, trial and decision. Called by `python -m futuresres.signals.z05`. decisions.md 99-100."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.y01_structure_ev as y
from futuresres.signals.z05 import (M_0820, M_1330, M_1655, MGC_RT, PRIOR_MEAN, PRIOR_SD, ROUND_TRIPS,
                                     TEST_START, position_profile)

ROOT = Path(__file__).resolve().parents[3]
INJ = ROOT / "reports" / "z05_injection.json"
OUT = ROOT / "reports" / "z05_trial.json"
OUT_MD = ROOT / "reports" / "z05_trial.md"


def _data():
    """Per complete MGC session: segment returns, the strategy's $ path for 1 MGC (cost not yet charged),
    and the path's worst point. Returns relative to the session's 18:00 open (y01's loader)."""
    y.SERIES = y.ROOT / "data" / "continuous" / "MGC.parquet"
    y.MULT = 10.0
    dates, H, L, C, notional = y.load_sessions()
    m = dates >= np.datetime64(TEST_START)
    dates, H, L, C = dates[m], H[m], L[m], C[m]
    P = 1.0 + C                                       # price relative to the open
    r_night1 = P[:, M_0820 - 1] - 1.0                 # 18:00 -> 08:20
    r_day = P[:, M_1330 - 1] / P[:, M_0820 - 1] - 1.0  # 08:20 -> 13:30
    r_night2 = P[:, M_1655 - 1] / P[:, M_1330 - 1] - 1.0   # 13:30 -> 16:55
    # the strategy's minute-by-minute $ path for one MGC (long / short / long)
    step = np.diff(np.concatenate([np.ones((len(P), 1)), P], axis=1), axis=1)   # price change per minute
    pos = position_profile()
    pnl_path = np.cumsum(pos[None, :] * step / 1.0, axis=1) * notional
    day_pnl = pnl_path[:, -1]
    low = pnl_path.min(axis=1)
    return dates, r_night1, r_day, r_night2, day_pnl, low, notional


def injection(reps: int = 2000, seed: int = 99) -> int:
    dates, *_, day_pnl, low, notional = _data()
    rng = np.random.default_rng(seed)
    x0 = day_pnl - ROUND_TRIPS * MGC_RT
    n = len(x0); yrs = n / 252
    sd = float(x0.std())
    mu = PRIOR_MEAN / math.sqrt(252) * sd
    est = np.empty(reps)
    for k in range(reps):
        # a BOOTSTRAP draw (with replacement): a permutation leaves the sample mean and SD unchanged, so it
        # cannot measure sampling uncertainty (caught on the first run, decisions.md 99)
        x = rng.choice(x0 - x0.mean(), size=n, replace=True) + mu
        est[k] = x.mean() / x.std(ddof=1) * math.sqrt(252)
    res = {"n_days": n, "years": yrs, "sought_sharpe": PRIOR_MEAN, "mean_estimate": float(est.mean()),
           "sd_estimate": float(est.std(ddof=1)), "power_sharpe_gt_0": float((est > 0).mean()),
           "recovered": bool(abs(est.mean() - PRIOR_MEAN) <= 3 * est.std(ddof=1) / math.sqrt(reps) + 0.03)}
    INJ.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def _prop_ev(day_pnl, low, sharpe, seed=100):
    import futuresres.reporting.z_firms as zf
    c = day_pnl - ROUND_TRIPS * MGC_RT
    l = np.minimum(low - ROUND_TRIPS * MGC_RT, c)
    sd = float(c.std())
    drift = sharpe / math.sqrt(252) * sd - float(c.mean())
    cc = (c + drift)[:, None].astype(np.float32); ll = np.minimum(l + drift, c + drift)[:, None].astype(np.float32)
    r = zf.simulate(zf.SPECS["Tradeify Select Daily (user's terms)"], (cc, ll, cc), np.random.default_rng(seed), accounts=8000)
    return {"sharpe_assumed": sharpe, "daily_sigma_usd": sd, **r}


def run_trial() -> int:
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    dates, rn1, rd, rn2, day_pnl, low, notional = _data()
    night = rn1 + rn2                                  # the overnight legs on the same session (sum of returns)
    welch = (night.mean() - rd.mean()) / math.sqrt(night.var(ddof=1) / len(night) + rd.var(ddof=1) / len(rd))
    net = day_pnl - ROUND_TRIPS * MGC_RT
    s_net = float(net.mean() / net.std(ddof=1) * math.sqrt(252))
    s_gross = float(day_pnl.mean() / day_pnl.std(ddof=1) * math.sqrt(252))
    legs = {"long_night_only_net": float(((rn1 + rn2) * notional - 2 * MGC_RT).mean() / ((rn1 + rn2) * notional).std() * math.sqrt(252)),
            "short_day_only_net": float((-rd * notional - MGC_RT).mean() / (rd * notional).std() * math.sqrt(252))}
    eras = {}
    for name, lo_, hi_ in (("2013-2016", "2013-01-01", "2016-12-31"), ("2017-2020", "2017-01-01", "2020-12-31"),
                           ("2021-2026", "2021-01-01", "2026-12-31")):
        mm = (dates >= np.datetime64(lo_)) & (dates <= np.datetime64(hi_))
        x = net[mm]
        eras[name] = {"days": int(mm.sum()), "sharpe_net": float(x.mean() / x.std(ddof=1) * math.sqrt(252)),
                      "night_bps": float(night[mm].mean() * 1e4), "day_bps": float(rd[mm].mean() * 1e4)}
    p0, p1 = 1 / PRIOR_SD ** 2, 1 / inj["sd_estimate"] ** 2
    post = (PRIOR_MEAN * p0 + s_net * p1) / (p0 + p1); post_sd = math.sqrt(1 / (p0 + p1))
    ev_post = _prop_ev(day_pnl, low, post); ev_zero = _prop_ev(day_pnl, low, 0.0)
    cond1 = bool(welch > 1.645 and night.mean() > 0 and rd.mean() < 0)
    confirm = bool(cond1 and s_net > 0 and ev_post["ev_2y"] > 0)
    s = {"hypothesis": "Z05", "window": [str(dates[0]), str(dates[-1])], "days": int(len(dates)),
         "night_bps": float(night.mean() * 1e4), "day_bps": float(rd.mean() * 1e4), "welch_t": float(welch),
         "sharpe_net": s_net, "sharpe_gross": s_gross, "legs": legs, "eras": eras,
         "posterior": {"mean": post, "sd": post_sd}, "ev_at_posterior": ev_post, "ev_at_zero_edge": ev_zero,
         "decision": "CONFIRM" if confirm else "REJECT", "injection": inj}
    OUT.write_text(json.dumps(s, indent=1, default=float) + "\n")
    OUT_MD.write_text(render(s))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id="Z05", symbol="MGC",
                           date_range=(str(dates[0]), str(dates[-1])), status="completed", sharpe=s_net / math.sqrt(252),
                           params={"statistic": "net Sharpe, long overnight / short NY day, 1 MGC", "sharpe_annual_net": s_net,
                                   "welch_t_night_vs_day": float(welch), "night_bps": s["night_bps"], "day_bps": s["day_bps"],
                                   "posterior_mean": post, "ev_at_posterior_2y": ev_post["ev_2y"], "decision": s["decision"]},
                           note="provenance=native; source=external (Blose, Gondhalekar & Kort 2018), tested 2013-2026 after the paper's sample. decisions.md 100."))
    print(OUT_MD.read_text()); print("logged", rec["trial_id"])
    return 0


def render(s: dict) -> str:
    e, z = s["ev_at_posterior"], s["ev_at_zero_edge"]
    rows = ["| period | days | overnight bps | day bps | net Sharpe |", "|---|---|---|---|---|"]
    rows += [f"| {k} | {v['days']} | {v['night_bps']:+.1f} | {v['day_bps']:+.1f} | {v['sharpe_net']:+.2f} |" for k, v in s["eras"].items()]
    return "\n".join([
        "# Z05 — gold: long overnight, short the New York day (MGC): the trial", "",
        f"**Decision: {s['decision']}.** {s['days']} sessions, {s['window'][0]} → {s['window'][1]}.", "",
        f"- Mean MGC return: overnight **{s['night_bps']:+.1f} bps**, New York day **{s['day_bps']:+.1f} bps** "
        f"(Welch t on the difference {s['welch_t']:+.2f}; needs > 1.645 with the published signs).",
        f"- Strategy, 1 MGC, three round trips a day: net Sharpe **{s['sharpe_net']:+.2f}** (gross {s['sharpe_gross']:+.2f}); "
        f"legs alone: long overnight {s['legs']['long_night_only_net']:+.2f}, short day {s['legs']['short_day_only_net']:+.2f}.",
        f"- Posterior Sharpe {s['posterior']['mean']:+.2f} ± {s['posterior']['sd']:.2f}; Tradeify EV per $80 over 2 years "
        f"**{e['ev_2y']:+,.0f}** at the posterior (P(pass) {e['p_pass']:.0%}, P(payout ≤ 84 days) {e['p_payout_84']:.0%}); "
        f"at zero edge {z['ev_2y']:+,.0f}.", "", *rows, "",
        f"Outcome injection: Sharpe {s['injection']['sought_sharpe']} planted, recovered {s['injection']['mean_estimate']:.2f} "
        f"(SD {s['injection']['sd_estimate']:.2f}); P(estimate > 0) {s['injection']['power_sharpe_gt_0']:.0%}.", ""])
