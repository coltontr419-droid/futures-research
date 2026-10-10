"""Z02's construction check, outcome injection, trial and decision. Called by `python -m futuresres.signals.z02`.

THE DECISION RULE, ruled by the user 2026-10-09 (decisions.md 86-87) and fixed before the test runs:
  CONFIRM if the post-2023-03-17 Sharpe of the exact construction, net of cost, is > 0 with the published
  sign, AND the Tradeify evaluation EV at the POSTERIOR Sharpe is positive. Posterior: prior Normal(0.5,
  0.35) - the published ~1.0 halved for decay - updated with the test's Sharpe and its standard error
  (from the outcome injection, at the test's own n and noise).
  REJECT if the post-2023-03-17 Sharpe is <= 0.

TEST WINDOW: 2023-03-18 to the end of the data (2026-09-11) - after the paper's sample ends (2023-03-17).
2010-2023 is inside the paper's sample: the construction check uses SIGNAL properties only there, and the
trial reports that period's return as context, not evidence.

EXECUTION: weight(D) from bar D's close; held on bar D+1 (enter 20:00 ET on D - the account is flat only
17:00-18:00 - exit 16:55 ET on D+1). Cost: one MES round trip per contract per day held, $3.07 (X01),
as a fraction of MES notional per unit of weight.

PROP EV at the posterior: whole MES contracts, contracts(t) = round(weight(t) x K), capped at 5, K fixed
from the weight distribution of 2010-2023 (no returns) so that the median nonzero position is one
contract; daily P&L from ES returns with the day's adverse excursion from the held contract's high/low;
drift replaced by the posterior; Tradeify's confirmed rules (decisions.md 81-82).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Final

import numpy as np

from futuresres.data.daily_bars import align, load_market
from futuresres.signals.portfolio import evaluate_portfolio
from futuresres.signals.z02 import calendar_signal, threshold_signal, weights

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
TEST_START: Final[str] = "2023-03-18"
PAPER_AR1: Final[dict[str, float]] = {"threshold": 0.61, "calendar": 0.91}
PAPER_CORR: Final[float] = 0.605
MES_MULT: Final[float] = 5.0
MES_RT: Final[float] = 3.07
PRIOR_MEAN: Final[float] = 0.5
PRIOR_SD: Final[float] = 0.35
MAX_CONTRACTS: Final[int] = 5
OUT: Final[Path] = ROOT / "reports" / "z02_trial.json"
OUT_MD: Final[Path] = ROOT / "reports" / "z02_trial.md"
CHECK: Final[Path] = ROOT / "reports" / "z02_check.json"
INJ: Final[Path] = ROOT / "reports" / "z02_injection.json"


def _data():
    es, zn = load_market("ES"), load_market("ZN")
    dates, cols = align([es, zn])
    r_sp, r_ty = cols["ES:ret"], cols["ZN:ret"]
    price = cols["ES:price"]
    lo = np.zeros(len(dates)); hi = np.zeros(len(dates))
    idx = np.searchsorted(dates, es.dates)
    lo[idx] = es.ret_low; hi[idx] = es.ret_high
    return dates, r_sp, r_ty, price, lo, hi


def construction_check() -> int:
    """Signal properties on 2010-06 to 2023-03-17 against the paper's Table C.1 / C.2. No returns scored."""
    dates, r_sp, r_ty, *_ = _data()
    m = dates <= np.datetime64("2023-03-17")
    thr = threshold_signal(r_sp, r_ty)[m]
    cal = calendar_signal(dates, r_sp, r_ty)[m]
    ar1 = {"threshold": float(np.corrcoef(thr[:-1], thr[1:])[0, 1]),
           "calendar": float(np.corrcoef(cal[:-1], cal[1:])[0, 1])}
    corr = float(np.corrcoef(thr, cal)[0, 1])
    res = {"window": [str(dates[m][0]), str(dates[m][-1])], "ar1": ar1, "paper_ar1": PAPER_AR1,
           "corr_threshold_calendar": corr, "paper_corr": PAPER_CORR,
           "ok": bool(all(abs(ar1[k] - PAPER_AR1[k]) <= 0.1 for k in ar1) and abs(corr - PAPER_CORR) <= 0.15)}
    CHECK.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0 if res["ok"] else 1


