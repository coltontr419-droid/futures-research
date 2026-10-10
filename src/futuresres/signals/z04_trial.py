"""Z04's outcome injection, trial and decision. Called by `python -m futuresres.signals.z04`. decisions.md 96-97."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from futuresres.data.daily_bars import load_market
from futuresres.signals.portfolio import evaluate_portfolio
from futuresres.signals.z04 import MES_MULT, MES_RT, PRIOR_MEAN, PRIOR_SD, TEST_START, weights

ROOT = Path(__file__).resolve().parents[3]
INJ = ROOT / "reports" / "z04_injection.json"
OUT = ROOT / "reports" / "z04_trial.json"
OUT_MD = ROOT / "reports" / "z04_trial.md"


def _data():
    es = load_market("ES")
    m = es.dates >= np.datetime64(TEST_START)
    price = es.front_close[m]
    return es.dates[m], es.ret[m], es.ret_low[m], es.ret_high[m], price


def injection(reps: int = 2000, seed: int = 96) -> int:
    dates, r, *_ = _data()
    w = weights(dates)
    ev = w > 0
    rng = np.random.default_rng(seed)
    n_ev = int(ev.sum())
    sigma = float(r.std())
    per_day = PRIOR_MEAN / math.sqrt(n_ev / (len(dates) / 252)) * sigma      # per-event-day mean for annual Sharpe 0.25
    est = np.empty(reps)
    for k in range(reps):
        x = rng.permutation(r - r.mean())[ev] + per_day
        est[k] = x.mean() / x.std(ddof=1) * math.sqrt(n_ev / (len(dates) / 252))
    res = {"n_event_days": n_ev, "years": len(dates) / 252, "sought_sharpe": PRIOR_MEAN,
           "mean_estimate": float(est.mean()), "sd_estimate": float(est.std(ddof=1)),
           "power_sharpe_gt_0": float((est > 0).mean()),
           "recovered": bool(abs(est.mean() - PRIOR_MEAN) <= 3 * est.std(ddof=1) / math.sqrt(reps) + 0.03)}
    INJ.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def _prop_ev(dates, r, lo, hi, price, ev, sharpe, seed=97):
    import futuresres.reporting.z_firms as zf
    notional = float(price[np.isfinite(price)][-1]) * MES_MULT
    c = notional * r[ev]; l = np.minimum(notional * lo[ev], c)
    sd = float(c.std())
    events_per_year = ev.sum() / (len(dates) / 252)
    drift = sharpe / math.sqrt(events_per_year) * sd - float(c.mean())
    c = c + drift - MES_RT; l = np.minimum(l + drift - MES_RT, c)
    k = int(round(len(c) * (len(dates) - ev.sum()) / ev.sum()))
    cc = np.concatenate([c, np.zeros(k)])[:, None].astype(np.float32)
    ll = np.concatenate([l, np.zeros(k)])[:, None].astype(np.float32)
    r_ = zf.simulate(zf.SPECS["Tradeify Select Daily (user's terms)"], (cc, ll, cc), np.random.default_rng(seed), accounts=8000)
    return {"sharpe_assumed": sharpe, "event_day_sigma_usd": sd, **r_}


def run_trial() -> int:
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    dates, r, lo, hi, price = _data()
    w = weights(dates); ev = w > 0
    cost = MES_RT / (np.nan_to_num(np.r_[price[0], price[:-1]]) * MES_MULT)
    # the split is set at the window's start, so evaluate_portfolio's "post" period IS the test window and
    # its rotation null (the event calendar shifted against returns) is computed on it. Sharpe is annualised
    # over ALL days, zeros included - the strategy's own Sharpe.
    res = evaluate_portfolio(dates, [w[:, None]], r[:, None], np.nan_to_num(cost)[:, None], TEST_START, n_rotations=500)
    full = res["post_2021"]
    s_net = full["sharpe_net"]
    a, b = r[ev], r[~ev]
    welch = (a.mean() - b.mean()) / math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    p0, p1 = 1 / PRIOR_SD ** 2, 1 / inj["sd_estimate"] ** 2
    post_mean = (PRIOR_MEAN * p0 + s_net * p1) / (p0 + p1); post_sd = math.sqrt(1 / (p0 + p1))
    ev_post = _prop_ev(dates, r, lo, hi, price, ev, post_mean)
    ev_zero = _prop_ev(dates, r, lo, hi, price, ev, 0.0)
    confirm = bool(welch > 1.645 and s_net > 0 and ev_post["ev_2y"] > 0)
    summary = {"hypothesis": "Z04", "window": [str(dates[0]), str(dates[-1])], "event_days": int(ev.sum()),
               "mean_event_bps": float(a.mean() * 1e4), "mean_other_bps": float(b.mean() * 1e4), "welch_t": float(welch),
               "sharpe_net": s_net, "sharpe_gross": full["sharpe_gross"],
               "rotation_null": res["rotation_null_post_2021"],
               "posterior": {"mean": post_mean, "sd": post_sd}, "ev_at_posterior": ev_post, "ev_at_zero_edge": ev_zero,
               "decision": "CONFIRM" if confirm else "REJECT", "injection": inj}
    OUT.write_text(json.dumps(summary, indent=1, default=float) + "\n")
    OUT_MD.write_text(render(summary))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(
        trial_id=log.next_id("t"), hypothesis_id="Z04", symbol="MES", date_range=(str(dates[0]), str(dates[-1])),
        status="completed", sharpe=s_net / math.sqrt(252),
        params={"statistic": "net Sharpe of long MES on event days (zeros elsewhere)", "sharpe_annual_net": s_net,
                "welch_t_event_vs_other": float(welch), "mean_event_bps": float(a.mean() * 1e4),
                "mean_other_bps": float(b.mean() * 1e4), "posterior_mean": post_mean,
                "ev_at_posterior_2y": ev_post["ev_2y"], "decision": summary["decision"]},
        note="provenance=native; source=external (Savor & Wilson 2013), tested 2010-2026 after the original sample. decisions.md 97."))
    print(OUT_MD.read_text()); print("logged", rec["trial_id"])
    return 0


def render(s: dict) -> str:
    e, z = s["ev_at_posterior"], s["ev_at_zero_edge"]
    return "\n".join([
        "# Z04 — the macro-announcement premium on MES: the trial", "",
        f"**Decision: {s['decision']}.** {s['event_days']} event days, {s['window'][0]} → {s['window'][1]}.", "",
        f"- Mean ES return: **{s['mean_event_bps']:+.1f} bps on event days** vs {s['mean_other_bps']:+.1f} bps on other days "
        f"(Welch t {s['welch_t']:+.2f}; needs > 1.645).",
        f"- Strategy (long MES on event days only): net Sharpe **{s['sharpe_net']:+.2f}** (gross {s['sharpe_gross']:+.2f}).",
        f"- Rotation null (calendar shifted): {s['rotation_null']}.",
        f"- Posterior Sharpe {s['posterior']['mean']:+.2f} ± {s['posterior']['sd']:.2f}.",
        f"- Tradeify, 1 MES: EV per $80 over 2 years **{e['ev_2y']:+,.0f}** at the posterior "
        f"(P(pass) {e['p_pass']:.0%}, P(payout ≤ 84 days) {e['p_payout_84']:.0%}); at zero edge {z['ev_2y']:+,.0f}.", "",
        f"Outcome injection: Sharpe {s['injection']['sought_sharpe']} planted, recovered {s['injection']['mean_estimate']:.2f} "
        f"(SD {s['injection']['sd_estimate']:.2f}); P(estimate > 0) {s['injection']['power_sharpe_gt_0']:.0%}.", ""])
