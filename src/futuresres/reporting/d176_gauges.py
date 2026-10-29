"""D-series family 176 (decisions.md §1125): S-series gauges (put/call, breadth, short volume, insider) as every-day signs for non-equity futures.

    python -m futuresres.reporting.d176_gauges [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12
import futuresres.reporting.d24_shock as d24
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
TARGETS = ("GC", "SI", "HG", "CL", "NG", "ZN", "6E", "6J", "ZC", "ZS", "ZW", "RTY")
LO = dt.date(2018, 11, 1)


def gauges() -> dict:
    """{gauge: {date: side}} with side = +1 risk-on, -1 risk-off, known at that date's close."""
    st = ROOT / "data" / "stocks"; out = {}
    pc = json.loads((st / "s2" / "pc.json").read_text()); ds = sorted(pc); v = np.array([pc[d] for d in ds])
    out["putcall"] = {dt.date.fromisoformat(ds[i]): (1 if v[i - 4:i + 1].mean() / v[i - 59:i + 1].mean() - 1 < 0 else -1) for i in range(60, len(ds))}
    z = np.load(st / "long" / "pack.npz"); cal = [str(c) for c in z["cal"]]; A = z["A"].astype(np.float64); B = np.full(len(cal), np.nan)
    for i in range(50, len(cal)):
        W = A[:, i - 49:i + 1]; ok = np.isfinite(W).all(axis=1)
        if ok.sum() >= 300:
            B[i] = float((A[ok, i] > W[ok].mean(axis=1)).mean())
    out["breadth"] = {dt.date.fromisoformat(cal[i]): (1 if B[i] - np.nanmean(B[i - 250:i]) > 0 else -1) for i in range(300, len(cal)) if np.isfinite(B[i])}
    D = json.loads((st / "s4" / "rows.json").read_text()); ds = sorted(D); v = np.array([D[d] for d in ds])
    out["shortvol"] = {dt.date.fromisoformat(ds[i]): (1 if v[i] - v[i - 60:i].mean() > 0 else -1) for i in range(60, len(ds))}
    C = json.loads((st / "s5" / "counts.json").read_text()); days = cal
    P = np.array([C["P"].get(d, 0) for d in days], float); S = np.array([C["S"].get(d, 0) for d in days], float)
    fri = [i for i in range(20, len(days) - 1) if dt.date.fromisoformat(days[i + 1]).isocalendar()[1] != dt.date.fromisoformat(days[i]).isocalendar()[1]]
    b = [P[i - 19:i + 1].sum() / max(P[i - 19:i + 1].sum() + S[i - 19:i + 1].sum(), 1) for i in fri]
    ins, k = {}, 52
    for i in range(fri[52], len(days)):
        while k + 1 < len(fri) and fri[k + 1] <= i:
            k += 1
        ins[dt.date.fromisoformat(days[i])] = 1 if b[k] - np.mean(b[k - 52:k]) > 0 else -1
    out["insider"] = ins
    return out


def cell(S, G, g, tgt, rule, lo, hi):
    D, x, al, sd = [], [], [], []
    for d, y in sorted(S[tgt].items()):
        if not (lo <= d <= hi):
            continue
        s = G[g].get(d3.prev_weekday(d))
        if s is None:
            continue
        side = s * rule; D.append(d); sd.append(side)
        x.append(side * y - d12.COST[tgt]); al.append((side - 1) * y - (d12.COST[tgt] if side < 0 else 0.0))
    return np.array(D), np.array(x), np.array(al), np.array(sd)


def t(x):
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 else float("nan")


def main(validate: bool) -> None:
    S = d10.series(); G = gauges(); res = []
    for g in G:
        for tgt in TARGETS:
            for rule, nm in ((1, "follow"), (-1, "fade")):
                _, x, _, _ = cell(S, G, g, tgt, rule, LO, d24.DISC[1])
                res.append({"gauge": g, "target": tgt, "rule": nm, "n": len(x), "mean_bps": round(float(x.mean()), 2), "t": round(t(x), 2)})
    car = sorted([r for r in res if r["mean_bps"] > 0 and r["t"] > 1.96], key=lambda r: -r["t"])[:5]
    out = {"cells": len(res), "carried": car, "all": res}
    print(f"family 176 discovery: {len(res)} cells, {len(car)} carried"); [print(" ", c) for c in car]
    if validate:
        rng = np.random.default_rng(1125); out["sealed"] = []
        for c in car:
            rule = 1 if c["rule"] == "follow" else -1
            _, x, al, sd = cell(S, G, c["gauge"], c["target"], rule, *d24.VAL)
            y = (x + d12.COST[c["target"]]) * sd; m = x.mean(); sh = []
            for _ in range(2000):
                s2 = np.roll(sd, rng.integers(1, len(sd))); sh.append((s2 * y - d12.COST[c["target"]]).mean())
            pct = float((np.array(sh) < m).mean() * 100)
            v = "CONFIRM" if t(x) > 1.645 and t(al) > 1.645 and pct >= 95 else ("WATCHLIST" if m > 0 else "REJECT")
            r = {**c, "sealed_n": len(x), "sealed_mean": round(float(m), 2), "sealed_t": round(t(x), 2), "vs_long_t": round(t(al), 2), "placebo": pct, "decision": v}
            out["sealed"].append(r); print(" sealed", r)
    (ROOT / "reports" / f"d176_{'sealed' if validate else 'discovery'}.json").write_text(json.dumps(out, indent=1, default=str) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] == ["validate"])
