"""D-series family 157 - weekly US jobless claims as a week-long sign, current regime (decisions.md 554)."""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d157_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
LAG = {"ICSA": 5, "CCSA": 12}
TARGETS = d111.TARGETS
SAME_DAY = {"MNQ"}                               # opens after 08:30 ET on the release Thursday
_C: dict = {}


def releases(series: str, h: int) -> tuple:
    """(sorted release dates, values = change over h weeks)."""
    key = (series, h)
    if key not in _C:
        rows = [(dt.date.fromisoformat(a), float(b)) for a, b in list(csv.reader(open(ROOT / "data" / "cache" / f"fred_{series}.csv")))[1:] if b not in ("", ".")]
        rel = [(rows[i][0] + dt.timedelta(days=LAG[series]), rows[i][1] - rows[i - h][1]) for i in range(h, len(rows))]
        _C[key] = ([r[0] for r in rel], [r[1] for r in rel])
    return _C[key]


def latest(series: str, h: int, d: dt.date, tg: str):
    R, V = releases(series, h); cut = d if tg in SAME_DAY else d - dt.timedelta(days=1)
    i = bisect.bisect_right(R, cut) - 1
    return (R[i], V[i]) if i >= 0 and (cut - R[i]).days < 7 else None


_G: dict = {}


def group(d: dt.date):
    return _G.get(d)


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    if med is None:
        R, V = releases(p, h); med = float(np.median([abs(v) for r, v in zip(R, V) if DISC[0] <= r <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in d111.target(tg).items():
        if not (lo <= d <= hi):
            continue
        w = latest(p, h, d, tg)
        if w is None or not w[1] or (form == "strong" and abs(w[1]) <= med):
            continue
        D.append(d); S.append(np.sign(w[1])); YY.append(y); _G[d] = str(w[0])
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def weekly_t(D, g) -> float:
    G = {}
    for d, x in zip(D, g):
        G.setdefault(group(d), []).append(x)
    return _t(np.array([np.sum(v) for v in G.values()]))


def scan() -> dict:
    res = []
    for p in LAG:
        for h in (1, 4):
            for tg, cost in TARGETS.items():
                for form in ("all", "strong"):
                    D, S, Y, med = rows(p, h, tg, form, *DISC)
                    g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                    Dc, Sc, Yc, _ = rows(p, h, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                    r = {"target": tg, "predictor": p, "h": h, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                         "net_bps": float(net.mean()), "t": _t(net), "t_weekly": weekly_t(D, net), "context_net": float(cc.mean()), "context_t": _t(cc)}
                    r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0 and r["t_weekly"] > 1.96); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; carried {len(carried)}", flush=True)
    for r in res[:12]:
        print(f"  {r['target']:3} <- {r['predictor']} {r['h']}w {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} (weekly {r['t_weekly']:+5.2f}) | 2010-20 "
              f"{r['context_net']:+6.2f} t {r['context_t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


if __name__ == "__main__":
    scan()
