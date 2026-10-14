"""D124 - copper falls after the Chilean peso weakens (decisions.md 384-385), each validated ONCE on sealed 2023-01 -> 2026-08.

    python -m futuresres.signals.d_producer --inject D124
    python -m futuresres.signals.d_producer --run D124
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d98_producer as d98

ROOT = Path(__file__).resolve().parents[3]
FIRST_ID, FIRST_TEST_NUMBER = 124, 136


def cells() -> dict:
    c = json.loads((ROOT / "reports" / "d98_discovery.json").read_text())["carried"]
    return {f"D{FIRST_ID + i}": x for i, x in enumerate(c)}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _p(hid):
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def net_of(c, Y, X):
    return (1.0 if c["rule"] == "with local weakness" else -1.0) * np.sign(X) * Y - d98.COST[c["target"]]


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; D, Y, X = d98.rows(c["currency"], *d98.VAL); assert D.min() >= d98.VAL[0]
    net = net_of(c, Y, X); noise = net - net.mean(); mu = c["net_bps"] / 2
    rng = np.random.default_rng(385 + int(hid[1:])); est = np.empty(reps); passes = 0
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
    D, Y, X = d98.rows(c["currency"], *d98.VAL); net = net_of(c, Y, X); t = _t(net)
    _, Yn, Xn = d98.rows(c["currency"], *d98.VAL, shock=False); pool = net_of(c, Yn, Xn); rng = np.random.default_rng(3850 + int(hid[1:]))
    draws = np.array([rng.choice(pool, len(net), replace=False).mean() for _ in range(1000)])
    pct = float((draws < net.mean()).mean() * 100)
    yrs = np.array([d.year for d in D]); by_year = {int(y): float(net[yrs == y].mean()) for y in sorted(set(yrs))}
    pos = sum(v > 0 for v in by_year.values())
    ca, cb, cc = t > T_CRIT, pct >= 95.0, pos >= 3
    tier = "CONFIRM" if (ca and cb and cc) else ("WATCHLIST" if net.mean() > 0 else "REJECT")
    title = f"{c['target']} falls after the producer currency ({c['currency']}) weakens"
    out = {"hypothesis": hid, "cell": title, "trades": int(len(net)), "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct,
           "by_year": by_year, "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc)}, "decision": tier,
           "z_d_market_test_number": FIRST_TEST_NUMBER + list(cells()).index(hid), "injection": inj}
    out_p.write_text(json.dumps(out, indent=1, default=float) + "\n")
    md_p.write_text("\n".join([f"# {hid} — {title}: the validation trial", "", f"**Decision: {tier}.** {len(net)} trades, 2023-01 → 2026-08.", "",
        f"- (a) Net: **{net.mean():+.2f} bps**, t **{t:+.2f}**: {ca}. (b) placebo (non-shock days) **{pct:.0f}th** pct: {cb}.",
        f"- (c) years positive {pos} of {len(by_year)} ({', '.join(f'{y} {v:+.1f}' for y, v in by_year.items())}): {cc}.",
        f"- Discovery (2018–22) net {c['net_bps']:+.2f}, t {c['t']:+.2f}, n {c['n']}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=c["target"], date_range=(str(D[0]), str(D[-1])), status="completed",
                           sharpe=float(net.mean() / net.std(ddof=1)), params={"statistic": f"{title}; sealed 2023-2026; standalone net; strict rule + tiers",
                                                                              "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 98, decisions.md 384-385); validated once on sealed data."))
    print(md_p.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_producer")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
