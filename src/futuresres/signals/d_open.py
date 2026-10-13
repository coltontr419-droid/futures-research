"""D101 - MNQ's day follows its opening minute (decisions.md 278-279), validated ONCE on sealed 2023-01 -> 2026-08 data,
standalone. hypotheses.yaml D101.

    python -m futuresres.signals.d_open --inject D101
    python -m futuresres.signals.d_open --run D101
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d52_open as d52

ROOT = Path(__file__).resolve().parents[3]
TEST_NUMBER = 113


def cell() -> dict:
    return json.loads((ROOT / "reports" / "d52_discovery.json").read_text())["carried"][0]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _p(hid):
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def data(c):
    D, X, Y, _ = d52.rows(c["market"], *d52.VAL); keep = np.sign(X) != 0
    return D[keep], np.sign(X[keep]), Y[keep]


def net_of(c, S, Y):
    return (1.0 if c["rule"] == "follow" else -1.0) * S * Y - d52.MARKETS[c["market"]][2]


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cell(); D, S, Y = data(c); assert D.min() >= d52.VAL[0]
    net = net_of(c, S, Y); noise = net - net.mean(); mu = c["net_bps"] / 2
    rng = np.random.default_rng(279); est = np.empty(reps); passes = 0
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
    c = cell(); inj_p, out_p, md_p = _p(hid)
    inj = json.loads(inj_p.read_text()) if inj_p.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    D, S, Y = data(c)
    net = net_of(c, S, Y); t = _t(net)
    rng = np.random.default_rng(2790)
    draws = np.array([net_of(c, rng.permutation(S), Y).mean() for _ in range(1000)])
    pct = float((draws < net.mean()).mean() * 100)
    always_long = float((Y - d52.MARKETS[c["market"]][2]).mean())
    yrs = np.array([d.year for d in D]); by_year = {int(y): float(net[yrs == y].mean()) for y in sorted(set(yrs))}
    pos = sum(v > 0 for v in by_year.values())
    ca, cb, cc = t > T_CRIT, pct >= 95.0, pos >= 3
    tier = "CONFIRM" if (ca and cb and cc) else ("WATCHLIST" if net.mean() > 0 else "REJECT")
    title = "MNQ day follows its opening minute"
    out = {"hypothesis": hid, "cell": title, "trades": int(len(net)), "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct,
           "always_long_net_bps": always_long, "by_year": by_year, "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc)},
           "decision": tier, "z_d_market_test_number": TEST_NUMBER, "injection": inj}
    out_p.write_text(json.dumps(out, indent=1, default=float) + "\n")
    md_p.write_text("\n".join([f"# {hid} — {title}: the validation trial", "", f"**Decision: {tier}.** {len(net)} sessions, 2023-01 → 2026-08.", "",
        f"- (a) Net: **{net.mean():+.2f} bps**, t **{t:+.2f}**: {ca}. (b) placebo (shuffled signs) **{pct:.0f}th** pct: {cb}.",
        f"- (c) years positive {pos} of {len(by_year)} ({', '.join(f'{y} {v:+.2f}' for y, v in by_year.items())}): {cc}.",
        f"- Always long over the same sessions: {always_long:+.2f} bps.",
        f"- Discovery (2018–22) net {c['net_bps']:+.2f}, t {c['t']:+.2f}, n {c['n']}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol="MNQ", date_range=(str(D[0]), str(D[-1])), status="completed",
                           sharpe=float(net.mean() / net.std(ddof=1)), params={"statistic": f"{title}; sealed 2023-2026; standalone net; strict rule + tiers",
                                                                              "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 52, decisions.md 278-279); validated once on sealed data."))
    print(md_p.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_open")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
