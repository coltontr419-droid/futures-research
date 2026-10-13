"""D37-D38 - the release-day tests carried by the family-9 discovery (decisions.md 168-169): gold fades its first 5 / 15 minutes
after an 08:30 New York release, to 11:30. Validated ONCE on sealed 2018-01 -> 2026-08 data. hypotheses.yaml D37-D38.

    python -m futuresres.signals.d_events --inject D37
    python -m futuresres.signals.d_events --run D37
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d9_events as d9

ROOT = Path(__file__).resolve().parents[3]
FIRST_ID, FIRST_TEST_NUMBER = 37, 49


def cells() -> dict:
    c = json.loads((ROOT / "reports" / "d9_discovery.json").read_text())["carried"]
    return {f"D{FIRST_ID + i}": x for i, x in enumerate(c)}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _p(hid):
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def sample(c: dict):
    rows = [r for r in d9.event_days(c["event"]) if d9.VAL[0] <= r["date"] <= d9.VAL[1]]
    assert all(r["date"] >= d9.VAL[0] for r in rows)
    k = c["k"]; rule = 1.0 if c["rule"] == "follow" else -1.0
    rel = [r for r in rows if r["release"]]; non = [r for r in rows if not r["release"]]
    def arr(rs):
        X = np.array([r[f"x{k}"] for r in rs]); Y = np.array([r[f"y{k}"] for r in rs]); D = [r["date"] for r in rs]
        m = np.ones(len(X), bool) if c["form"] == "all" else np.abs(X) > c["median_abs_pred"]
        return [d for d, ok in zip(D, m) if ok], X[m], Y[m]
    return arr(rel), arr(non), rule


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; (D, X, Y), _, rule = sample(c); cost = d9.COST[c["market"]]
    z0 = rule * np.sign(X) * Y; noise = (z0 - z0.mean()) * 1.0; mu = abs(c["mean_pts_demeaned"]) / 2
    rng = np.random.default_rng(169 + int(hid[1:])); est = np.empty(reps); passes = 0
    for k in range(reps):
        z = rng.choice(noise, len(z0), replace=True) * rng.choice([-1.0, 1.0], len(z0)) + mu + cost
        net = z - cost; est[k] = net.mean() - cost * 0 ; passes += _t(net) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"hypothesis": hid, "n_events": int(len(z0)), "sought_pts_net": mu, "mean_estimate": float(est.mean()), "sd_estimate": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - mu) <= 3 * sd / math.sqrt(reps) + 0.05)}
    _p(hid)[0].write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial(hid: str) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; inj_p, out_p, md_p = _p(hid)
    inj = json.loads(inj_p.read_text()) if inj_p.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    (D, X, Y), (Dn, Xn, Yn), rule = sample(c); cost = d9.COST[c["market"]]
    net = rule * np.sign(X) * Y - cost; t = _t(net)
    netn = rule * np.sign(Xn) * Yn - cost
    rng = np.random.default_rng(1690 + int(hid[1:]))
    draws = np.array([rng.choice(netn, len(net), replace=False).mean() for _ in range(1000)])
    pct = float((draws < net.mean()).mean() * 100)
    mu0 = sd0 = abs(c["mean_pts_demeaned"]) / 2
    p0, p1 = 1 / sd0 ** 2, 1 / (net.std(ddof=1) ** 2 / len(net))
    post = (mu0 * p0 + net.mean() * p1) / (p0 + p1)
    yrs = np.array([d.year for d in D])
    eras = {lab: {"events": int(m.sum()), "net_pts": float(net[m].mean()), "t": _t(net[m])} for lab, m in (("2018-20", yrs <= 2020), ("2021-26", yrs >= 2021))}
    ca, cb, cc, cd = t > T_CRIT, pct >= 95.0, post > 0, eras["2021-26"]["net_pts"] > 0
    tier = "CONFIRM" if (ca and cb and cc and cd) else ("WATCHLIST" if net.mean() > 0 else "REJECT")
    title = f"{c['event']}: {c['market']} {c['rule']}s its first {c['k']} minutes to the session end ({'every release day' if c['form'] == 'all' else 'strong'})"
    out = {"hypothesis": hid, "cell": title, "events": int(len(net)), "net_pts": float(net.mean()), "t_net": t, "placebo_pct": pct,
           "non_release_net_pts": float(netn.mean()), "posterior": post, "eras": eras,
           "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc), "d": bool(cd)}, "decision": tier,
           "z_d_market_test_number": FIRST_TEST_NUMBER + list(cells()).index(hid), "injection": inj}
    out_p.write_text(json.dumps(out, indent=1, default=float) + "\n")
    md_p.write_text("\n".join([f"# {hid} — {title}: the validation trial", "",
        f"**Decision: {tier}.** {len(net)} release days, 2018-01 → 2026-08 (sealed until registration).", "",
        f"- (a) Net of {cost} pts a round trip: **{net.mean():+.2f} pts** a trade, t **{t:+.2f}** (needs > 1.645): {ca}.",
        f"- (b) Placebo, the same rule on random non-release days at the same clock: real at the **{pct:.0f}th** pct (needs ≥ 95): {cb}.",
        f"- (c) Posterior {post:+.2f}: {cc}. (d) 2021–26 {eras['2021-26']['net_pts']:+.2f} pts (needs > 0): {cd}; 2018–20 {eras['2018-20']['net_pts']:+.2f}.",
        f"- Discovery (2013–17): {c['mean_pts_demeaned']:+.2f} pts demeaned, t {c['t']:+.2f}, n {c['n']}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=c["market"], date_range=(str(D[0]), str(D[-1])), status="completed",
                           sharpe=float(net.mean() / net.std(ddof=1)), params={"statistic": f"release drift: {title}; sealed 2018-2026; net of costs; strict rule + tiers",
                                                                              "net_pts": float(net.mean()), "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 9, release-day drift, decisions.md 168-169); validated once on sealed data."))
    print(md_p.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_events")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
