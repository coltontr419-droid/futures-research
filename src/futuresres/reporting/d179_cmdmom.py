"""D-series family 179 (decisions.md §1133): weekly momentum / reversal in 8 commodity futures, cross-sectional (top 2 vs bottom 2) and own-market, risk units.

    python -m futuresres.reporting.d179_cmdmom [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12

ROOT = Path(__file__).resolve().parents[3]
M = ("GC", "SI", "HG", "CL", "NG", "ZC", "ZS", "ZW")
DISC = (dt.date(2010, 3, 1), dt.date(2022, 12, 31)); VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))


def weekly(S):
    """{week_monday: {m: (risk-unit return, cost in risk units)}}, sd from the 60 sessions before the week."""
    out = {}
    for m in M:
        ds = sorted(S[m]); r = np.array([S[m][d] for d in ds]); wk = {}
        for i, d in enumerate(ds):
            wk.setdefault(d - dt.timedelta(days=d.weekday()), []).append(i)
        for w, ix in wk.items():
            if ix[0] < 60 or len(ix) < 4:
                continue
            sd = r[ix[0] - 60:ix[0]].std(ddof=1) * np.sqrt(5)
            out.setdefault(w, {})[m] = (r[ix].sum() / sd, d12.COST[m] * len(ix) / sd)
    return out


def series(W, cell, lo, hi):
    ws = sorted(W); x, bench = [], []
    for a, b in zip(ws, ws[1:]):
        if not (lo <= b <= hi) or (b - a).days != 7:
            continue
        common = [m for m in M if m in W[a] and m in W[b]]
        if len(common) < 6:
            continue
        past = {m: W[a][m][0] for m in common}; nxt = {m: W[b][m] for m in common}
        if cell in ("xs_follow", "xs_fade"):
            o = sorted(common, key=lambda m: past[m]); s = 1 if cell == "xs_follow" else -1
            v = s * (sum(nxt[m][0] for m in o[-2:]) - sum(nxt[m][0] for m in o[:2])) / 4 - sum(nxt[m][1] for m in o[:2] + o[-2:]) / 4
        else:
            s = 1 if cell == "ts_follow" else -1
            v = np.mean([s * np.sign(past[m]) * nxt[m][0] - nxt[m][1] for m in common])
        x.append(v); bench.append(np.mean([nxt[m][0] - nxt[m][1] for m in common]))
    return np.array(x), np.array(bench)


def t(x):
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def main(validate: bool) -> None:
    W = weekly(d10.series()); out = {"cells": []}
    for c in ("xs_follow", "xs_fade", "ts_follow", "ts_fade"):
        x, _ = series(W, c, *DISC); r = {"cell": c, "weeks": len(x), "mean_ru": round(float(x.mean()), 4), "t": round(t(x), 2)}
        out["cells"].append(r); print("discovery", r)
        if validate and r["mean_ru"] > 0 and r["t"] > 1.96:
            x, b = series(W, c, *VAL); rng = np.random.default_rng(1133); m = x.mean()
            pct = float((np.array([np.mean(x * rng.choice((-1.0, 1.0), len(x))) for _ in range(2000)]) < m).mean() * 100)
            v = "CONFIRM" if t(x) > 1.645 and t(x - b) > 1.645 and pct >= 95 else ("WATCHLIST" if m > 0 else "REJECT")
            r.update(sealed_weeks=len(x), sealed_mean=round(float(m), 4), sealed_t=round(t(x), 2), vs_long_t=round(t(x - b), 2), placebo=pct, decision=v); print("sealed", r)
    (ROOT / "reports" / f"d179_{'sealed' if validate else 'discovery'}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] == ["validate"])
