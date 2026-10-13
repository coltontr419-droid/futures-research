"""D28 - the one cell carried by the family-5 calendar scan (decisions.md 155-156): crude (MCL) is weaker on Mondays. Validated
ONCE on sealed 2018-01 -> 2026-08 data. hypotheses.yaml D28.

    python -m futuresres.signals.d_calendar --inject D28
    python -m futuresres.signals.d_calendar --run D28

Conditions (decisions.md 155, 4, with the 156 addendum): (a) the short rule against always-long on the cell's days - the daily
difference -2 x raw return - t > 1.645; (b) placebo for a WEEKDAY cell: its demeaned mean beats each of the other four weekdays'
(the 95th percentile of four); (c) posterior > 0, prior Normal(|discovery|/2, |discovery|/2); (d) 2021-26 alone > 0.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d3_relay as d3
import futuresres.reporting.d5_calendar as d5

ROOT = Path(__file__).resolve().parents[3]
CELL = {"D28": json.loads((ROOT / "reports" / "d5_discovery.json").read_text())["carried"][0]}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _p(hid):
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = CELL[hid]; S = d3.series(); cal = d5.calendar(S)
    D, Y, M = d5.cell_days(S, c["target"], c["cell"], cal, *d5.VAL)
    assert D.min() >= d5.VAL[0]
    noise = Y[~M] - Y[~M].mean(); n = int(M.sum()); mu = abs(c["mean_bps"]) / 2
    rng = np.random.default_rng(156); est = np.empty(reps); passes = 0
    for k in range(reps):
        z = rng.choice(noise, n, replace=True) + mu
        est[k] = z.mean(); passes += _t(z) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"hypothesis": hid, "n_events": n, "sought_bps": mu, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - mu) <= 3 * sd / math.sqrt(reps) + 0.5)}
    _p(hid)[0].write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial(hid: str) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = CELL[hid]; inj_p, out_p, md_p = _p(hid)
    inj = json.loads(inj_p.read_text()) if inj_p.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    S = d3.series(); cal = d5.calendar(S)
    D, Y, M = d5.cell_days(S, c["target"], c["cell"], cal, *d5.VAL)
    s = 1.0 if c["direction"] == "long" else -1.0
    z = s * (Y - Y.mean())[M]
    diff = (s - 1.0) * Y[M]
    t_a = _t(diff) if s < 0 else float((Y[M].mean() - Y[~M].mean()) / math.sqrt(Y[M].var(ddof=1) / M.sum() + Y[~M].var(ddof=1) / (~M).sum()))
    others = {}
    for wd in ("Mon", "Tue", "Wed", "Thu", "Fri"):
        if wd != c["cell"]:
            _, Yo, Mo = d5.cell_days(S, c["target"], wd, cal, *d5.VAL)
            others[wd] = float((s * (Yo - Yo.mean()))[Mo].mean())
    beats = all(z.mean() > v for v in others.values())
    mu0 = sd0 = abs(c["mean_bps"]) / 2
    p0, p1 = 1 / sd0 ** 2, 1 / (z.std(ddof=1) ** 2 / len(z))
    post = (mu0 * p0 + z.mean() * p1) / (p0 + p1)
    yrs = np.array([d.year for d in D[M]])
    eras = {lab: {"days": int(mm.sum()), "bps": float(z[mm].mean()), "t": _t(z[mm])} for lab, mm in (("2018-20", yrs <= 2020), ("2021-26", yrs >= 2021))}
    ca, cb, cc, cd = t_a > T_CRIT, beats, post > 0, eras["2021-26"]["bps"] > 0
    tier = "CONFIRM" if (ca and cb and cc and cd) else ("WATCHLIST" if z.mean() > 0 else "REJECT")
    out = {"hypothesis": hid, "cell": f"{c['target']} {c['cell']} {c['direction']}", "days": int(len(z)), "bps_vs_ordinary_day": float(z.mean()),
           "t": _t(z), "t_a": t_a, "other_weekdays": others, "posterior": post, "eras": eras,
           "conditions": {"a": bool(ca), "b_beats_other_weekdays": bool(cb), "c": bool(cc), "d": bool(cd)}, "decision": tier, "injection": inj}
    out_p.write_text(json.dumps(out, indent=1, default=float) + "\n")
    md = "\n".join([f"# {hid} — crude weaker on Mondays: the validation trial", "",
                    f"**Decision: {tier}.** {len(z)} Mondays, 2018-01 → 2026-08 (sealed until registration).", "",
                    f"- Short-Monday rule vs an ordinary day: **{z.mean():+.2f} bps**, t {_t(z):+.2f}; (a) vs always-long t **{t_a:+.2f}**: {ca}.",
                    f"- (b) Beats each other weekday ({', '.join(f'{k} {v:+.1f}' for k, v in others.items())}): {cb}.",
                    f"- (c) Posterior {post:+.2f}: {cc}. (d) 2021–26 {eras['2021-26']['bps']:+.2f} bps: {cd}. 2018–20 {eras['2018-20']['bps']:+.2f}.",
                    f"- Discovery {c['mean_bps']:+.2f} bps, t {c['t']:+.2f}. Note: the owned crude bar dated Monday runs from Friday's close, "
                    f"so it includes the weekend gap the plan (entering Sunday 18:00) does not hold. Z and D market-test 40.", ""])
    md_p.write_text(md)
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol="MCL", date_range=(str(D[M][0]), str(D[M][-1])), status="completed",
                           sharpe=float(z.mean() / z.std(ddof=1)), params={"statistic": "crude short on Mondays vs an ordinary day; sealed 2018-2026; strict rule + tiers",
                                                                          "bps": float(z.mean()), "t_a": t_a, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 5, the calendar, decisions.md 155-156); validated once on sealed data."))
    print(md); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_calendar")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
