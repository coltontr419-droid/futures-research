"""D-series family 7 - London continuation beyond gold (decisions.md 161): does a market's overnight move (11:30 -> 03:00 New
York), or gold's, set the direction of its London window (03:00 -> 11:30)? Silver and six currency pairs, free HistData minute
bars on the corrected clock. Discovery 2010-06 -> 2017-12 only.

    python -m futuresres.reporting.d7_london --build PAIR     (one pair per process)
    python -m futuresres.reporting.d7_london --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "reports" / "d7_discovery.json"
DISC, VAL = d3.DISC, d3.VAL
PAIRS = {"xagusd": "SI", "eurusd": "6E", "gbpusd": "6B", "audusd": "6A", "usdjpy": "6J", "usdchf": "6S", "usdcad": "6C"}


def build(pair: str) -> None:
    f = d3.histdata(pair, {"p0300": ("America/New_York", 3, 0), "p1130": ("America/New_York", 11, 30)})
    f = f.filter(pl.col("date").dt.weekday() <= 5).sort("date").drop_nulls()
    f = f.with_columns(((pl.col("p1130") / pl.col("p0300") - 1) * 1e4).alias("win"),
                       ((pl.col("p0300") / pl.col("p1130").shift(1) - 1) * 1e4).alias("pre"))
    f.write_parquet(CACHE / f"d7_{pair}.parquet")
    print(pair, f.height, "days", f["date"].min(), "->", f["date"].max(), "win sd", round(float(f["win"].std()), 1),
          "pre sd", round(float(f["pre"].std()), 1), flush=True)


def _clean(d: dict) -> dict:
    v = np.array(list(d.values())); med = np.median(v); rsd = 1.4826 * np.median(np.abs(v - med))
    return {k: x for k, x in d.items() if abs(x - med) <= 15 * rsd}


def series(pair: str) -> tuple[dict, dict]:
    f = pl.read_parquet(CACHE / f"d7_{pair}.parquet")
    win = _clean({d: float(x) for d, x in zip(f["date"].to_list(), f["win"].to_list()) if x is not None})
    pre = _clean({d: float(x) for d, x in zip(f["date"].to_list(), f["pre"].to_list()) if x is not None})
    return win, pre


def rows(pair: str, predictor: str, lo: dt.date, hi: dt.date):
    win, pre = series(pair)
    P = pre if predictor == "own" else d3.series()["MGC_pre"]
    D = sorted(d for d in win if lo <= d <= hi and d in P)
    return np.array(D), np.array([win[d] for d in D]), np.array([P[d] for d in D])


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for pair in PAIRS:
        for pred in ("own", "gold"):
            D, Y, X = rows(pair, pred, *DISC)
            assert D.max() <= DISC[1], "discovery read sealed data"
            med = float(np.median(np.abs(X))); ydm = Y - Y.mean()
            for form in ("all", "strong"):
                m = np.ones(len(X), bool) if form == "all" else np.abs(X) > med
                z = np.sign(X[m]) * ydm[m]
                res.append({"pair": pair, "future": PAIRS[pair], "predictor": pred, "form": form, "median_abs_pred": med, "n": int(m.sum()),
                            "mean_bps": float(z.mean()), "sd_bps": float(z.std(ddof=1)), "t": _t(z), "rule": "follow" if z.mean() > 0 else "fade"})
    res.sort(key=lambda r: -abs(r["t"]))
    carried = [r for r in res if abs(r["t"]) > 1.96]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_passes_5pct": round(0.05 * len(res), 1),
           "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests on {DISC[0]} -> {DISC[1]}; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res:
        print(f"  {r['pair']} ({r['future']}) <- {r['predictor']:4} overnight ({r['form']:6}) n {r['n']:5} {r['rule']:6} mean {r['mean_bps']:+6.2f} bps "
              f"t {r['t']:+5.2f}{'  CARRIED' if abs(r['t']) > 1.96 else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--build", choices=tuple(PAIRS)); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.build:
        build(a.build)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
