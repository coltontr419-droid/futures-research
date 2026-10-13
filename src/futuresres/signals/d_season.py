"""D46-D52 - the seasonal cells carried by the family-11 discovery (decisions.md 174-175), each validated ONCE on sealed
2018-01 -> 2026-08 data, as STANDALONE strategies (against not trading, net of cost). hypotheses.yaml D46-D52.

    python -m futuresres.signals.d_season --inject D46
    python -m futuresres.signals.d_season --run D46
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d11_season as d11

ROOT = Path(__file__).resolve().parents[3]
FIRST_ID, FIRST_TEST_NUMBER = 46, 58


def cells() -> dict:
    c = json.loads((ROOT / "reports" / "d11_discovery.json").read_text())["carried"]
    return {f"D{FIRST_ID + i}": x for i, x in enumerate(c)}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _p(hid):
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def data(c):
    S = d11.series(c["market"])
    D, Y, other = d11.month_days(S, c["month"], *d11.VAL)
    assert D.min() >= d11.VAL[0]
    s = 1.0 if c["direction"] == "long" else -1.0
    return D, s * Y - c["cost_bps"], s * other - c["cost_bps"]


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; D, net, other = data(c)
    noise = other - other.mean(); mu = abs(c["mean_bps"]) / 2 - c["cost_bps"]
    rng = np.random.default_rng(175 + int(hid[1:])); est = np.empty(reps); passes = 0
    for k in range(reps):
        z = rng.choice(noise, len(net), replace=True) + mu
        est[k] = z.mean(); passes += _t(z) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"hypothesis": hid, "n_events": int(len(net)), "sought_bps": mu, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - mu) <= 3 * sd / math.sqrt(reps) + 0.5)}
    _p(hid)[0].write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial(hid: str) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; inj_p, out_p, md_p = _p(hid)
    inj = json.loads(inj_p.read_text()) if inj_p.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    D, net, other = data(c); t = _t(net)
    rng = np.random.default_rng(1750 + int(hid[1:]))
    draws = np.array([rng.choice(other, len(net), replace=False).mean() for _ in range(1000)])
    pct = float((draws < net.mean()).mean() * 100)
    mu0 = sd0 = abs(c["mean_bps"]) / 2
    p0, p1 = 1 / sd0 ** 2, 1 / (net.std(ddof=1) ** 2 / len(net))
    post = (mu0 * p0 + net.mean() * p1) / (p0 + p1)
    yrs = np.array([d.year for d in D])
    eras = {lab: {"days": int(m.sum()), "net_bps": float(net[m].mean()), "t": _t(net[m])} for lab, m in (("2018-20", yrs <= 2020), ("2021-26", yrs >= 2021))}
    by_year = {int(y): float(net[yrs == y].mean()) for y in sorted(set(yrs))}
    ca, cb, cc, cd = t > T_CRIT, pct >= 95.0, post > 0, eras["2021-26"]["net_bps"] > 0
    tier = "CONFIRM" if (ca and cb and cc and cd) else ("WATCHLIST" if net.mean() > 0 else "REJECT")
    title = f"{c['market']} {c['direction']} every session in {d11.MONTHS[c['month'] - 1]}"
    out = {"hypothesis": hid, "cell": title, "days": int(len(net)), "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct, "posterior": post,
           "eras": eras, "by_year": by_year, "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc), "d": bool(cd)}, "decision": tier,
           "z_d_market_test_number": FIRST_TEST_NUMBER + list(cells()).index(hid), "injection": inj}
    out_p.write_text(json.dumps(out, indent=1, default=float) + "\n")
    md_p.write_text("\n".join([f"# {hid} — {title}: the validation trial", "", f"**Decision: {tier}.** {len(net)} sessions, 2018-01 → 2026-08.", "",
        f"- (a) Net of {c['cost_bps']} bps a day, against not trading: **{net.mean():+.2f} bps** a session, t **{t:+.2f}**: {ca}.",
        f"- (b) Placebo, the same trade on other months' days: real at the **{pct:.0f}th** pct: {cb}. (c) posterior {post:+.2f}: {cc}.",
        f"- (d) 2021–26 {eras['2021-26']['net_bps']:+.2f} bps: {cd}; 2018–20 {eras['2018-20']['net_bps']:+.2f}. By year: "
        + ", ".join(f"{y} {v:+.0f}" for y, v in by_year.items()) + ".",
        f"- Discovery {c['mean_bps']:+.2f} bps, t {c['t']:+.2f}, n {c['n']}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=c["market"], date_range=(str(D[0]), str(D[-1])), status="completed",
                           sharpe=float(net.mean() / net.std(ddof=1)), params={"statistic": f"seasonality: {title}; sealed 2018-2026; standalone net of cost; strict rule + tiers",
                                                                              "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 11, commodity seasonality, decisions.md 174-175); validated once on sealed data."))
    print(md_p.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_season")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
