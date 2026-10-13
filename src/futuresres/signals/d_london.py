"""D32-D36 - the London-continuation tests carried by the family-7 discovery (decisions.md 161-162), each validated ONCE on sealed
2018-01 -> 2026-08 data. hypotheses.yaml D32-D36. Conditions as decisions.md 149, 5; the always-long baseline is a long
position over the same London window (03:00 -> 11:30 New York).

    python -m futuresres.signals.d_london --inject D29
    python -m futuresres.signals.d_london --run D29
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d7_london as d7

ROOT = Path(__file__).resolve().parents[3]
FIRST_ID, FIRST_TEST_NUMBER = 32, 44


def cells() -> dict:
    c = json.loads((ROOT / "reports" / "d7_discovery.json").read_text())["carried"]
    return {f"D{FIRST_ID + i}": x for i, x in enumerate(c)}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _p(hid):
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def data(c: dict, shift: int = 0):
    D, Y, X = d7.rows(c["pair"], c["predictor"], *d7.VAL)
    assert D.min() >= d7.VAL[0]
    if shift:
        n = len(D); idx = np.arange(n) - shift; keep = (idx >= 0) & (idx < n)
        D, Y, X = D[keep], Y[keep], X[np.clip(idx, 0, n - 1)][keep]
    m = np.ones(len(X), bool) if c["form"] == "all" else np.abs(X) > c["median_abs_pred"]
    s = 1.0 if c["rule"] == "follow" else -1.0
    return D[m], Y[m], s * np.sign(X[m])


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; D, Y, dirn = data(c)
    ydm = Y - Y.mean(); mu = abs(c["mean_bps"]) / 2; n = len(Y)
    rng = np.random.default_rng(162 + int(hid[1:])); est = np.empty(reps); passes = 0
    for k in range(reps):
        z = rng.choice(ydm, n, replace=True) * rng.choice([-1.0, 1.0], n) + mu
        est[k] = z.mean(); passes += _t(z) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"hypothesis": hid, "n_events": n, "sought_bps": mu, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - mu) <= 3 * sd / math.sqrt(reps) + 0.1)}
    _p(hid)[0].write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial(hid: str) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; inj_p, out_p, md_p = _p(hid)
    inj = json.loads(inj_p.read_text()) if inj_p.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    D, Y, dirn = data(c)
    z = dirn * (Y - Y.mean()); diff = (dirn - 1.0) * Y; t_diff = _t(diff)
    shifted = []
    for k in [s for s in range(-11, 12) if abs(s) >= 2]:
        Ds, Ys, ds = data(c, shift=k); shifted.append(float((ds * (Ys - Ys.mean())).mean()))
    pct = float((np.array(shifted) < z.mean()).mean() * 100)
    mu0 = sd0 = abs(c["mean_bps"]) / 2
    p0, p1 = 1 / sd0 ** 2, 1 / (z.std(ddof=1) ** 2 / len(z))
    post = (mu0 * p0 + z.mean() * p1) / (p0 + p1); post0 = z.mean() * p1 / (p0 + p1)
    yrs = np.array([d.year for d in D])
    eras = {lab: {"days": int(mm.sum()), "demeaned_bps": float(z[mm].mean()), "t": _t(z[mm]), "vs_long_bps": float(diff[mm].mean())}
            for lab, mm in (("2018-20", yrs <= 2020), ("2021-26", yrs >= 2021))}
    ca, cb, cc, cd = t_diff > T_CRIT, pct >= 95.0, post > 0, eras["2021-26"]["demeaned_bps"] > 0
    tier = "CONFIRM" if (ca and cb and cc and cd) else ("WATCHLIST" if z.mean() > 0 else "REJECT")
    number = FIRST_TEST_NUMBER + list(cells()).index(hid)
    title = f"{c['pair']} London window {c['rule']}s {'its own' if c['predictor'] == 'own' else 'gold' + chr(39) + 's'} overnight move ({'every day' if c['form'] == 'all' else 'strong days'})"
    out = {"hypothesis": hid, "cell": title, "window": [str(D[0]), str(D[-1])], "days": int(len(z)), "demeaned_bps": float(z.mean()),
           "t_demeaned": _t(z), "vs_always_long_bps": float(diff.mean()), "t_vs_always_long": t_diff, "hit_rate": float((z > 0).mean()),
           "placebo_pct": pct, "shifted_means": shifted, "prior": [mu0, sd0], "posterior_bps": {"registered_prior": post, "zero_prior": post0},
           "eras": eras, "discovery": {k: c[k] for k in ("n", "mean_bps", "t")},
           "conditions": {"vs_long_t_gt_1.645": bool(ca), "placebo_ge_95": bool(cb), "posterior_gt_0": bool(cc), "post2021_gt_0": bool(cd)},
           "z_d_market_test_number": number, "decision": tier, "injection": inj}
    out_p.write_text(json.dumps(out, indent=1, default=float) + "\n")
    rows = ["| period | days | demeaned bps | t | vs always-long bps |", "|---|---|---|---|---|"] + \
        [f"| {k} | {e['days']} | {e['demeaned_bps']:+.2f} | {e['t']:+.2f} | {e['vs_long_bps']:+.2f} |" for k, e in eras.items()]
    md_p.write_text("\n".join([
        f"# {hid} — {title}: the validation trial", "",
        f"**Decision: {tier}.** {len(z)} days, {out['window'][0]} → {out['window'][1]} (sealed until registration).", "",
        f"- Demeaned (skill beyond drift): **{z.mean():+.2f} bps** a day, t {_t(z):+.2f}; hit rate {out['hit_rate']:.0%}.",
        f"- (a) Against always-long over the same window, raw: **{diff.mean():+.2f} bps**, t **{t_diff:+.2f}** (needs > 1.645): {ca}.",
        f"- (b) Placebo, predictor shifted ±2…±11 days: real at the **{pct:.0f}th** pct (needs ≥ 95): {cb}.",
        f"- (c) Posterior {post:+.2f} bps (prior Normal({mu0:.2f}, {sd0:.2f})): {cc}. (d) 2021–26 alone {eras['2021-26']['demeaned_bps']:+.2f}: {cd}.",
        f"- Discovery (2010–17): {c['mean_bps']:+.2f} bps, t {c['t']:+.2f}, n {c['n']}. Z and D market-test number {number}.", "", *rows, "",
        f"Outcome injection: {inj['sought_bps']:.2f} bp planted, recovered {inj['mean_estimate']:.2f}; power of the strict t {inj['power_strict_t']:.0%}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    fut = c["future"]
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=fut, date_range=(out["window"][0], out["window"][1]),
                           status="completed", sharpe=float(z.mean() / z.std(ddof=1)),
                           params={"statistic": f"London continuation: {title}; sealed 2018-2026; strict rule vs always-long + S8 + tiers",
                                   "demeaned_bps": out["demeaned_bps"], "t_vs_always_long": t_diff, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 7, London continuation, decisions.md 161-162); validated once on sealed data."))
    print(md_p.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_london")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
