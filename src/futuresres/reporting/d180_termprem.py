"""D-series family 180 (decisions.md §1135): ACM 10-year term-premium shocks (> 2 sd) -> ZN / ES open -> close two sessions later.

    python -m futuresres.reporting.d180_termprem [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12

ROOT = Path(__file__).resolve().parents[3]
DISC = (dt.date(2010, 3, 1), dt.date(2022, 12, 31)); VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))


def events():
    x = pd.read_excel(ROOT / "data" / "treasury" / "acm.xls", sheet_name="ACM Daily")
    d = [dt.datetime.strptime(v, "%d-%b-%Y").date() for v in x["DATE"]]; tp = x["ACMTP10"].astype(float).to_numpy(); ch = np.diff(tp); d = d[1:]
    return [(d[i], ch[i]) for i in range(60, len(ch)) if abs(ch[i]) > 2 * ch[i - 60:i].std(ddof=1)]


def cell(S, E, tgt, rule, lo, hi):
    days = sorted(S[tgt]); x, al, sd = [], [], []
    for d, c in E:
        nxt = [v for v in days if v > d][:2]
        if len(nxt) < 2 or not (lo <= nxt[1] <= hi) or (nxt[1] - d).days > 6:
            continue
        side = -np.sign(c) * rule; y = S[tgt][nxt[1]]; k = d12.COST[tgt]
        x.append(side * y - k); al.append((side - 1) * y - (k if side < 0 else 0.0)); sd.append(side)
    return np.array(x), np.array(al), np.array(sd)


def t(x):
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def main(validate: bool) -> None:
    S = d10.series(); E = events(); out = {"cells": []}
    for tgt in ("ZN", "ES"):
        for rule, nm in ((1, "follow"), (-1, "fade")):
            x, _, _ = cell(S, E, tgt, rule, *DISC); r = {"target": tgt, "rule": nm, "n": len(x), "mean_bps": round(float(x.mean()), 2), "t": round(t(x), 2)}
            out["cells"].append(r); print("discovery", r)
            if validate and r["mean_bps"] > 0 and r["t"] > 1.96:
                x, al, sd = cell(S, E, tgt, rule, *VAL); y = (x + d12.COST[tgt]) * sd; rng = np.random.default_rng(1135); m = x.mean()
                pct = float((np.array([(np.roll(sd, rng.integers(1, len(sd))) * y - d12.COST[tgt]).mean() for _ in range(2000)]) < m).mean() * 100)
                v = "CONFIRM" if t(x) > 1.645 and t(al) > 1.645 and pct >= 95 else ("WATCHLIST" if m > 0 else "REJECT")
                r.update(sealed_n=len(x), sealed_mean=round(float(m), 2), sealed_t=round(t(x), 2), vs_long_t=round(t(al), 2), placebo=pct, decision=v); print("sealed", r)
    (ROOT / "reports" / f"d180_{'sealed' if validate else 'discovery'}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] == ["validate"])
