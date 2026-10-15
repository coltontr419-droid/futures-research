"""D-series family 155 - Japan MOF weekly cross-border flows as a week-long sign, current regime (decisions.md 550).
Data: MOF week.csv (International Transactions in Securities, weekly), cached as data/cache/mof_week.csv (gitignored)."""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "data" / "cache" / "mof_week.csv"
OUT = ROOT / "reports" / "d155_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
COLS = {"foreign_equity": 14, "foreign_bonds": 17, "resident_foreign_equity": 3}
TARGETS = {k: v for k, v in d111.TARGETS.items() if k in ("NKD", "DAX", "MGC", "MNQ")}
_C: dict = {}


def _num(x: str) -> float:
    return float(x.replace(",", "").strip())


def weeks() -> list:
    """[(release Thursday, {name: value})], sorted."""
    if "w" not in _C:
        out = []
        for r in csv.reader(open(SRC, encoding="shift_jis", errors="ignore")):
            if not r or not r[0][:4].isdigit():
                continue
            per = r[0].replace("．", ".").replace(" ", "")
            if "〜" not in per:
                continue
            a, b = per.split("〜"); y, m1, d1 = (int(x) for x in a.split(".")); bb = [int(x) for x in b.split(".")]
            end = dt.date(*bb) if len(bb) == 3 else dt.date(y + (1 if bb[0] < m1 else 0), bb[0], bb[1])
            try:
                out.append((end + dt.timedelta(days=5), {k: _num(r[i]) for k, i in COLS.items()}))
            except (ValueError, IndexError):
                continue
        _C["w"] = sorted(out)
    return _C["w"]


def latest(d: dt.date):
    """The latest week released on or before date d (release Thursday <= d): (release date, values)."""
    W = weeks(); lo, hi = 0, len(W) - 1; best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if W[mid][0] <= d:
            best = W[mid]; lo = mid + 1
        else:
            hi = mid - 1
    return best if best and (d - best[0]).days < 9 else None


def group(d: dt.date):
    w = latest(d)
    return str(w[0]) if w else None


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    if med is None:
        med = float(np.median([abs(v[p]) for r, v in weeks() if DISC[0] <= r <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in d111.target(tg).items():
        if not (lo <= d <= hi):
            continue
        w = latest(d)
        if w is None or not w[1][p] or (form == "strong" and abs(w[1][p]) <= med):
            continue
        D.append(d); S.append(np.sign(w[1][p])); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def weekly_t(D, g) -> float:
    G = {}
    for d, x in zip(D, g):
        G.setdefault(group(d), []).append(x)
    s = np.array([np.sum(v) for v in G.values()])
    return _t(s)


def scan() -> dict:
    res = []
    for p in COLS:
        for tg, cost in TARGETS.items():
            for form in ("all", "strong"):
                D, S, Y, med = rows(p, 1, tg, form, *DISC)
                g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                Dc, Sc, Yc, _ = rows(p, 1, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                r = {"target": tg, "predictor": p, "h": 1, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                     "net_bps": float(net.mean()), "t": _t(net), "t_weekly": weekly_t(D, net), "context_net": float(cc.mean()), "context_t": _t(cc)}
                r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0 and r["t_weekly"] > 1.96); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; carried {len(carried)}; weeks parsed {len(weeks())} ({weeks()[0][0]} -> {weeks()[-1][0]})", flush=True)
    for r in res[:12]:
        print(f"  {r['target']:3} <- {r['predictor']:23} {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} (weekly t {r['t_weekly']:+5.2f}) | 2010-20 "
              f"{r['context_net']:+6.2f} t {r['context_t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


if __name__ == "__main__":
    scan()
