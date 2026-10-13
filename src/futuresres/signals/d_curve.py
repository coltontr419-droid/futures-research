"""D82-D83 - the curve-shock tests carried by the family-28 discovery (decisions.md 221-222), validated ONCE on sealed 2023-01 ->
2026-08 data. hypotheses.yaml D82-D83.

    python -m futuresres.signals.d_curve --inject D82
    python -m futuresres.signals.d_curve --run D82
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d28_curve as d28

ROOT = Path(__file__).resolve().parents[3]
FIRST_ID = 82


def cells() -> dict:
    c = json.loads((ROOT / "reports" / "d28_discovery.json").read_text())["carried"]
    return {f"D{FIRST_ID + i}": x for i, x in enumerate(c)}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _p(hid):
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; D, R, X = d28.rows(c["target"], *d28.VAL); x = d28.net(c, R, X); noise = x - x.mean(); mu = c["net_bps"] / 2
    rng = np.random.default_rng(222 + int(hid[1:])); est = np.empty(reps); passes = 0
    for k in range(reps):
        z = rng.choice(noise, len(x), replace=True) + mu; est[k] = z.mean(); passes += _t(z) > T_CRIT
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
    D, R, X = d28.rows(c["target"], *d28.VAL); x = d28.net(c, R, X); t = _t(x)
    Dn, Rn, Xn = d28.rows(c["target"], *d28.VAL, shock=False); pool = d28.net(c, Rn, Xn)
    rng = np.random.default_rng(2220 + int(hid[1:])); draws = np.array([rng.choice(pool, len(x), replace=False).mean() for _ in range(1000)])
    pct = float((draws < x.mean()).mean() * 100)
    yrs = np.array([d.year for d in D]); by_year = {int(y): float(x[yrs == y].mean()) for y in sorted(set(yrs))}; pos = sum(v > 0 for v in by_year.values())
    ca, cb, cc = t > T_CRIT, pct >= 95.0, pos >= 3
    tier = "CONFIRM" if (ca and cb and cc) else ("WATCHLIST" if x.mean() > 0 else "REJECT")
    title = f"{c['target']} {c['rule']}s a yield-curve shock (next session)"
    out = {"hypothesis": hid, "cell": title, "trades": int(len(x)), "net_bps": float(x.mean()), "t_net": t, "placebo_pct": pct, "by_year": by_year,
           "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc)}, "decision": tier, "injection": inj}
    out_p.write_text(json.dumps(out, indent=1, default=float) + "\n")
    md_p.write_text("\n".join([f"# {hid} — {title}: the validation trial", "", f"**Decision: {tier}.** {len(x)} trades, 2023-01 → 2026-08.", "",
        f"- (a) Net **{x.mean():+.2f} bps**, t **{t:+.2f}**: {ca}. (b) placebo **{pct:.0f}th** pct: {cb}. (c) years positive {pos} of {len(by_year)} "
        f"({', '.join(f'{y} {v:+.1f}' for y, v in by_year.items())}): {cc}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=c["target"], date_range=(str(D[0]), str(D[-1])), status="completed",
                           sharpe=float(x.mean() / x.std(ddof=1)), params={"statistic": f"curve shock: {title}; sealed 2023-2026; net; strict rule + tiers",
                                                                          "net_bps": float(x.mean()), "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 28, yield-curve shocks, decisions.md 221-222); validated once on sealed data."))
    print(md_p.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_curve")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid")
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())
