"""D152-D153 - family 115's intraday structures (decisions.md 433-434), each validated ONCE on sealed 2025-01 -> 2026-08 under
decisions.md 426, 2 (placebo: predictor signs shuffled across the sealed sessions).

    python -m futuresres.signals.d_intraday115 --inject D152
    python -m futuresres.signals.d_intraday115 --run D152
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d115_intraday as d115

ROOT = Path(__file__).resolve().parents[3]
FIRST_ID, FIRST_TEST_NUMBER = 152, 164


def cells() -> dict:
    c = json.loads((ROOT / "reports" / "d115_discovery.json").read_text())["carried"]
    return {f"D{FIRST_ID + i}": x for i, x in enumerate(c)}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _p(hid):
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def data(c):
    D, S, Y, _ = d115.cell_rows(c["market"], c["rule"], c["form"], *d115.VAL, med=c["median_abs"])
    return D, S, Y


def net_of(c, S, Y):
    return (1.0 if c["dir"] == "follow" else -1.0) * S * Y - d115.COST[c["market"]]


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; D, S, Y = data(c); assert D.min() >= d115.VAL[0]
    net = net_of(c, S, Y); noise = net - net.mean(); mu = c["net_bps"] / 2
    rng = np.random.default_rng(434 + int(hid[1:])); est = np.empty(reps); passes = 0
    for k in range(reps):
        z = rng.choice(noise, len(net), replace=True) + mu
        est[k] = z.mean(); passes += _t(z) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"hypothesis": hid, "n_events": int(len(net)), "sought_bps": mu, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - mu) <= 3 * sd / math.sqrt(reps) + 0.5)}
    _p(hid)[0].write_text(json.dumps(res, indent=1) + "\n")
    return 0 if res["recovered"] else 1


def run_trial(hid: str) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; inj_p, out_p, md_p = _p(hid)
    inj = json.loads(inj_p.read_text()) if inj_p.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    D, S, Y = data(c); net = net_of(c, S, Y); t = _t(net); rng = np.random.default_rng(4340 + int(hid[1:]))
    draws = np.array([net_of(c, rng.permutation(S), Y).mean() for _ in range(1000)])
    pct = float((draws < net.mean()).mean() * 100)
    yrs = np.array([d.year for d in D]); by_year = {int(y): float(net[yrs == y].mean()) for y in sorted(set(yrs))}
    ca, cb = t > T_CRIT, pct >= 95.0; cc = all(by_year.get(y, -1) > 0 for y in (2025, 2026))
    tier = "CONFIRM" if (ca and cb and cc) else ("WATCHLIST" if net.mean() > 0 else "REJECT")
    title = f"{c['market']} {c['rule']} ({c['form']}) {c['dir']} (current regime)"
    always = float((Y - d115.COST[c["market"]]).mean())
    out = {"hypothesis": hid, "cell": title, "trades": int(len(net)), "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct,
           "always_long_net_bps": always, "by_year": by_year, "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc)}, "decision": tier,
           "z_d_market_test_number": FIRST_TEST_NUMBER + list(cells()).index(hid), "injection": inj}
    out_p.write_text(json.dumps(out, indent=1, default=float) + "\n")
    md_p.write_text("\n".join([f"# {hid} — {title}: the validation trial", "", f"**Decision: {tier}.** {len(net)} sessions, 2025-01 → 2026-08.", "",
        f"- (a) Net **{net.mean():+.2f} bps**, t **{t:+.2f}**: {ca}. (b) placebo (shuffled signs) **{pct:.0f}th** pct: {cb}.",
        f"- (c) positive in 2025 and 2026 ({', '.join(f'{y} {v:+.2f}' for y, v in by_year.items())}): {cc}. Always long, same sessions: {always:+.2f}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=c["market"], date_range=(str(D[0]), str(D[-1])), status="completed",
                           sharpe=float(net.mean() / net.std(ddof=1)), params={"statistic": f"{title}; sealed 2025-2026; decisions.md 426 rule",
                                                                              "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 115, decisions.md 433-434); validated once on sealed data."))
    print(f"{hid} {title}: {tier} | n {len(net)} net {net.mean():+.2f} t {t:+.2f} pct {pct:.0f} | {by_year} | always-long {always:+.2f} | {rec['trial_id']}")
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_intraday115")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