def _held(dates, r_sp, r_ty):
    w = weights(dates, r_sp, r_ty)
    held = np.zeros_like(w); held[1:] = w[:-1]
    return held


def injection(reps: int = 2000, seed: int = 87) -> int:
    """Real post-2023 weights, real ES noise with its alignment destroyed (permuted), and a planted edge
    of Sharpe 0.5 (the prior mean). Recovery at the test's own n; and the standard error used by the
    posterior."""
    dates, r_sp, r_ty, *_ = _data()
    held = _held(dates, r_sp, r_ty)
    m = dates >= np.datetime64(TEST_START)
    w = held[m]; noise = r_sp[m]
    rng = np.random.default_rng(seed)
    sigma = float(noise.std())
    kappa = PRIOR_MEAN / math.sqrt(252) * sigma * math.sqrt(float((w ** 2).mean())) / float((w ** 2).mean())
    est = np.empty(reps)
    for k in range(reps):
        e = rng.permutation(noise - noise.mean()) + kappa * w
        x = w * e
        est[k] = x.mean() / x.std(ddof=1) * math.sqrt(252)
    res = {"n_injection": int(m.sum()), "sought_sharpe": PRIOR_MEAN, "mean_estimate": float(est.mean()),
           "sd_estimate": float(est.std(ddof=1)), "power_sharpe_gt_0": float((est > 0).mean()),
           "recovered": bool(abs(est.mean() - PRIOR_MEAN) <= 3 * est.std(ddof=1) / math.sqrt(reps) + 0.05)}
    INJ.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def _posterior(s: float, se: float) -> tuple[float, float]:
    p0, p1 = 1 / PRIOR_SD ** 2, 1 / se ** 2
    v = 1 / (p0 + p1)
    return v * (PRIOR_MEAN * p0 + s * p1), math.sqrt(v)


SIZINGS: Final[tuple[str, ...]] = ("proportional_cap5", "proportional_cap2", "sign_1", "sign_2")


def _contracts(held: np.ndarray, K: float, sizing: str) -> np.ndarray:
    if sizing == "proportional_cap5":
        return np.clip(np.rint(held * K), -MAX_CONTRACTS, MAX_CONTRACTS)
    if sizing == "proportional_cap2":
        return np.clip(np.rint(held * K), -2, 2)
    base = np.sign(np.rint(held * K))                 # same days in the market as proportional sizing
    return base * (1 if sizing == "sign_1" else 2)


def _prop_ev(dates, r_sp, price, lo, hi, held, sharpe: float, seed: int = 88,
             sizing: str = "proportional_cap5") -> dict:
    import futuresres.reporting.y01_structure_ev as y
    import futuresres.reporting.y02_tradeify as z
    pre = dates <= np.datetime64("2023-03-17")
    nz = np.abs(held[pre & (held != 0)])
    K = 1.0 / float(np.median(nz))
    contracts = _contracts(held, K, sizing)
    notional = np.r_[price[0], price[:-1]] * MES_MULT
    live = (contracts != 0) & np.isfinite(notional)
    c_usd = contracts * notional * r_sp
    adverse = np.where(contracts > 0, contracts * notional * lo, -contracts * notional * hi)
    cost = np.abs(contracts) * MES_RT
    c_usd, adverse, cost = c_usd[live], adverse[live], cost[live]
    sd = float(c_usd.std())
    # `sharpe` is NET of cost (the test statistic is net), so the gross drift must cover the cost charged
    # below. CORRECTED 2026-10-09 (decisions.md 88): the first run charged the cost twice.
    drift = sharpe / math.sqrt(252) * sd - float(c_usd.mean()) + float(cost.mean())
    c_path = (c_usd + drift - cost)[:, None]
    l_path = np.minimum(adverse + drift - cost, c_path[:, 0])[:, None]
    saved = (y.RT_COST, y.TICK_USD)
    y.RT_COST, y.TICK_USD = 0.0, 1.25
    try:
        rng = np.random.default_rng(seed)
        e = z.run_eval((c_path, l_path, c_path), 1, rng, True, z.CONSISTENCY, accounts=8000, lock=False)
        paid = z.run_funded((c_path, l_path, c_path), 1, rng, True, 1, z.CAP, accounts=8000, live_after=3)
    finally:
        y.RT_COST, y.TICK_USD = saved
    return {"sharpe_assumed": sharpe, "sizing": sizing, "K": K, "days_in_market_share": float(live.mean()),
            "daily_sigma_usd_in_market": sd, "median_contracts": float(np.median(np.abs(contracts[live]))),
            "p_pass": e["p_pass"], "expected_payout": float(paid.mean()),
            "ev": e["p_pass"] * float(paid.mean()) - 80.0}


