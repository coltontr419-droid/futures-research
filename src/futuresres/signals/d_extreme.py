"""D53-D55 - the extreme-session tests carried by the family-12 discovery (decisions.md 177-178), each validated ONCE on sealed
2018-01 -> 2026-08 data, standalone. hypotheses.yaml D53-D55.

    python -m futuresres.signals.d_extreme --inject D53
    python -m futuresres.signals.d_extreme --run D53
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12

ROOT = Path(__file__).resolve().parents[3]
FIRST_ID, FIRST_TEST_NUMBER = 53, 65


def cells() -> dict:
    c = json.loads((ROOT / "reports" / "d12_discovery.json").read_text())["carried"]
    return {f"D{FIRST_ID + i}": x for i, x in enumerate(c)}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _p(hid):
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def setup(c):
    S = d10.series(); D, r, sig = d12.arrays(S, c["market"])
    dirn = 1 if c["rule"] == "follow" else -1; cost = d12.COST[c["market"]]
    tr = d12.trades(D, r, sig, c["h"], dirn, cost, *d12.VAL)
    assert all(d >= d12.VAL[0] for d, _ in tr)
    return D, r, sig, dirn, cost, tr


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; D, r, sig, dirn, cost, tr = setup(c)
    x = np.array([v for _, v in tr]); noise = x - x.mean(); mu = c["net_bps"] / 2
    rng = np.random.default_rng(178 + int(hid[1:])); est = np.empty(reps); passes = 0
    for k in range(reps):
        z = rng.choice(noise, len(x), replace=True) + mu
        est[k] = z.mean(); passes += _t(z) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"hypothesis": hid, "n_events": int(len(x)), "sought_bps": mu, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - mu) <= 3 * sd / math.sqrt(reps) + 0.5)}
    _p(hid)[0].write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial(hid: str) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; inj_p, out_p, md_p = _p(hid)
    inj = json.loads(inj_p.read_text()) if inj_p.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    D, r, sig, dirn, cost, tr = setup(c)
    x = np.array([v for _, v in tr]); t = _t(x)
    lo, hi = d12.VAL
    pool = [i for i in range(60, len(r) - c["h"]) if lo <= D[i] <= hi and np.isfinite(sig[i]) and abs(r[i]) <= 2 * sig[i]]
    rng = np.random.default_rng(1780 + int(hid[1:])); draws = []
    for _ in range(1000):
        st = sorted(rng.choice(pool, len(x), replace=False))
        rt = d12.trades(D, r, sig, c["h"], dirn, cost, lo, hi, starts=st)
        draws.append(np.mean([v for _, v in rt]) if rt else 0.0)
    pct = float((np.array(draws) < x.mean()).mean() * 100)
    mu0 = sd0 = c["net_bps"] / 2
    p0, p1 = 1 / sd0 ** 2, 1 / (x.std(ddof=1) ** 2 / len(x))
    post = (mu0 * p0 + x.mean() * p1) / (p0 + p1)
    yrs = np.array([d.year for d, _ in tr])
    eras = {lab: {"trades": int(m.sum()), "net_bps": float(x[m].mean()) if m.any() else float("nan"), "t": _t(x[m])}
            for lab, m in (("2018-20", yrs <= 2020), ("2021-26", yrs >= 2021))}
    up = np.array([1 if r[list(D).index(d) - 1] > 0 else 0 for d, _ in tr])
    sides = {"after up sessions": float(x[up == 1].mean()) if (up == 1).any() else float("nan"),
             "after down sessions": float(x[up == 0].mean()) if (up == 0).any() else float("nan"),
             "n_up": int(up.sum()), "n_down": int((up == 0).sum())}
    ca, cb, cc, cd = t > T_CRIT, pct >= 95.0, post > 0, eras["2021-26"]["net_bps"] > 0
    tier = "CONFIRM" if (ca and cb and cc and cd) else ("WATCHLIST" if x.mean() > 0 else "REJECT")
    title = f"{c['market']} {c['rule']}s a 2-sigma session over the next {c['h']}"
    out = {"hypothesis": hid, "cell": title, "trades": int(len(x)), "net_bps": float(x.mean()), "t_net": t, "placebo_pct": pct, "posterior": post,
           "eras": eras, "sides": sides, "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc), "d": bool(cd)}, "decision": tier,
           "z_d_market_test_number": FIRST_TEST_NUMBER + list(cells()).index(hid), "injection": inj}
    out_p.write_text(json.dumps(out, indent=1, default=float) + "\n")
    md_p.write_text("\n".join([f"# {hid} — {title}: the validation trial", "", f"**Decision: {tier}.** {len(x)} trades, 2018-01 → 2026-08.", "",
        f"- (a) Net of {cost} bps a session, against not trading: **{x.mean():+.2f} bps** a trade, t **{t:+.2f}**: {ca}.",
        f"- (b) Placebo (random non-event starts): **{pct:.0f}th** pct: {cb}. (c) posterior {post:+.2f}: {cc}.",
        f"- (d) 2021–26 {eras['2021-26']['net_bps']:+.2f} bps: {cd}; 2018–20 {eras['2018-20']['net_bps']:+.2f}.",
        f"- After up sessions {sides['after up sessions']:+.1f} bps (n {sides['n_up']}); after down sessions {sides['after down sessions']:+.1f} (n {sides['n_down']}).",
        f"- Discovery net {c['net_bps']:+.2f} bps, t {c['t']:+.2f}, {c['events']} trades.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=c["market"], date_range=(str(tr[0][0]), str(tr[-1][0])), status="completed",
                           sharpe=float(x.mean() / x.std(ddof=1)), params={"statistic": f"extreme session: {title}; sealed 2018-2026; standalone net of cost; strict rule + tiers",
                                                                          "net_bps": float(x.mean()), "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 12, after extreme sessions, decisions.md 177-178); validated once on sealed data."))
    print(md_p.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_extreme")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
