"""D95-D96 - the COT tests carried by the family-31 discovery (decisions.md 230-231), validated ONCE on sealed 2023-01 -> 2026-08.
hypotheses.yaml D95-D96.

    python -m futuresres.signals.d_cot --run D95       (week-clustered; the placebo shuffles the weekly signal)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d30_cot as d30
import futuresres.reporting.d31_cotgroups as d31

ROOT = Path(__file__).resolve().parents[3]
FIRST_ID, FIRST_TEST_NUMBER = 95, 107


def cells() -> dict:
    c = json.loads((ROOT / "reports" / "d31_discovery.json").read_text())["carried"]
    return {f"D{FIRST_ID + i}": x for i, x in enumerate(c)}


def run_trial(hid: str) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = cells()[hid]; S = d10.series(); sig = d30.weekly_signals(d31.positions(c["group"])[c["market"]])
    direction = 1 if c["rule"] == "follow" else -1
    tr = d30.trades(S, sig, c["market"], c["kind"], direction, *d30.VAL); assert all(d >= d30.VAL[0] for _, d, _ in tr)
    x = np.array([v for _, _, v in tr]); t = d30.clustered_t(tr)
    rng = np.random.default_rng(231 + int(hid[1:]))
    draws = [np.mean([v for _, _, v in d30.trades(S, sig, c["market"], c["kind"], direction, *d30.VAL, shuffle_rng=rng)] or [0.0]) for _ in range(1000)]
    pct = float((np.array(draws) < x.mean()).mean() * 100)
    yrs = np.array([d.year for _, d, _ in tr]); by_year = {int(y): float(x[yrs == y].mean()) for y in sorted(set(yrs))}; pos = sum(v > 0 for v in by_year.values())
    ca, cb, cc = t > T_CRIT, pct >= 95.0, pos >= 3
    tier = "CONFIRM" if (ca and cb and cc) else ("WATCHLIST" if x.mean() > 0 else "REJECT")
    title = f"{c['market']} {c['rule']}s {c['group']} {c['kind']} (next week)"
    out = {"hypothesis": hid, "cell": title, "sessions": int(len(x)), "net_bps": float(x.mean()), "t_week": t, "placebo_pct": pct, "by_year": by_year,
           "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc)}, "decision": tier, "z_d_market_test_number": FIRST_TEST_NUMBER + list(cells()).index(hid)}
    (ROOT / "reports" / f"{hid.lower()}_trial.json").write_text(json.dumps(out, indent=1) + "\n")
    md = "\n".join([f"# {hid} — {title}: the validation trial", "", f"**Decision: {tier}.** {len(x)} sessions, 2023-01 → 2026-08.", "",
                    f"- (a) Net **{x.mean():+.2f} bps** a session, week-clustered t **{t:+.2f}**: {ca}. (b) placebo (shuffled weeks) **{pct:.0f}th** pct: {cb}.",
                    f"- (c) years positive {pos} of {len(by_year)} ({', '.join(f'{y} {v:+.1f}' for y, v in by_year.items())}): {cc}.", ""])
    (ROOT / "reports" / f"{hid.lower()}_trial.md").write_text(md)
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=c["market"], date_range=(str(tr[0][1]), str(tr[-1][1])), status="completed",
                           sharpe=float(x.mean() / x.std(ddof=1)), params={"statistic": f"COT: {title}; sealed 2023-2026; net; strict rule + tiers",
                                                                          "net_bps": float(x.mean()), "t_week": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 31, COT groups, decisions.md 230-231); validated once on sealed data."))
    print(md); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_cot"); ap.add_argument("--run"); a = ap.parse_args(argv)
    return run_trial(a.run) if a.run else 0


if __name__ == "__main__":
    sys.exit(main())
