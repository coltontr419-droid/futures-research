"""D-series family 177 (decisions.md §1127): EIA weekly gas-storage change vs its 5-year same-week norm -> NG's next 5 weekdays (open -> close).

    python -m futuresres.reporting.d177_ngstorage [validate]
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
DISC = (dt.date(2015, 1, 1), dt.date(2022, 12, 31)); VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))


def weeks():
    x = pd.read_excel(ROOT / "data" / "ng" / "storage.xls", sheet_name="Data 1", skiprows=2)
    x.columns = ["date", "bcf"] + list(x.columns[2:]); x = x[["date", "bcf"]].dropna()
    d = [pd.Timestamp(v).date() for v in x["date"]]; b = x["bcf"].astype(float).to_numpy(); ch = np.diff(b); d = d[1:]
    wk = [v.isocalendar()[1] for v in d]; out = []
    for i, v in enumerate(d):
        prior = [ch[j] for j in range(i) if wk[j] == wk[i] and 0 < v.year - d[j].year <= 5]
        if len(prior) == 5:
            out.append((v + dt.timedelta(days=6), ch[i] - np.mean(prior)))   # release Thursday
    return out


def cell(S, W, rule, lo, hi):
    days = sorted(S["NG"]); x, al, sd = [], [], []
    for rel, u in W:
        if not (lo <= rel <= hi):
            continue
        nxt = [d for d in days if rel < d <= rel + dt.timedelta(days=7)][:5]
        if len(nxt) < 4:
            continue
        y = sum(S["NG"][d] for d in nxt); side = (-1.0 if u > 0 else 1.0) * rule; c = d12.COST["NG"] * len(nxt)
        x.append(side * y - c); al.append((side - 1) * y - (c if side < 0 else 0.0)); sd.append(side)
    return np.array(x), np.array(al), np.array(sd)


def t(x):
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def main(validate: bool) -> None:
    S = d10.series(); W = weeks(); out = {"cells": []}
    for rule, nm in ((1, "follow"), (-1, "fade")):
        x, _, _ = cell(S, W, rule, *DISC); r = {"rule": nm, "n": len(x), "mean_bps": round(float(x.mean()), 1), "t": round(t(x), 2)}
        out["cells"].append(r); print("discovery", r)
        if validate and r["mean_bps"] > 0 and r["t"] > 1.96:
            x, al, sd = cell(S, W, rule, *VAL); y = (x + d12.COST["NG"] * 5) * sd; rng = np.random.default_rng(1127); m = x.mean()
            pct = float((np.array([(np.roll(sd, rng.integers(1, len(sd))) * y - d12.COST["NG"] * 5).mean() for _ in range(2000)]) < m).mean() * 100)
            v = "CONFIRM" if t(x) > 1.645 and t(al) > 1.645 and pct >= 95 else ("WATCHLIST" if m > 0 else "REJECT")
            r.update(sealed_n=len(x), sealed_mean=round(float(m), 1), sealed_t=round(t(x), 2), vs_long_t=round(t(al), 2), placebo=pct, decision=v); print("sealed", r)
    (ROOT / "reports" / f"d177_{'sealed' if validate else 'discovery'}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] == ["validate"])
