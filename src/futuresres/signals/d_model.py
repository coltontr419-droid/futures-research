"""D58-D63 - the six frozen family-19 models (decisions.md 194-195), each scored ONCE on sealed 2023-01 -> 2026-08 data.
hypotheses.yaml D58-D63.

    python -m futuresres.signals.d_model --run D58      (no injection: the model is frozen; the placebo is the control)
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d19_model as d19
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
IDS = {f"D{58 + i}": t for i, t in enumerate(d19.TARGETS)}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def run_trial(hid: str) -> int:
    from futuresres.signals.z_strict import T_CRIT
    target = IDS[hid]; model = json.loads(d19.OUT.read_text())[target]
    D, Y, X, _ = d19.features(d3.series(), target)
    m = np.array([d19.VAL[0] <= d <= d19.VAL[1] for d in D]); D, Y, X = D[m], Y[m], X[m]
    assert D.min() >= d19.VAL[0]
    pred = d19.predict(model, X); s = np.sign(pred); s[s == 0] = 1.0
    cost = d19.COST[target]; net = s * Y - cost; t = _t(net)
    rng = np.random.default_rng(195 + int(hid[1:]))
    draws = [(np.sign(d19.predict(model, X[rng.permutation(len(X))])) * Y - cost).mean() for _ in range(1000)]
    pct = float((np.array(draws) < net.mean()).mean() * 100)
    diff = (s - 1.0) * Y; t_long = _t(diff)
    yrs = np.array([d.year for d in D]); by_year = {int(y): float(net[yrs == y].mean()) for y in sorted(set(yrs))}
    pos = sum(v > 0 for v in by_year.values())
    need_long = model["train_mean_y"] > 0
    ca, cb, cc, cd = t > T_CRIT, pct >= 95.0, (t_long > T_CRIT) if need_long else True, pos >= 3
    tier = "CONFIRM" if (ca and cb and cc and cd) else ("WATCHLIST" if net.mean() > 0 else "REJECT")
    out = {"hypothesis": hid, "target": target, "days": int(len(net)), "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct,
           "vs_always_long_bps": float(diff.mean()), "t_vs_always_long": t_long, "always_long_required": bool(need_long), "share_long": float((s > 0).mean()),
           "by_year": by_year, "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc), "d": bool(cd)}, "decision": tier}
    (ROOT / "reports" / f"{hid.lower()}_trial.json").write_text(json.dumps(out, indent=1) + "\n")
    md = "\n".join([f"# {hid} — the combined model for {target}: the validation trial", "", f"**Decision: {tier}.** {len(net)} days, 2023-01 → 2026-08.", "",
        f"- (a) Net of {cost} bps: **{net.mean():+.2f} bps** a day, t **{t:+.2f}**: {ca}. Long on {out['share_long']:.0%} of days.",
        f"- (b) Placebo (features of random days): **{pct:.0f}th** pct: {cb}. (c) vs always-long {diff.mean():+.2f} bps, t {t_long:+.2f} "
        f"(required: {need_long}): {cc}. (d) years positive {pos} of {len(by_year)} ({', '.join(f'{y} {v:+.1f}' for y, v in by_year.items())}): {cd}.", ""])
    (ROOT / "reports" / f"{hid.lower()}_trial.md").write_text(md)
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    sym = {"NKD_win": "NKD", "DAX_win": "FDXM", "MGC_win": "MGC", "MNQ_win": "MNQ", "MCL": "MCL", "ZS": "ZS"}[target]
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=sym, date_range=(str(D[0]), str(D[-1])), status="completed",
                           sharpe=float(net.mean() / net.std(ddof=1)), params={"statistic": f"frozen ridge model, {target}; sealed 2023-2026; net of cost; strict rule + tiers",
                                                                              "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 19, combined models, decisions.md 194-195); scored once on sealed data."))
    print(md); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_model"); ap.add_argument("--run"); a = ap.parse_args(argv)
    return run_trial(a.run) if a.run else 0


if __name__ == "__main__":
    sys.exit(main())