def ev_sensitivity() -> int:
    """Recompute the decision's EV component after the cost correction, without re-running the trial:
    at the posterior, its +/-1 SD, and at zero edge for the same sizing."""
    dates, r_sp, r_ty, price, lo, hi = _data()
    held = _held(dates, r_sp, r_ty)
    s = json.loads(OUT.read_text())
    m, sd = s["posterior"]["mean"], s["posterior"]["sd"]
    rows = [_prop_ev(dates, r_sp, price, lo, hi, held, x) for x in (0.0, m - sd, m, m + sd)]
    s["prop_ev_corrected"] = {"rows": rows, "posterior_mean": m, "posterior_sd": sd,
                              "decision": "CONFIRM" if (s["test"]["sharpe_net"] > 0 and rows[2]["ev"] > 0)
                              else "REJECT"}
    OUT.write_text(json.dumps(s, indent=1, default=float) + "\n")
    for r in rows:
        print(f"Sharpe {r['sharpe_assumed']:+.2f}: P(pass) {r['p_pass']:.3f} payout {r['expected_payout']:.0f} "
              f"EV {r['ev']:+.0f}")
    print("decision:", s["prop_ev_corrected"]["decision"])
    return 0


def sizing_ev() -> int:
    """EV at the posterior (and its +/-1 SD, and zero) for four sizing rules fixed before this run. The
    simulation imposes the drift, so it compares sizings on the SHAPE of the returns, not their realised
    mean; it does not re-test the edge. decisions.md 88."""
    dates, r_sp, r_ty, price, lo, hi = _data()
    held = _held(dates, r_sp, r_ty)
    s = json.loads(OUT.read_text())
    m, sd = s["posterior"]["mean"], s["posterior"]["sd"]
    rows = []
    for sz in SIZINGS:
        for x in (0.0, m - sd, m, m + sd):
            r = _prop_ev(dates, r_sp, price, lo, hi, held, x, sizing=sz)
            rows.append(r)
            print(f"{sz:18} Sharpe {x:+.2f}: P(pass) {r['p_pass']:.3f} payout {r['expected_payout']:.0f} "
                  f"EV {r['ev']:+.0f}  sigma {r['daily_sigma_usd_in_market']:.0f}", flush=True)
    s["sizing_ev"] = rows
    OUT.write_text(json.dumps(s, indent=1, default=float) + "\n")
    return 0


