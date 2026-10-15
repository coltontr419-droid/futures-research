"""D-series family 150 - Japanese and euro-area government yields as every-day predictors, current regime (decisions.md 534).
Data: Japan MOF jgbcme_all.csv / jgbcme.csv and ECB YC 2Y/10Y csvdata, cached under data/cache/yields (gitignored)."""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d146_newseries as d146
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
Y = ROOT / "data" / "cache" / "yields"
OUT = ROOT / "reports" / "d150_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
PRED = ("jgb10", "jgb2", "jp_curve", "us_jp10", "ea10", "ea_curve", "us_ea10")
LAG2 = {"ea10", "ea_curve", "us_ea10"}
TARGETS = {k: v for k, v in d111.TARGETS.items() if k in ("NKD", "DAX", "MGC", "MNQ")}
_C: dict = {}


def levels() -> dict:
    if "lv" not in _C:
        jp = {}
        for f in ("jgb_all.csv", "jgb_cur.csv"):
            for r in csv.reader(open(Y / f, encoding="utf-8", errors="ignore")):
                if r and r[0][:2] in ("19", "20") and "/" in r[0]:
                    try:
                        d = dt.datetime.strptime(r[0], "%Y/%m/%d").date(); jp[d] = (float(r[2]), float(r[10]))
                    except ValueError:
                        pass
        ea = {}
        for k, f in ((0, "ea2.csv"), (1, "ea10.csv")):
            for r in csv.DictReader(open(Y / f)):
                ea.setdefault(dt.date.fromisoformat(r["TIME_PERIOD"]), [np.nan, np.nan])[k] = float(r["OBS_VALUE"])
        d146.load("^TNX")
        import polars as pl
        import futuresres.reporting.a22_more_markets as a22
        z = a22.load("^TNX", "1d").with_columns(pl.col("ts").dt.date().alias("date")).unique("date", keep="last").sort("date")
        us = dict(zip(z["date"].to_list(), z["c"].to_list()))
        lv = {"jgb10": {d: v[1] for d, v in jp.items()}, "jgb2": {d: v[0] for d, v in jp.items()}, "jp_curve": {d: v[1] - v[0] for d, v in jp.items()},
              "us_jp10": {d: us[d] - v[1] for d, v in jp.items() if d in us}, "ea10": {d: v[1] for d, v in ea.items()},
              "ea_curve": {d: v[1] - v[0] for d, v in ea.items()}, "us_ea10": {d: us[d] - v[1] for d, v in ea.items() if d in us}}
        _C["lv"] = lv
    return _C["lv"]


def series(p: str, h: int) -> dict:
    """date -> change in bps over the h observations ending that date."""
    key = (p, h)
    if key not in _C:
        L = levels()[p]; ds = sorted(d for d, v in L.items() if np.isfinite(v)); v = np.array([L[d] for d in ds])
        _C[key] = {ds[i]: float((v[i] - v[i - h]) * 100) for i in range(h, len(ds))}
    return _C[key]


def asof(S: dict, d: dt.date, lag: int):
    q = d
    for _ in range(lag):
        q = d3.prev_weekday(q)
    for _ in range(4):
        if q in S:
            return S[q]
        q = d3.prev_weekday(q)
    return None


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    P = series(p, h); T = d111.target(tg); lag = 2 if p in LAG2 else 1
    if med is None:
        med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in T.items():
        x = asof(P, d, lag)
        if lo <= d <= hi and x and (form == "all" or abs(x) > med):
            D.append(d); S.append(np.sign(x)); YY.append(y)
    o = np.argsort(D)
    return np.array(D)[o], np.array(S)[o], np.array(YY)[o], med


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for p in PRED:
        for h in (1, 5):
            for tg, cost in TARGETS.items():
                for form in ("all", "strong"):
                    D, S, Yv, med = rows(p, h, tg, form, *DISC)
                    if len(Yv) < 100:
                        continue
                    g = S * Yv; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                    _, Sc, Yc, _ = rows(p, h, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                    r = {"target": tg, "predictor": p, "h": h, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                         "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()) if len(cc) else float("nan"), "context_t": _t(cc) if len(cc) > 2 else float("nan")}
                    r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_carries": round(0.025 * len(res), 1), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res[:15]:
        print(f"  {r['target']:3} <- {r['predictor']:8} {r['h']}d {r['form']:6} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} t {r['t']:+5.2f} | 2010-20 "
              f"{r['context_net']:+6.2f} t {r['context_t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


if __name__ == "__main__":
    scan()
