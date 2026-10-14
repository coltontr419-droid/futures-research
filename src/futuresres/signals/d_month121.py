"""D250-D264 - family 121 twenty-day cross-market direction rules (decisions.md 455-456), each validated ONCE on sealed
2025-01 -> 2026-08 under decisions.md 426, 2 (placebo: signs shuffled across the sealed sessions).

    python -m futuresres.signals.d_month121 --run-all
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d121_month as d121

ROOT = Path(__file__).resolve().parents[3]
FIRST_ID, FIRST_TEST_NUMBER = 250, 262


def cells() -> dict:
    c = json.loads((ROOT / "reports" / "d121_discovery.json").read_text())["carried"]
    return {f"D{FIRST_ID + i}": x for i, x in enumerate(c)}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def validate(hid: str) -> dict:
    from futuresres.signals.z_strict import T_CRIT
    from futuresres.stats.trials import Trial, TrialLog
    c = cells()[hid]; cost = d121.TARGETS[c["target"]]; sg = 1.0 if c["dir"] == "follow" else -1.0
    D, S, Y, _ = d121.rows(c["predictor"], c["target"], c["form"], *d121.VAL, med=c["median_abs"]); assert D.min() >= d121.VAL[0]
    net = sg * S * Y - cost
    rng = np.random.default_rng(456 + int(hid[1:])); mu = c["net_bps"] / 2; noise = net - net.mean()
    est = np.array([(rng.choice(noise, len(net)) + mu).mean() for _ in range(2000)])
    inj = {"hypothesis": hid, "n_events": int(len(net)), "sought_bps": mu, "mean_estimate": float(est.mean()),
           "recovered": bool(abs(est.mean() - mu) <= 3 * est.std(ddof=1) / math.sqrt(2000) + 0.5)}
    (ROOT / "reports" / f"{hid.lower()}_injection.json").write_text(json.dumps(inj, indent=1) + "\n")
    if not inj["recovered"]:
        raise SystemExit(f"{hid}: injection not recovered")
    t = _t(net); rng = np.random.default_rng(4560 + int(hid[1:]))
    draws = np.array([(sg * rng.permutation(S) * Y - cost).mean() for _ in range(1000)]); pct = float((draws < net.mean()).mean() * 100)
    yrs = np.array([d.year for d in D]); by = {int(y): float(net[yrs == y].mean()) for y in sorted(set(yrs))}
    ca, cb = t > T_CRIT, pct >= 95.0; cc = all(by.get(y, -1) > 0 for y in (2025, 2026))
    tier = "CONFIRM" if (ca and cb and cc) else ("WATCHLIST" if net.mean() > 0 else "REJECT")
    title = f"{c['target']} {c['dir']}s {c['predictor']} ({c['form']}, 20-day, current regime)"
    out = {"hypothesis": hid, "cell": title, "trades": int(len(net)), "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct, "by_year": by,
           "always_long_net_bps": float((Y - cost).mean()), "conditions": {"a": bool(ca), "b": bool(cb), "c": bool(cc)}, "decision": tier,
           "z_d_market_test_number": FIRST_TEST_NUMBER + list(cells()).index(hid), "injection": inj}
    (ROOT / "reports" / f"{hid.lower()}_trial.json").write_text(json.dumps(out, indent=1) + "\n")
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=c["target"], date_range=(str(D[0]), str(D[-1])), status="completed",
                           sharpe=float(net.mean() / net.std(ddof=1)), params={"statistic": f"{title}; sealed 2025-2026; decisions.md 426 rule",
                                                                              "net_bps": float(net.mean()), "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series family 121, decisions.md 455-456); validated once on sealed data."))
    out["trial_id"] = rec["trial_id"]
    print(f"{hid} {title}: {tier} | n {len(net)} net {net.mean():+.2f} t {t:+.2f} pct {pct:.0f} | " + ", ".join(f"{y} {v:+.1f}" for y, v in by.items()) + f" | {rec['trial_id']}", flush=True)
    return out


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "--run-all":
        for hid in cells():
            validate(hid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