def run_trial() -> int:
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    chk = json.loads(CHECK.read_text()) if CHECK.exists() else None
    if not (inj and inj["recovered"] and chk and chk["ok"]):
        raise SystemExit("refusing to run: construction check or outcome injection missing or failed")
    dates, r_sp, r_ty, price, lo, hi = _data()
    held = _held(dates, r_sp, r_ty)
    cost = MES_RT / (np.r_[price[0], price[:-1]] * MES_MULT)
    cost = np.nan_to_num(cost, nan=0.0)
    res = evaluate_portfolio(dates, [held[:, None]], r_sp[:, None], cost[:, None], TEST_START, n_rotations=500)
    test = res["post_2021"]; before = res["pre_2021"]          # keys name the split at TEST_START
    s, se = test["sharpe_net"], inj["sd_estimate"]
    post_mean, post_sd = _posterior(s, se)
    ev = _prop_ev(dates, r_sp, price, lo, hi, held, post_mean)
    confirm = bool(s > 0 and ev["ev"] > 0)
    summary = {"hypothesis": "Z02", "test_window": [TEST_START, str(dates[-1])], "test": test,
               "before_test_context_only": before, "rotation_null_test": res["rotation_null_post_2021"],
               "posterior": {"mean": post_mean, "sd": post_sd, "prior": [PRIOR_MEAN, PRIOR_SD], "se_used": se},
               "prop_ev_at_posterior": ev, "decision": "CONFIRM" if confirm else "REJECT",
               "injection": inj, "construction_check": chk}
    OUT.write_text(json.dumps(summary, indent=1, default=float) + "\n")
    OUT_MD.write_text(render(summary))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(
        trial_id=log.next_id("t"), hypothesis_id="Z02", symbol="MES",
        date_range=(TEST_START, str(dates[-1])), status="completed",
        sharpe=s / math.sqrt(252),
        params={"statistic": "post-2023-03-17 daily net Sharpe of the equity leg (per observation in `sharpe`)",
                "sharpe_annual_test_net": s, "sharpe_annual_test_gross": test["sharpe_gross"], "t_test": test["t"],
                "posterior_mean": post_mean, "posterior_sd": post_sd, "prop_ev_at_posterior": ev["ev"],
                "decision": summary["decision"],
                "rotation_share_at_or_above": res["rotation_null_post_2021"]["share_at_or_above_real"]},
        note=("provenance=native; source=external (Harvey, Mazzoleni & Melone 2025), replicated to the letter; "
              "tested only after the paper's sample end. One trial. decisions.md 87."),
    ))
    print(OUT_MD.read_text())
    print(f"logged {rec['trial_id']}")
    return 0


def render(s: dict) -> str:
    t, b, rn, p, ev = (s["test"], s["before_test_context_only"], s["rotation_null_test"], s["posterior"],
                       s["prop_ev_at_posterior"])
    w: list[str] = []
    a = w.append
    a("# Z02 — front-running rebalancers, equity leg on MES: the trial")
    a("")
    a("Generated by `python -m futuresres.signals.z02 --run`. One trial; `hypotheses.yaml` Z02; `decisions.md` §86–§87.")
    a("")
    a(f"**Decision: {s['decision']}.** Post-{s['test_window'][0]} net Sharpe {t['sharpe_net']:+.2f} "
      f"(gross {t['sharpe_gross']:+.2f}, T = {t['t']:,}); posterior {p['mean']:+.2f} ± {p['sd']:.2f}; "
      f"Tradeify EV at the posterior {ev['ev']:+,.0f} per $80.")
    a("")
    a("| | T | Sharpe gross | Sharpe net |")
    a("|---|---|---|---|")
    a(f"| **test, {s['test_window'][0]} → {s['test_window'][1]}** | {t['t']:,} | {t['sharpe_gross']:+.2f} | **{t['sharpe_net']:+.2f}** |")
    a(f"| 2010–2023-03-17 (inside the paper's sample — context, not evidence) | {b['t']:,} | {b['sharpe_gross']:+.2f} | {b['sharpe_net']:+.2f} |")
    a("")
    a(f"Rotation null (500), test window: mean {rn['mean']:+.2f}, 95th percentile {rn['p95']:+.2f}, share at "
      f"or above the real {rn['share_at_or_above_real']:.3f}.")
    a("")
    i = s["injection"]
    a(f"Outcome injection: Sharpe {i['sought_sharpe']} planted at n = {i['n_injection']:,}, recovered "
      f"{i['mean_estimate']:.2f} (SD {i['sd_estimate']:.2f}); P(estimate > 0) {i['power_sharpe_gt_0']:.0%}.")
    a("")
    c = s["construction_check"]
    a(f"Construction check (signals only): AR(1) threshold {c['ar1']['threshold']:.2f} (paper 0.61), calendar "
      f"{c['ar1']['calendar']:.2f} (paper 0.91); correlation {c['corr_threshold_calendar']:.2f} (paper 0.605).")
    a("")
    a(f"Prop EV at the posterior: {ev['median_contracts']:.0f} MES median position, in the market "
      f"{ev['days_in_market_share']:.0%} of days, daily $σ {ev['daily_sigma_usd_in_market']:,.0f}; "
      f"P(pass) {ev['p_pass']:.1%}, E[payout] {ev['expected_payout']:,.0f}, EV {ev['ev']:+,.0f}.")
    a("")
    return "\n".join(w)
