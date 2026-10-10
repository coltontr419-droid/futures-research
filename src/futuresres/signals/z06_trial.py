"""Z06's data, outcome injection, trial and decision. Called by `python -m futuresres.signals.z06`. decisions.md 110."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from futuresres.signals.z06 import PLANS, PRIOR_MEAN, PRIOR_SD, TEST_END, TEST_START, monthly_sign

ROOT = Path(__file__).resolve().parents[3]
INJ = ROOT / "reports" / "z06_injection.json"
OUT = ROOT / "reports" / "z06_trial.json"
OUT_MD = ROOT / "reports" / "z06_trial.md"


def window_returns(prod: str):
    """Session dates and REAL window returns (drift kept), complete sessions, era by era (the 2.7 GB machine)."""
    cache = ROOT / "data" / "cache" / f"z06_{prod}.npz"
    if cache.exists():
        z = np.load(cache)
        return z["d"], z["r"]
    import polars as pl
    import futuresres.reporting.y01_structure_ev as y
    import futuresres.reporting.y03_sessions as s3
    spec = s3.PRODUCTS[prod]; full = ROOT / "data" / "continuous" / f"{spec['series']}.parquet"
    cache.parent.mkdir(parents=True, exist_ok=True)
    D, R = [], []
    for era, rows in (("pre", pl.col("session") < pl.date(2021, 1, 1)), ("post", pl.col("session") >= pl.date(2021, 1, 1))):
        sub = cache.parent / f"z06_{prod}_{era}.parquet"
        pl.scan_parquet(full).filter(rows).sink_parquet(sub)
        try:
            y.SERIES = sub; y.MULT = spec["mult"]; y.WINDOWS.update(s3.WINDOWS)
            d, H, L, C, _ = y.load_sessions()
            a, b = y.WINDOWS[PLANS[prod]["window"]]
            r = (1.0 + C[:, b - 1].astype(np.float64)) / (1.0 + C[:, a - 1].astype(np.float64)) - 1.0
            D.append(d); R.append(r)
            del H, L, C
        finally:
            sub.unlink(missing_ok=True)
    d, r = np.concatenate(D), np.concatenate(R)
    np.savez(cache, d=d, r=r)
    return d, r


def _data(prod: str):
    from futuresres.data.daily_bars import load_market
    mk = load_market(PLANS[prod]["daily"])
    sig = monthly_sign(mk.dates, mk.ret)
    d, r = window_returns(prod)
    m = (d >= np.datetime64(TEST_START)) & (d <= np.datetime64(TEST_END))
    d, r = d[m], r[m]
    s = np.array([sig.get(str(x.astype("datetime64[M]")), np.nan) for x in d])
    ok = np.isfinite(s)
    return d[ok], r[ok], s[ok]


def _sharpe(x) -> float:
    return float(x.mean() / x.std(ddof=1) * math.sqrt(252))


def injection(reps: int = 2000, seed: int = 110) -> int:
    res = {}
    rng = np.random.default_rng(seed)
    for prod in PLANS:
        d, r, s = _data(prod)
        x0 = s * r
        n = len(x0); mu = PRIOR_MEAN / math.sqrt(252) * float(x0.std())
        est = np.array([_sharpe(rng.choice(x0 - x0.mean(), size=n, replace=True) + mu) for _ in range(reps)])
        res[prod] = {"n_sessions": n, "sought_sharpe": PRIOR_MEAN, "mean_estimate": float(est.mean()),
                     "sd_estimate": float(est.std(ddof=1)), "power_sharpe_gt_0": float((est > 0).mean()),
                     "recovered": bool(abs(est.mean() - PRIOR_MEAN) <= 3 * est.std(ddof=1) / math.sqrt(reps) + 0.03)}
    res["recovered"] = all(v["recovered"] for v in res.values())
    INJ.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial() -> int:
    inj = json.loads(INJ.read_text()) if INJ.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    out = {"hypothesis": "Z06", "products": {}}
    for prod in PLANS:
        d, r, s = _data(prod)
        x = s * r
        sh, sh_long = _sharpe(x), _sharpe(r)
        p0, p1 = 1 / PRIOR_SD ** 2, 1 / inj[prod]["sd_estimate"] ** 2
        post = (PRIOR_MEAN * p0 + sh * p1) / (p0 + p1); post_sd = math.sqrt(1 / (p0 + p1))
        eras = {}
        for name, lo, hi in (("2011-15", "2011-01-01", "2015-12-31"), ("2016-20", "2016-01-01", "2020-12-31"),
                             ("2021-26", "2021-01-01", "2026-12-31")):
            mm = (d >= np.datetime64(lo)) & (d <= np.datetime64(hi))
            eras[name] = {"sessions": int(mm.sum()), "sharpe_signal": _sharpe(x[mm]), "sharpe_long": _sharpe(r[mm]),
                          "short_share": float((s[mm] < 0).mean())}
        c1, c2, c3 = sh > 0, float(x.mean()) > float(r.mean()), post > 0
        out["products"][prod] = {
            "window": [str(d[0]), str(d[-1])], "sessions": int(len(d)), "sharpe_signal": sh, "sharpe_always_long": sh_long,
            "mean_signal_bps": float(x.mean() * 1e4), "mean_long_bps": float(r.mean() * 1e4),
            "short_share": float((s < 0).mean()), "mean_bps_on_short_days": float(r[s < 0].mean() * 1e4) if (s < 0).any() else None,
            "posterior": {"mean": post, "sd": post_sd}, "eras": eras,
            "conditions": {"sharpe_gt_0": bool(c1), "beats_always_long": bool(c2), "posterior_gt_0": bool(c3)},
            "decision": "CONFIRM" if (c1 and c2 and c3) else "REJECT"}
    out["injection"] = inj
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n"); OUT_MD.write_text(render(out))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    pm = out["products"]
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id="Z06", symbol="MNQ+MGC",
                           date_range=(TEST_START, TEST_END), status="completed",
                           sharpe=float(np.mean([v["sharpe_signal"] for v in pm.values()])) / math.sqrt(252),
                           params={"statistic": "annualised Sharpe of trend sign x plan window return, per product",
                                   **{f"{k}_{f}": v[f] for k, v in pm.items() for f in ("sharpe_signal", "sharpe_always_long", "decision")}},
                           note="provenance=native; source=external (Moskowitz, Ooi & Pedersen 2012), tested 2011-2026 after the paper's sample; follow-on to W04. decisions.md 110."))
    print(OUT_MD.read_text()); print("logged", rec["trial_id"])
    return 0


def render(s: dict) -> str:
    w = ["# Z06 — the 12-month trend sign sets the bracket's direction: the trial", ""]
    for prod, v in s["products"].items():
        c = v["conditions"]
        w += [f"## {prod} — **{v['decision']}**", "",
              f"{v['sessions']} sessions, {v['window'][0]} → {v['window'][1]}; short in {v['short_share']:.0%} of sessions.", "",
              f"- Sign × window: Sharpe **{v['sharpe_signal']:+.2f}** (mean {v['mean_signal_bps']:+.2f} bps) — needs > 0: {c['sharpe_gt_0']}.",
              f"- Always long, same window: Sharpe {v['sharpe_always_long']:+.2f} (mean {v['mean_long_bps']:+.2f} bps) — signal must beat it: {c['beats_always_long']}."
              + (f" Window mean on short-signal sessions {v['mean_bps_on_short_days']:+.2f} bps." if v["mean_bps_on_short_days"] is not None else ""),
              f"- Posterior {v['posterior']['mean']:+.2f} ± {v['posterior']['sd']:.2f} — needs > 0: {c['posterior_gt_0']}.", "",
              "| period | sessions | signal Sharpe | always-long Sharpe | short share |", "|---|---|---|---|---|"]
        w += [f"| {k} | {e['sessions']} | {e['sharpe_signal']:+.2f} | {e['sharpe_long']:+.2f} | {e['short_share']:.0%} |" for k, e in v["eras"].items()]
        i = s["injection"][prod]
        w += ["", f"Outcome injection: {i['sought_sharpe']} planted, recovered {i['mean_estimate']:.2f} (SD {i['sd_estimate']:.2f}); "
              f"P(estimate > 0) {i['power_sharpe_gt_0']:.0%}.", ""]
    return "\n".join(w)
