"""D-series family 115 - the intraday structures on the current regime (decisions.md 433). `pairs(market, rule)` returns
{date: (predictor bps or signal, target bps)} from the owned minute grids (family 8); discovery 2021-24, sealed 2025-01 -> 2026-08.

    python -m futuresres.reporting.d115_intraday --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.d8_intraday as d8

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d115_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
COST = {"MNQ": 0.5, "MGC": 0.8}
RULES = ("session_before", "morning_afternoon", "first30_rest", "opening_minute", "prev_window", "close_location", "last_hour_next",
         "signed_volume", "into_fix")
GRIDS = {"MNQ": ("day", "night", "post"), "MGC": ("london", "asia", "ny")}
_G: dict = {}


def _g(m, s):
    if (m, s) not in _G:
        D, C, V, K = d8.load(m, s); _G[(m, s)] = (D, C, V, K, {d: i for i, d in enumerate(D)})
    return _G[(m, s)]


def _oc(C, K, i, a=None, b=None):
    c = C[i]
    if a is None:
        f = np.where(np.isfinite(c))[0]
        if len(f) < 0.5 * len(c):
            return None
        a, b = f[0], f[-1]
    if not (np.isfinite(c[a]) and np.isfinite(c[b])) or K[i, a] != K[i, b]:
        return None
    return float((c[b] / c[a] - 1) * 1e4)


def _nxt(d):
    return d + dt.timedelta(days=1 if d.weekday() < 4 else 3)


def pairs(m: str, rule: str) -> dict:
    warnings.filterwarnings("ignore")
    w, pre, aft = GRIDS[m]
    D, C, V, K, I = _g(m, w); Dp, Cp, Vp, Kp, Ip = _g(m, pre); Da, Ca, Va, Ka, Ia = _g(m, aft)
    e = C.shape[1] - 1; out = {}
    for i, d in enumerate(D):
        x = y = None
        if rule == "session_before" and d in Ip:
            x = _oc(Cp, Kp, Ip[d]); y = _oc(C, K, i)
        elif rule == "morning_afternoon":
            a, b, c, z = (0, 150, 210, 389) if m == "MNQ" else (0, 240, 330, 509)
            x = _oc(C, K, i, a, b); y = _oc(C, K, i, c, z)
        elif rule == "first30_rest":
            x = _oc(C, K, i, 0, 30); y = _oc(C, K, i, 30, e)
        elif rule == "opening_minute":
            if m == "MNQ" and d in Ip:
                j = Ip[d]; p0 = Cp[j, -1]; p1 = C[i, 0]
                if np.isfinite(p0) and np.isfinite(p1) and Kp[j, -1] == K[i, 0]:
                    x = float((p1 / p0 - 1) * 1e4); y = _oc(C, K, i, 0, e)
            elif m == "MGC":
                x = _oc(C, K, i, 319, 320); y = _oc(C, K, i, 320, e)
        elif rule == "prev_window" and i > 0:
            x = _oc(C, K, i - 1); y = _oc(C, K, i)
        elif rule == "close_location" and i > 0:
            pc = C[i - 1]; f = np.where(np.isfinite(pc))[0]
            if len(f) > 0.5 * len(pc):
                hi, lo = np.nanmax(pc), np.nanmin(pc)
                if hi > lo:
                    x = float((pc[f[-1]] - lo) / (hi - lo) - 0.5); y = _oc(C, K, i)
        elif rule == "last_hour_next":
            if m == "MNQ":
                n = _nxt(d)
                if n in Ip:
                    x = _oc(C, K, i, 329, 389); y = _oc(Cp, Kp, Ip[n])
            elif d in Ia:
                x = _oc(C, K, i, 449, 509); y = _oc(Ca, Ka, Ia[d], 0, Ca.shape[1] - 1)
        elif rule == "signed_volume" and d in Ip:
            j = Ip[d]; dC = np.diff(Cp[j]); same = Kp[j, 1:] == Kp[j, :-1]
            sg = np.where(same & np.isfinite(dC), np.sign(dC), 0.0); v = Vp[j, 1:]
            if v.sum() > 0:
                x = float((sg * v).sum() / v.sum()); y = _oc(C, K, i)
        elif rule == "into_fix":
            if m == "MNQ":
                x = _oc(C, K, i, 89, 119); y = _oc(C, K, i, 119, 149)
            elif d in Ia:
                j = Ia[d]; x = _oc(Ca, Ka, j, 89, 119); y = _oc(Ca, Ka, j, 119, 149)
        if x is not None and y is not None and x != 0:
            out[d] = (x, y)
    return out


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def cell_rows(m, rule, form, lo, hi, med=None):
    P = pairs(m, rule)
    if med is None:
        med = float(np.median([abs(x) for d, (x, _) in P.items() if DISC[0] <= d <= DISC[1]]))
    D = sorted(d for d in P if lo <= d <= hi and (form == "all" or abs(P[d][0]) > med))
    return np.array(D), np.array([np.sign(P[d][0]) for d in D]), np.array([P[d][1] for d in D]), med


def scan() -> dict:
    res = []
    for m in ("MNQ", "MGC"):
        for rule in RULES:
            for form in ("all", "strong"):
                D, S, Y, med = cell_rows(m, rule, form, *DISC)
                if len(Y) < 30:
                    continue
                g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - COST[m]
                _, Sc, Yc, _ = cell_rows(m, rule, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - COST[m]
                r = {"market": m, "rule": rule, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else None, "context_t": _t(cc) if len(cc) > 2 else None}
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"])
    carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res[:10]:
        print(f"  {r['market']} {r['rule']:18} {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 "
              f"{(r['context_net'] or float('nan')):+6.2f} t {(r['context_t'] or float('nan')):+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    if ap.parse_args(argv).scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
