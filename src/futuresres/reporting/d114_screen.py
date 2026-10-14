"""D-series family 114 - family 111's shock screen on the current regime (decisions.md 426-427): discovery 2021-01 -> 2024-12,
sealed validation 2025-01 -> 2026-08; carried at net > 0, t > 1.96.

    python -m futuresres.reporting.d114_screen --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d114_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
TARGETS = d111.TARGETS
rows = d111.rows


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for p in d111.OC + d111.CC + d111.FX + d111.FRED:
        for tg, cost in TARGETS.items():
            if not d111.eligible(p, tg):
                continue
            D, Y, X = rows(p, tg, *DISC)
            if len(Y) < 20:
                continue
            assert D.max() <= DISC[1], "discovery read sealed data"
            g = np.sign(X) * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            _, Yc, Xc = rows(p, tg, *CONTEXT); cc = dirn * np.sign(Xc) * Yc - cost
            r = {"predictor": p, "target": tg, "n": int(len(g)), "rule": "follow" if dirn == 1 else "fade", "net_bps": float(net.mean()), "t": _t(net),
                 "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"])
    carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_carries": round(0.025 * len(res), 1), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} carried by chance; carried {len(carried)}", flush=True)
    for r in carried:
        print(f"  {r['target']:3} after {r['predictor']:9} n {r['n']:3} {r['rule']:6} net {r['net_bps']:+7.2f} t {r['t']:+5.2f} | 2010-20 "
              f"{(r['context_net'] or float('nan')):+7.2f} t {(r['context_t'] or float('nan')):+5.2f}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    if ap.parse_args(argv).scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
