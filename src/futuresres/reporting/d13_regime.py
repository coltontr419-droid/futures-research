"""D-series family 13 - volatility regimes (decisions.md 180): in high / low recent volatility, does a window continue or
reverse its previous window or its pre-window move? Discovery 2018-01 -> 2022-12; validation 2023-01 -> 2026-08 sealed.

    python -m futuresres.reporting.d13_regime --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d13_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
PAIRS = [("NKD_win", "NKD_win", "prev"), ("NKD_win", "NKD_pre", "same"), ("DAX_win", "DAX_win", "prev"), ("DAX_win", "DAX_pre", "same"),
         ("MGC_win", "MGC_win", "prev"), ("MGC_win", "MGC_pre", "same"), ("MNQ_win", "MNQ_win", "prev"), ("MNQ_win", "MNQ_on", "same"),
         ("MCL", "MCL", "prev"), ("ZS", "ZS", "prev")]
COST = {"MNQ_win": 0.5, "MGC_win": 0.8, "MCL": 5.4, "NKD_win": 0.2, "DAX_win": 0.3, "ZS": 0.7}


def regime(S: dict, target: str) -> dict:
    """date -> 'high' / 'low', from the target's previous 20 returns against the median of that over its previous 250 days."""
    ds = sorted(S[target]); r = np.array([S[target][d] for d in ds])
    s20 = np.full(len(r), np.nan)
    for i in range(20, len(r)):
        s20[i] = r[i - 20:i].std(ddof=1)
    out = {}
    for i in range(270, len(r)):
        med = np.nanmedian(s20[i - 250:i])
        if np.isfinite(s20[i]) and np.isfinite(med):
            out[ds[i]] = "high" if s20[i] > med else "low"
    return out


def rows(S: dict, target: str, pred: str, when: str, reg: str, lo: dt.date, hi: dt.date, shift: int = 0):
    R = regime(S, target)
    D, Y, X = d3.pairs(S, target, pred, when, lo, hi)
    if shift:
        n = len(D); idx = np.arange(n) - shift; keep = (idx >= 0) & (idx < n)
        D, Y, X = D[keep], Y[keep], X[np.clip(idx, 0, n - 1)][keep]
    m = np.array([R.get(d) == reg for d in D], bool)
    return D[m], Y[m], X[m]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    S = d3.series(); res = []
    for tg, pr, when in PAIRS:
        for reg in ("high", "low"):
            D, Y, X = rows(S, tg, pr, when, reg, *DISC)
            assert D.max() <= DISC[1] and D.min() >= DISC[0]
            z = np.sign(X) * (Y - Y.mean())
            res.append({"target": tg, "predictor": pr, "when": when, "regime": reg, "n": int(len(z)), "mean_bps": float(z.mean()),
                        "t": _t(z), "rule": "follow" if z.mean() > 0 else "fade"})
    res.sort(key=lambda r: -abs(r["t"]))
    carried = [r for r in res if abs(r["t"]) > 1.96]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_passes_5pct": round(0.05 * len(res), 1),
           "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests on {DISC[0]} -> {DISC[1]}; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res:
        print(f"  {r['target']:8} <- {r['predictor']:8} ({r['when']:4}) {r['regime']:4} vol  n {r['n']:4} {r['rule']:6} mean {r['mean_bps']:+7.2f} bps "
              f"t {r['t']:+5.2f}{'  CARRIED' if abs(r['t']) > 1.96 else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
