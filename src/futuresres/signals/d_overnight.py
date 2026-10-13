"""D22-D27 - the overnight-state tests carried by the family-4 discovery (decisions.md 152-153), each validated ONCE on sealed
2018-01 -> 2026-08 data. hypotheses.yaml D22-D27. Conditions exactly as d_relay (decisions.md 149, 5).

    python -m futuresres.signals.d_overnight --inject D22
    python -m futuresres.signals.d_overnight --run D22
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d4_overnight as d4

ROOT = Path(__file__).resolve().parents[3]
DISC_JSON = ROOT / "reports" / "d4_discovery.json"
FIRST_ID, FIRST_TEST_NUMBER = 22, 34


def cells() -> dict:
    c = json.loads(DISC_JSON.read_text())["carried"]
    return {f"D{FIRST_ID + i}": x for i, x in enumerate(c)}


def _gate(c):
    g = c["gate"]
    return tuple(g) if isinstance(g, list) else g


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _paths(hid):
    s = hid.lower()
    return (ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md")


def data(c: dict, F: dict, shift: int = 0):
    """Validation days the rule acts on: dates, raw target, direction. `shift` moves the predictor (and its gate) by that many
    trading days in the market's own calendar (the placebo)."""
    D, Y, X, G = d4.rows(F, tuple(c["predictor"]), *d4.VAL)
    assert len(D) == 0 or D.min() >= d4.VAL[0]
    ok = np.isfinite(X); D, Y, X = D[ok], Y[ok], X[ok]; G = [g for g, k in zip(G, ok) if k]
    if shift:
        n = len(D); idx = np.arange(n) - shift
        keep = (idx >= 0) & (idx < n)
        X = np.where(keep, X[np.clip(idx, 0, n - 1)], np.nan); G = [G[i] if k else {} for i, k in zip(np.clip(idx, 0, n - 1), keep)]
        ok = np.isfinite(X); D, Y, X = D[ok], Y[ok], X[ok]; G = [g for g, k in zip(G, ok) if k]
    m = d4.gate_mask(_gate(c), X, G, c["thresholds"])
    s = 1.0 if c["rule"] == "follow" else -1.0
    return D[m], Y[m], s * np.sign(X[m])


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; F = d4.frame(c["market"])
    D, Y, dirn = data(c, F)
    ydm = Y - Y.mean(); mu = abs(c["mean_bps"]) / 2; n = len(Y)
    rng = np.random.default_rng(153 + int(hid[1:])); est = np.empty(reps); passes = 0
    for k in range(reps):
        z = rng.choice(ydm, n, replace=True) * rng.choice([-1.0, 1.0], n) + mu
        est[k] = z.mean(); passes += _t(z) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"hypothesis": hid, "n_events": n, "sought_bps": mu, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - mu) <= 3 * sd / math.sqrt(reps) + 0.1)}
    _paths(hid)[0].write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial(hid: str) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; inj_path, out_path, md_path = _paths(hid)
    inj = json.loads(inj_path.read_text()) if inj_path.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    F = d4.frame(c["market"])
    D, Y, dirn = data(c, F)
    z = dirn * (Y - Y.mean()); diff = (dirn - 1.0) * Y; t_diff = _t(diff)
    shifted = []
    for k in [s for s in range(-11, 12) if abs(s) >= 2]:
        Ds, Ys, ds = data(c, F, shift=k)
        shifted.append(float((ds * (Ys - Ys.mean())).mean()))
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
    g = c["gate"]; gs = "every day" if g is None else ("strong days" if g == "strong" else ("entry outside the previous window's range" if g == "outside" else f"{g[0]} {g[1]} above median"))
    title = f"{c['market']} {c['rule']}s {c['test'].split('|')[0]} ({gs})"
    out = {"hypothesis": hid, "cell": title, "window": [str(D[0]), str(D[-1])], "days": int(len(z)),
           "demeaned_bps": float(z.mean()), "t_demeaned": _t(z), "vs_always_long_bps": float(diff.mean()), "t_vs_always_long": t_diff,
           "hit_rate": float((z > 0).mean()), "placebo_pct": pct, "shifted_means": shifted, "prior": [mu0, sd0],
           "posterior_bps": {"registered_prior": post, "zero_prior": post0}, "eras": eras,
           "discovery": {k: c[k] for k in ("n", "mean_bps", "t")},
           "conditions": {"vs_long_t_gt_1.645": bool(ca), "placebo_ge_95": bool(cb), "posterior_gt_0": bool(cc), "post2021_gt_0": bool(cd)},
           "z_d_market_test_number": number, "decision": tier, "injection": inj}
    out_path.write_text(json.dumps(out, indent=1, default=float) + "\n")
    rows = ["| period | days | demeaned bps | t | vs always-long bps |", "|---|---|---|---|---|"] + \
        [f"| {k} | {e['days']} | {e['demeaned_bps']:+.2f} | {e['t']:+.2f} | {e['vs_long_bps']:+.2f} |" for k, e in eras.items()]
    md_path.write_text("\n".join([
        f"# {hid} — {title}: the validation trial", "",
        f"**Decision: {tier}.** {len(z)} days, {out['window'][0]} → {out['window'][1]} (sealed until registration).", "",
        f"- Demeaned (skill beyond drift): **{z.mean():+.2f} bps** a day, t {_t(z):+.2f}; hit rate {out['hit_rate']:.0%}.",
        f"- (a) Against always-long, raw: **{diff.mean():+.2f} bps** a day, t **{t_diff:+.2f}** (needs > 1.645): {ca}.",
        f"- (b) Placebo, predictor shifted ±2…±11 days: real at the **{pct:.0f}th** pct (needs ≥ 95): {cb}.",
        f"- (c) Posterior {post:+.2f} bps (prior Normal({mu0:.2f}, {sd0:.2f}); zero prior {post0:+.2f}): {cc}.",
        f"- (d) 2021–26 alone {eras['2021-26']['demeaned_bps']:+.2f} bps (needs > 0): {cd}.",
        f"- Discovery (2010–17): {c['mean_bps']:+.2f} bps, t {c['t']:+.2f}, n {c['n']}. Z and D market-test number {number}.", "",
        *rows, "",
        f"Outcome injection: {inj['sought_bps']:.2f} bp planted, recovered {inj['mean_estimate']:.2f} (SD {inj['sd_estimate_bps']:.2f}); "
        f"power of the strict t {inj['power_strict_t']:.0%}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=c["market"], date_range=(out["window"][0], out["window"][1]),
                           status="completed", sharpe=float(z.mean() / z.std(ddof=1)),
                           params={"statistic": f"overnight state: {title}; sealed 2018-2026; strict rule vs always-long + S8 + tiers",
                                   "demeaned_bps": out["demeaned_bps"], "t_vs_always_long": t_diff, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 4, the overnight state, decisions.md 152-153); validated once on sealed data."))
    print(md_path.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_overnight")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
