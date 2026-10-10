"""Z08's data, outcome injection, trial and decision. Called by `python -m futuresres.signals.z08`. decisions.md 117."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from futuresres.data.cot import commercial_flow, next_week_direction
from futuresres.signals.z08 import PRIOR_MEAN, PRIOR_SD, PRODUCTS, TEST_END, TEST_START

ROOT = Path(__file__).resolve().parents[3]
INJ = ROOT / "reports" / "z08_injection.json"
OUT = ROOT / "reports" / "z08_trial.json"
OUT_MD = ROOT / "reports" / "z08_trial.md"


def _sharpe(x) -> float:
    return float(x.mean() / x.std(ddof=1) * math.sqrt(252))


def _window(prod: str):
    from futuresres.data.daily_bars import load_market
    if prod == "MCL":
        mk = load_market("CL")
        m = ~mk.crossover & (mk.ret != 0)
        return mk.dates[m].astype("datetime64[D]"), mk.ret[m]
    from futuresres.signals.z06_trial import window_returns
    d, r = window_returns("MGC")
    return d.astype("datetime64[D]"), r


def _data(prod: str):
    d, r = _window(prod)
    m = (d >= np.datetime64(TEST_START)) & (d <= np.datetime64(TEST_END))
    d, r = d[m], r[m]
    tu, q = commercial_flow(PRODUCTS[prod])
    s = next_week_direction(tu, q, d)
    ok = np.isfinite(s)
    return d[ok], r[ok], s[ok]


def injection(reps: int = 2000, seed: int = 117) -> int:
    res = {}
    rng = np.random.default_rng(seed)
    for prod in PRODUCTS:
        d, r, s = _data(prod)
        x0 = s * r; n = len(x0); mu = PRIOR_MEAN / math.sqrt(252) * float(x0.std())
        est = np.array([_sharpe(rng.choice(x0 - x0.mean(), size=n, replace=True) + mu) for _ in range(reps)])
        res[prod] = {"n_sessions": n, "sought_sharpe": PRIOR_MEAN, "mean_estimate": float(est.mean()),
                     "sd_estimate": float(est.std(ddof=1)), "power_sharpe_gt_0": float((est > 0).mean()),
                     "recovered": bool(abs(est.mean() - PRIOR_MEAN) <= 3 * est.std(ddof=1) / math.sqrt(reps) + 0.03)}
    res["recovered"] = all(v["recovered"] for v in res.values())
    INJ.write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial() -> int:
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    out = {"hypothesis": "Z08", "products": {}}
    for prod in PRODUCTS:
        d, r, s = _data(prod)
        x = s * r
        sh, sh_long = _sharpe(x), _sharpe(r)
        p0, p1 = 1 / PRIOR_SD ** 2, 1 / inj[prod]["sd_estimate"] ** 2
        post = (PRIOR_MEAN * p0 + sh * p1) / (p0 + p1); post_sd = math.sqrt(1 / (p0 + p1))
        eras = {}
        for name, lo, hi in (("2015-20", "2015-01-01", "2020-12-31"), ("2021-26", "2021-01-01", "2026-12-31")):
            mm = (d >= np.datetime64(lo)) & (d <= np.datetime64(hi))
            eras[name] = {"sessions": int(mm.sum()), "sharpe_signal": _sharpe(x[mm]), "sharpe_long": _sharpe(r[mm])}
        c1, c2, c3 = sh > 0, float(x.mean()) > float(r.mean()), post > 0
        out["products"][prod] = {
            "window": [str(d[0]), str(d[-1])], "sessions": int(len(d)), "sharpe_signal": sh, "sharpe_always_long": sh_long,
            "mean_signal_bps": float(x.mean() * 1e4), "mean_long_bps": float(r.mean() * 1e4),
            "long_share": float((s > 0).mean()), "mean_bps_after_hedger_buying": float(r[s > 0].mean() * 1e4),
            "mean_bps_after_hedger_selling": float(r[s < 0].mean() * 1e4),
            "posterior": {"mean": post, "sd": post_sd}, "eras": eras,
            "conditions": {"sharpe_gt_0": bool(c1), "beats_always_long": bool(c2), "posterior_gt_0": bool(c3)},
            "decision": "CONFIRM" if (c1 and c2 and c3) else "REJECT"}
    # gold, not decisive: the same rule on the full-session daily GC return
    from futuresres.data.daily_bars import load_market
    gc = load_market("GC"); m = ~gc.crossover & (gc.ret != 0)
    gd, gr = gc.dates[m].astype("datetime64[D]"), gc.ret[m]
    mm = (gd >= np.datetime64(TEST_START)) & (gd <= np.datetime64(TEST_END)); gd, gr = gd[mm], gr[mm]
    tu, q = commercial_flow("GC"); gs = next_week_direction(tu, q, gd); ok = np.isfinite(gs)
    out["gold_full_session_daily"] = {"sharpe_signal": _sharpe((gs * gr)[ok]), "sharpe_long": _sharpe(gr[ok]), "sessions": int(ok.sum())}
    out["injection"] = inj
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n"); OUT_MD.write_text(render(out))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    pm = out["products"]
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id="Z08", symbol="MCL+MGC",
                           date_range=(TEST_START, TEST_END), status="completed",
                           sharpe=float(np.mean([v["sharpe_signal"] for v in pm.values()])) / math.sqrt(252),
                           params={"statistic": "annualised Sharpe of COT hedger-flow sign x plan window return, per product",
                                   **{f"{k}_{f}": v[f] for k, v in pm.items() for f in ("sharpe_signal", "sharpe_always_long", "decision")}},
                           note="provenance=native; source=external (Kang, Rouwenhorst & Tang 2020), tested 2015-2026 after the paper's sample. decisions.md 117."))
    print(OUT_MD.read_text()); print("logged", rec["trial_id"])
    return 0


def render(s: dict) -> str:
    w = ["# Z08 — hedger flow (CFTC COT) sets the commodity brackets' direction: the trial", ""]
    for prod, v in s["products"].items():
        c = v["conditions"]; i = s["injection"][prod]
        w += [f"## {prod} — **{v['decision']}**", "",
              f"{v['sessions']} sessions, {v['window'][0]} → {v['window'][1]}; long in {v['long_share']:.0%}.", "",
              f"- Sign × window: Sharpe **{v['sharpe_signal']:+.2f}** (mean {v['mean_signal_bps']:+.2f} bps) — needs > 0: {c['sharpe_gt_0']}.",
              f"- Always long: Sharpe {v['sharpe_always_long']:+.2f} (mean {v['mean_long_bps']:+.2f} bps) — must beat it: {c['beats_always_long']}.",
              f"- Window mean after hedgers bought {v['mean_bps_after_hedger_buying']:+.2f} bps; after they sold {v['mean_bps_after_hedger_selling']:+.2f} bps.",
              f"- Posterior {v['posterior']['mean']:+.2f} ± {v['posterior']['sd']:.2f} — needs > 0: {c['posterior_gt_0']}.", "",
              "| period | sessions | signal Sharpe | always-long Sharpe |", "|---|---|---|---|"]
        w += [f"| {k} | {e['sessions']} | {e['sharpe_signal']:+.2f} | {e['sharpe_long']:+.2f} |" for k, e in v["eras"].items()]
        w += ["", f"Outcome injection: {i['sought_sharpe']} planted, recovered {i['mean_estimate']:.2f} (SD {i['sd_estimate']:.2f}); "
              f"P(estimate > 0) {i['power_sharpe_gt_0']:.0%}.", ""]
    gfd = s["gold_full_session_daily"]
    w += [f"Gold, not decisive — the same rule on the full-session daily GC return: Sharpe {gfd['sharpe_signal']:+.2f} "
          f"(always long {gfd['sharpe_long']:+.2f}), {gfd['sessions']} sessions.", ""]
    return "\n".join(w)
