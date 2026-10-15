"""D-series family 153 - Asian local indices into the plan windows, timing-aware, current regime (decisions.md 540)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d153_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
CONTEXT = (dt.date(2010, 1, 1), dt.date(2020, 12, 31))
PRED = ("^KS11", "^TWII", "^AXJO", "^HSI", "000001.SS", "^STI", "^BSESN")
EARLY = {"^KS11", "^TWII", "^AXJO"}
#: exchange time zones: a bar is dated by its LOCAL session date (a22.load stamps New York time, which puts an Asian session on the
#: previous date and made "previous weekday" the same session - found on the first run, decisions.md 541)
TZ = {"^KS11": "Asia/Seoul", "^TWII": "Asia/Taipei", "^AXJO": "Australia/Sydney", "^HSI": "Asia/Hong_Kong", "000001.SS": "Asia/Shanghai",
      "^STI": "Asia/Singapore", "^BSESN": "Asia/Kolkata"}
TARGETS = {k: v for k, v in d111.TARGETS.items() if k in ("NKD", "DAX", "MGC", "MNQ")}
_C: dict = {}


def series(p: str, h: int) -> dict:
    key = (p, h)
    if key not in _C:
        z = a22.load(p, "1d").with_columns(pl.col("ts").dt.convert_time_zone(TZ[p]).dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5).unique("date", keep="last").sort("date")
        ds = z["date"].to_list(); c = z["c"].to_numpy(); r = np.r_[np.nan, np.diff(np.log(c)) * 1e4]
        S = d111._clean(ds, r); ds = sorted(S); v = np.array([S[d] for d in ds])
        _C[key] = {ds[i]: float(v[i - h + 1:i + 1].sum()) for i in range(h - 1, len(ds))}
    return _C[key]


def same_day(p: str, tg: str) -> bool:
    return tg == "MNQ" or (tg in ("DAX", "MGC") and p in EARLY)


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    P = series(p, h); Y = d111.target(tg); sd = same_day(p, tg)
    if med is None:
        med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
    D, S, YY = [], [], []
    for d, y in Y.items():
        x = P.get(d if sd else d3.prev_weekday(d))
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
                    D, S, Y, med = rows(p, h, tg, form, *DISC)
                    g = S * Y; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
                    _, Sc, Yc, _ = rows(p, h, tg, form, *CONTEXT, med=med); cc = dirn * Sc * Yc - cost
                    r = {"target": tg, "predictor": p, "h": h, "form": form, "median_abs": med, "n": int(len(g)), "dir": "follow" if dirn == 1 else "fade",
                         "same_day": same_day(p, tg), "net_bps": float(net.mean()), "t": _t(net), "context_net": float(cc.mean()), "context_t": _t(cc)}
                    r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
    res.sort(key=lambda r: -r["t"]); carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_carries": round(0.025 * len(res), 1), "all": res, "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.025 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res[:14]:
        print(f"  {r['target']:3} <- {r['predictor']:9} {r['h']}d {r['form']:6} {'same' if r['same_day'] else 'prev'} n {r['n']:4} {r['dir']:6} net {r['net_bps']:+6.2f} "
              f"t {r['t']:+5.2f} | 2010-20 {r['context_net']:+6.2f} t {r['context_t']:+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    return out


if __name__ == "__main__":
    scan()
