"""D39-D45 - the cross-market pairs carried by the family-10 discovery (decisions.md 171-172), each validated ONCE on sealed
2018-01 -> 2026-08 data. hypotheses.yaml D39-D45. Conditions as decisions.md 149, 5.

    python -m futuresres.signals.d_universe --inject D39
    python -m futuresres.signals.d_universe --run D39
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10

ROOT = Path(__file__).resolve().parents[3]
FIRST_ID, FIRST_TEST_NUMBER = 39, 51


def cells() -> dict:
    c = json.loads((ROOT / "reports" / "d10_discovery.json").read_text())["carried"]
    return {f"D{FIRST_ID + i}": x for i, x in enumerate(c)}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _p(hid):
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def data(c, S, shift=0):
    D, Y, X = d10.pairs(S, c["target"], c["predictor"], *d10.VAL, shift=shift)
    assert len(D) == 0 or D.min() >= d10.VAL[0]
    return D, Y, (1.0 if c["rule"] == "follow" else -1.0) * np.sign(X)


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; S = d10.series(); D, Y, dirn = data(c, S)
    ydm = Y - Y.mean(); mu = abs(c["mean_bps"]) / 2; n = len(Y)
    rng = np.random.default_rng(172 + int(hid[1:])); est = np.empty(reps); passes = 0
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
    S = d10.series(); D, Y, dirn = data(c, S)
    z = dirn * (Y - Y.mean()); diff = (dirn - 1.0) * Y; t_diff = _t(diff)
    shifted = []
    for k in [s for s in range(-11, 12) if abs(s) >= 2]:
        Ds, Ys, ds = data(c, S, shift=k); shifted.append(float((ds * (Ys - Ys.mean())).mean()))
    pct = float((np.array(shifted) < z.mean()).mean() * 100)
    mu0 = sd0 = abs(c["mean_bps"]) / 2
    p0, p1 = 1 / sd0 ** 2, 1 / (z.std(ddof=1) ** 2 / len(z))
    post = (mu0 * p0 + z.mean() * p1) / (p0 + p1)
    yrs = np.array([d.year for d in D])
    eras = {lab: {"days": int(m.sum()), "demeaned_bps": float(z[m].mean()), "t": _t(z[m]), "vs_long_bps": float(diff[m].mean())}
            for lab, m in (("2018-20", yrs <= 2020), ("2021-26", yrs >= 2021))}
    ca, cb, cc, cd = t_diff > T_CRIT, pct >= 95.0, post > 0, eras["2021-26"]["demeaned_bps"] > 0
    tier = "CONFIRM" if (ca and cb and cc and cd) else ("WATCHLIST" if z.mean() > 0 else "REJECT")
    title = f"{c['target']} {c['rule']}s the previous session of {c['predictor']}"
    out = {"hypothesis": hid, "cell": title, "days": int(len(z)), "demeaned_bps": float(z.mean()), "t_demeaned": _t(z),
           "vs_always_long_bps": float(diff.mean()), "t_vs_always_long": t_diff, "placebo_pct": pct, "posterior": post, "eras": eras,
           "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc), "d": bool(cd)}, "decision": tier,
           "z_d_market_test_number": FIRST_TEST_NUMBER + list(cells()).index(hid), "injection": inj}
    out_p.write_text(json.dumps(out, indent=1, default=float) + "\n")
    md_p.write_text("\n".join([f"# {hid} — {title}: the validation trial", "", f"**Decision: {tier}.** {len(z)} days, 2018-01 → 2026-08.", "",
        f"- Demeaned {z.mean():+.2f} bps (t {_t(z):+.2f}); (a) vs always-long {diff.mean():+.2f} bps, t {t_diff:+.2f}: {ca}.",
        f"- (b) placebo {pct:.0f}th pct: {cb}. (c) posterior {post:+.2f}: {cc}. (d) 2021–26 {eras['2021-26']['demeaned_bps']:+.2f}: {cd}; 2018–20 {eras['2018-20']['demeaned_bps']:+.2f}.",
        f"- Discovery {c['mean_bps']:+.2f} bps, t {c['t']:+.2f}, n {c['n']}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=c["target"], date_range=(str(D[0]), str(D[-1])), status="completed",
                           sharpe=float(z.mean() / z.std(ddof=1)), params={"statistic": f"cross-market: {title}; sealed 2018-2026; strict rule vs always-long + S8 + tiers",
                                                                          "demeaned_bps": float(z.mean()), "t_vs_always_long": t_diff, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 10, cross-market universe, decisions.md 171-172); validated once on sealed data."))
    print(md_p.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_universe")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
