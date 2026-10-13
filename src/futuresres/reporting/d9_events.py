"""D-series family 9 - drift after scheduled releases (decisions.md 168): on 08:30 / 14:00 release days (detected from a volume
spike), does the move in the first 5 / 15 minutes predict the rest of the session? MNQ and MGC, the family-8 minute grids.

    python -m futuresres.reporting.d9_events --scan        (discovery: 12 tests, 2013-2017 ONLY)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d8_intraday as d8

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d9_discovery.json"
DISC, VAL = d8.DISC, d8.VAL
COST = d8.COST
#: event type -> (market, grid of the release minute, release offset, end grid, end offset)
EVENTS = {"MNQ 08:30": ("MNQ", "night", 870, "day", 389), "MGC 08:30": ("MGC", "london", 330, "london", 509),
          "MNQ 14:00": ("MNQ", "day", 270, "day", 389)}


def event_days(ev: str):
    """Per release day: (date, predictor points for k=5, k=15, target points for k=5, k=15, is_release)."""
    m, g0, o, g1, e = EVENTS[ev]
    days0, C0, V0, K0 = d8.load(m, g0)
    if g1 != g0:
        days1, C1, _, K1 = d8.load(m, g1); idx1 = {d: i for i, d in enumerate(days1)}
    else:
        C1, K1, idx1 = C0, K0, {d: i for i, d in enumerate(days0)}
    vol = V0[:, o:o + 5].sum(axis=1)
    rows = []
    for i, d in enumerate(days0):
        if i < 20 or d not in idx1:
            continue
        j = idx1[d]
        med = np.median(vol[i - 20:i])
        is_rel = bool(med > 0 and vol[i] > 3 * med)
        p_pre = C0[i, o - 1]; end = C1[j, e]
        if not (np.isfinite(p_pre) and np.isfinite(end)) or K0[i, o - 1] != K1[j, e]:
            continue
        rec = {"date": d, "release": is_rel}
        for k in (5, 15):
            pk = C0[i, o + k - 1]
            if not np.isfinite(pk) or K0[i, o + k - 1] != K0[i, o - 1]:
                break
            rec[f"x{k}"] = float(pk - p_pre); rec[f"y{k}"] = float(end - pk)
        else:
            rows.append(rec)
    return rows


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for ev, (m, *_rest) in EVENTS.items():
        rows = event_days(ev)
        disc = [r for r in rows if DISC[0] <= r["date"] <= DISC[1]]
        assert all(r["date"] <= DISC[1] for r in disc)
        rel = [r for r in disc if r["release"]]
        print(f"{ev}: {len(rel)} release days of {len(disc)} sessions in 2013-17", flush=True)
        for k in (5, 15):
            X = np.array([r[f"x{k}"] for r in rel]); Y = np.array([r[f"y{k}"] for r in rel])
            med = float(np.median(np.abs(X))); ydm = Y - Y.mean()
            for form in ("all", "strong"):
                msk = np.ones(len(X), bool) if form == "all" else np.abs(X) > med
                z = np.sign(X[msk]) * ydm[msk]
                rule = 1 if z.mean() > 0 else -1
                net = rule * np.sign(X[msk]) * Y[msk] - COST[m]
                res.append({"event": ev, "market": m, "k": k, "form": form, "median_abs_pred": med, "n": int(msk.sum()),
                            "mean_pts_demeaned": float(z.mean()), "t": _t(z), "rule": "follow" if rule > 0 else "fade",
                            "net_pts_after_cost": float(net.mean()), "release_days": len(rel)})
    for r in res:
        r["carried"] = bool(abs(r["t"]) > 1.96 and r["net_pts_after_cost"] > 0)
    res.sort(key=lambda r: -abs(r["t"]))
    carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res:
        print(f"  {r['event']} first {r['k']:2} min ({r['form']:6}) n {r['n']:4} {r['rule']:6} demeaned {r['mean_pts_demeaned']:+7.2f} pts t {r['t']:+5.2f} "
              f"net after cost {r['net_pts_after_cost']:+7.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
