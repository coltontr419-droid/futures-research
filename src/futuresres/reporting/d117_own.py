"""D-series family 117 - each plan market's own past on the current regime (decisions.md 438)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d117_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
TARGETS = d111.TARGETS
KINDS = ("own_shock", "trend5", "trend20")


def rows(tg: str, kind: str, lo, hi):
    Y = d111.target(tg); ds = sorted(Y); r = np.array([Y[d] for d in ds]); D, S, YY = [], [], []
    for i in range(61, len(ds)):
        if not (lo <= ds[i] <= hi):
            continue
        if kind == "own_shock":
            sd = r[i - 61:i - 1].std(ddof=1); x = r[i - 1] if abs(r[i - 1]) > 2 * sd else 0.0
        elif kind == "trend5":
            x = r[i - 5:i].sum()
        else:
            x = r[i - 20:i].sum()
        if x == 0:
            continue
        D.append(ds[i]); S.append(np.sign(x)); YY.append(r[i])
    return np.array(D), np.array(S), np.array(YY)


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for tg, cost in TARGETS.items():
        for k in KINDS:
            D, S, Y = rows(tg, k, *DISC); g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            _, Sc, Yc = rows(tg, k, *CONTEXT); cc = dirn * Sc * Yc - cost
            r = {"target": tg, "kind": k, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade", "net_bps": float(net.mean()), "t": _t(net),
                 "context_net": float(cc.mean()), "context_t": _t(cc)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
            print(f"{tg:3} {k:9}: n {r['n']:4} {r['dir']:6} net {r['net_bps']:+7.2f} t {r['t']:+5.2f}{'  CARRIED' if r['carried'] else ''} | 2010-20 {r['context_net']:+7.2f} t {r['context_t']:+5.2f}", flush=True)
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


if __name__ == "__main__":
    scan()
