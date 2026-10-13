"""D57 - the test carried by the family-16 discovery (decisions.md 187-188): DAX's last 30 minutes follow the window so far on
strong days. Validated ONCE on sealed 2023-01 -> 2026-08 data, standalone net of cost. hypotheses.yaml D57.

    python -m futuresres.signals.d_close --inject D57
    python -m futuresres.signals.d_close --run D57
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d16_close as d16

ROOT = Path(__file__).resolve().parents[3]
CELL = {"D57": json.loads((ROOT / "reports" / "d16_discovery.json").read_text())["carried"][0]}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _p(hid):
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def rule_net(c, Y, X):
    m = np.ones(len(X), bool) if c["form"] == "all" else np.abs(X) > c["median_abs_pred"]
    s = 1.0 if c["rule"] == "follow" else -1.0
    return m, s * np.sign(X) * Y - d16.COST[c["market"]]


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = CELL[hid]; D, Y, X = d16.rows(c["market"], c["predictor"], *d16.VAL); assert D.min() >= d16.VAL[0]
    m, net = rule_net(c, Y, X); net = net[m]; noise = net - net.mean(); mu = c["net_bps"] / 2
    rng = np.random.default_rng(188); est = np.empty(reps); passes = 0
    for k in range(reps):
        z = rng.choice(noise, len(net), replace=True) + mu
        est[k] = z.mean(); passes += _t(z) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"hypothesis": hid, "n_events": int(len(net)), "sought_bps": mu, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - mu) <= 3 * sd / math.sqrt(reps) + 0.1)}
    _p(hid)[0].write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial(hid: str) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = CELL[hid]; inj_p, out_p, md_p = _p(hid)
    inj = json.loads(inj_p.read_text()) if inj_p.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    D, Y, X = d16.rows(c["market"], c["predictor"], *d16.VAL)
    m, net_all = rule_net(c, Y, X); net = net_all[m]; Dm = D[m]; t = _t(net)
    rng = np.random.default_rng(1880); draws = []
    for _ in range(1000):
        Xp = rng.permutation(X)                     # the predictor from a random other day
        mp, nn = rule_net(c, Y, Xp); draws.append(nn[mp].mean())
    pct = float((np.array(draws) < net.mean()).mean() * 100)
    mu0 = sd0 = c["net_bps"] / 2
    p0, p1 = 1 / sd0 ** 2, 1 / (net.std(ddof=1) ** 2 / len(net))
    post = (mu0 * p0 + net.mean() * p1) / (p0 + p1)
    yrs = np.array([d.year for d in Dm]); by_year = {int(y): float(net[yrs == y].mean()) for y in sorted(set(yrs))}
    pos = sum(v > 0 for v in by_year.values())
    ca, cb, cc, cd = t > T_CRIT, pct >= 95.0, post > 0, pos >= 3
    tier = "CONFIRM" if (ca and cb and cc and cd) else ("WATCHLIST" if net.mean() > 0 else "REJECT")
    title = f"{c['market']} last 30 minutes {c['rule']} the window so far ({'strong days' if c['form'] == 'strong' else 'every day'})"
    out = {"hypothesis": hid, "cell": title, "days": int(len(net)), "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct, "posterior": post,
           "by_year": by_year, "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc), "d": bool(cd)}, "decision": tier, "injection": inj}
    out_p.write_text(json.dumps(out, indent=1, default=float) + "\n")
    md_p.write_text("\n".join([f"# {hid} — {title}: the validation trial", "", f"**Decision: {tier}.** {len(net)} days, 2023-01 → 2026-08.", "",
        f"- (a) Net: **{net.mean():+.2f} bps**, t **{t:+.2f}**: {ca}. (b) placebo (predictor from random days) **{pct:.0f}th** pct: {cb}.",
        f"- (c) posterior {post:+.2f}: {cc}. (d) years positive {pos} of {len(by_year)} ({', '.join(f'{y} {v:+.2f}' for y, v in by_year.items())}): {cd}.",
        f"- Discovery (2018–22) net {c['net_bps']:+.2f} bps, t {c['t']:+.2f}, n {c['n']}. Z and D market-test 69.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol="FDXM", date_range=(str(Dm[0]), str(Dm[-1])), status="completed",
                           sharpe=float(net.mean() / net.std(ddof=1)), params={"statistic": f"close momentum: {title}; sealed 2023-2026; standalone net of cost; strict rule + tiers",
                                                                              "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 16, intraday momentum into the close, decisions.md 187-188); validated once on sealed data."))
    print(md_p.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_close")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
