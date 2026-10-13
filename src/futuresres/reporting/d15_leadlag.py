"""D-series family 15 - MNQ <-> gold lead-lag over 15-60 minutes (decisions.md 185), recent-period design: discovery 2018-01 ->
2022-12; validation 2023-01 -> 2026-08 sealed. Many trades a day, net of a round trip.

    python -m futuresres.reporting.d15_leadlag --scan
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
OUT = ROOT / "reports" / "d15_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
COST = {"MNQ": 0.56, "MGC": 1.0}
#: overlap -> (MNQ grid, MGC grid, start clock minute, end clock minute)
OVERLAPS = {"A 18:00-03:00": ("night", "asia", 1080, 180), "B 03:00-09:30": ("night", "london", 180, 570),
            "C 09:30-11:30": ("day", "london", 570, 690)}


def _clock_slice(market, session, c0, c1):
    """days, closes (days x minutes of the overlap), contracts; column j = the price at clock minute c0 + j (close of the bar before)."""
    days, C, V, K = d8.load(market, session)
    a, _ = d8.SESSIONS[(market, session)]
    L = (c1 - c0) % 1440
    o0 = (c0 - a) % 1440
    cols = [o0 + j - 1 for j in range(L + 1)]        # price at minute c0 + j = close of bar at offset o0 + j - 1
    cols = [max(c, 0) for c in cols]
    return days, C[:, cols], K[:, cols]


def build(overlap: str):
    mg, gg, c0, c1 = OVERLAPS[overlap]
    dq, Q, KQ = _clock_slice("MNQ", mg, c0, c1)
    dg, G, KG = _clock_slice("MGC", gg, c0, c1)
    iq = {d: i for i, d in enumerate(dq)}; ig = {d: i for i, d in enumerate(dg)}
    common = sorted(set(iq) & set(ig))
    a = np.array([iq[d] for d in common]); b = np.array([ig[d] for d in common])
    return np.array(common), {"MNQ": (Q[a], KQ[a]), "MGC": (G[b], KG[b])}


def trades(days, P, leader, follower, k, direction, cost, lo, hi, thr=None, leader_rows=None):
    """(day, net bps) per mark; leader_rows optionally replaces the leader's day (placebo)."""
    Lp, Lk = P[leader]; Fp, Fk = P[follower]
    n, W = Fp.shape; out = []
    for i in range(n):
        if not (lo <= days[i] <= hi):
            continue
        li = i if leader_rows is None else leader_rows[i]
        for t in range(k, W - k, k):
            l0, l1, f0, f1 = Lp[li, t - k], Lp[li, t], Fp[i, t], Fp[i, t + k]
            if not (np.isfinite(l0) and np.isfinite(l1) and np.isfinite(f0) and np.isfinite(f1)):
                continue
            if Lk[li, t - k] != Lk[li, t] or Fk[i, t] != Fk[i, t + k]:
                continue
            lr = (l1 / l0 - 1) * 1e4
            if lr == 0 or (thr is not None and abs(lr) <= thr):
                continue
            out.append((days[i], float(direction * np.sign(lr) * (f1 / f0 - 1) * 1e4 - cost)))
    return out


def leader_moves(days, P, leader, k, lo, hi):
    Lp, Lk = P[leader]; out = []
    for i in range(len(days)):
        if lo <= days[i] <= hi:
            for t in range(k, Lp.shape[1] - k, k):
                if np.isfinite(Lp[i, t - k]) and np.isfinite(Lp[i, t]) and Lk[i, t - k] == Lk[i, t]:
                    out.append(abs((Lp[i, t] / Lp[i, t - k] - 1) * 1e4))
    return np.array(out)


def clustered(tr):
    d = {}
    for day, v in tr:
        d[day] = d.get(day, 0.0) + v
    ds = np.array(list(d.values())); x = np.array([v for _, v in tr])
    t = float(ds.mean() / (ds.std(ddof=1) / math.sqrt(len(ds)))) if len(ds) > 2 else float("nan")
    return float(x.mean()) if len(x) else float("nan"), t, len(x), len(ds)


def scan() -> dict:
    res = []
    for ov in OVERLAPS:
        days, P = build(ov)
        for leader, follower in (("MNQ", "MGC"), ("MGC", "MNQ")):
            for k in (15, 30, 60):
                med = float(np.median(leader_moves(days, P, leader, k, *DISC)))
                for form in ("all", "strong"):
                    thr = med if form == "strong" else None
                    fol = trades(days, P, leader, follower, k, 1, 0.0, *DISC, thr=thr)
                    assert all(d <= DISC[1] for d, _ in fol)
                    gross = np.mean([v for _, v in fol])
                    direction = 1 if gross > 0 else -1
                    tr = [(d, direction * v - COST[follower]) for d, v in fol]
                    net, t, n, nd = clustered(tr)
                    res.append({"overlap": ov, "leader": leader, "follower": follower, "k": k, "form": form, "median_abs_leader_bps": med,
                                "rule": "follow" if direction == 1 else "fade", "gross_follow_bps": float(gross), "net_bps": net, "t_day": t,
                                "trades": n, "days": nd, "per_day": n / max(nd, 1)})
                    print(f"  {ov} {leader}->{follower} k {k:2} {form:6} {res[-1]['rule']:6} trades {n:6} ({n / max(nd, 1):4.1f}/day) "
                          f"gross {gross:+6.2f} net {net:+6.2f} bps t {t:+5.2f}", flush=True)
        del P
    for q in res:
        q["carried"] = bool(abs(q["t_day"]) > 1.96 and q["net_bps"] > 0)
    res.sort(key=lambda q: -(q["t_day"] if q["net_bps"] > 0 else -9))
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
