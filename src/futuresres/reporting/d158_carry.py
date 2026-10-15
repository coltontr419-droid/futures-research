"""D-series family 158 - own-curve carry as an every-day sign for crude and gold, current regime (decisions.md 556)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3
from futuresres.data.daily_bars import load_market

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d158_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
PAIRS = {"CL": "CL", "GC": "MGC"}
TARGETS = {"CL": 0.7, "MGC": 0.8}
_C: dict = {}


def series(root: str, kind: str) -> dict:
    key = (root, kind)
    if key not in _C:
        m = load_market(root); ds = [x.astype(object) for x in m.dates.astype("datetime64[D]")]; c = m.carry.astype(float)
        if kind == "level":
            out = {d: v for d, v in zip(ds, c) if np.isfinite(v)}
        else:
            out = {ds[i]: c[i] - c[i - 5] for i in range(5, len(ds)) if np.isfinite(c[i]) and np.isfinite(c[i - 5])}
        _C[key] = out
    return _C[key]


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    root, kind = p.split(":"); P = series(root, kind); Y = d111.target(tg)
    if med is None:
        med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in Y.items():
        x = P.get(d3.prev_weekday(d))
        if lo <= d <= hi and x and (form == "all" or abs(x) > med):
            D.append(d); S.append(np.sign(x)); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def group(d):
    return (d.year, d.month)


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for root, tg in PAIRS.items():
        for kind in ("level", "change5"):
            for form in ("all", "strong"):
                p = f"{root}:{kind}"; D, S, Y, med = rows(p, 1, tg, form, *DISC)
                g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - TARGETS[tg]
                _, Sc, Yc, _ = rows(p, 1, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - TARGETS[tg]
                G = {}
                for d, x in zip(D, net):
                    G.setdefault(group(d), []).append(x)
                tm = _t(np.array([np.sum(v) for v in G.values()]))
                r = {"target": tg, "predictor": p, "h": 1, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "share_long": float(((dirn * S) > 0).mean()), "net_bps": float(net.mean()), "t": _t(net), "t_monthly": tm,
                     "always_long": float((Y - TARGETS[tg]).mean()), "context_net": float(cc.mean()), "context_t": _t(cc)}
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0 and tm > 1.96); res.append(r)
                print(f"  {tg:3} <- {p:11} {form:6} n {r['n']:4} {r['dir']:6} long {r['share_long']:.0%} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} (monthly {tm:+5.2f}) "
                      f"always-long {r['always_long']:+6.2f} | 2010-20 {r['context_net']:+6.2f} t {r['context_t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    carried = [r for r in res if r["carried"]]
    OUT.write_text(json.dumps({"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}, indent=1) + "\n")
    return res


if __name__ == "__main__":
    scan()
