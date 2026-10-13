"""D-series family 10 - the cross-market daily universe (decisions.md 171): does yesterday's session in one market set today's
direction in another? 14 CME futures, Yahoo daily bars, open -> settlement within one bar. Discovery 2010-01 -> 2017-12 only.

    python -m futuresres.reporting.d10_universe --fetch
    python -m futuresres.reporting.d10_universe --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d10_discovery.json"
DISC = (dt.date(2010, 1, 1), dt.date(2017, 12, 31))
VAL = (dt.date(2018, 1, 1), dt.date(2026, 8, 31))
UNIVERSE = {"ES": "ES=F", "NQ": "NQ=F", "RTY": "RTY=F", "GC": "GC=F", "SI": "SI=F", "HG": "HG=F", "CL": "CL=F", "NG": "NG=F",
            "ZN": "ZN=F", "6E": "6E=F", "6J": "6J=F", "ZC": "ZC=F", "ZS": "ZS=F", "ZW": "ZW=F"}


def fetch() -> None:
    for k, sym in UNIVERSE.items():
        d = a22.fetch(sym, "1d"); print(k, sym, d.height, flush=True); time.sleep(0.5)


def series() -> dict:
    out = {}
    for k, sym in UNIVERSE.items():
        z = a22.load(sym, "1d").with_columns(pl.col("ts").dt.date().alias("date"))
        z = z.filter(pl.col("date").dt.weekday() <= 5)
        r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy(); ds = z["date"].to_list()
        med = np.median(r); rsd = 1.4826 * np.median(np.abs(r - med))
        out[k] = {d: float(x) for d, x in zip(ds, r) if np.isfinite(x) and abs(x - med) <= 15 * rsd}
    return out


def pairs(S: dict, target: str, pred: str, lo: dt.date, hi: dt.date, shift: int = 0):
    D, Y, X = [], [], []
    for d, y in S[target].items():
        if not (lo <= d <= hi):
            continue
        p = d3.prev_weekday(d)
        for _ in range(abs(shift)):
            p = d3.prev_weekday(p) if shift > 0 else p + dt.timedelta(days=1 if p.weekday() < 4 else 3)
        x = S[pred].get(p)
        if x is None:
            continue
        D.append(d); Y.append(y); X.append(x)
    o = np.argsort(D)
    return np.array(D)[o], np.array(Y)[o], np.array(X)[o]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    S = series(); res = []
    for tg in UNIVERSE:
        for pr in UNIVERSE:
            if pr == tg:
                continue
            D, Y, X = pairs(S, tg, pr, *DISC)
            assert D.max() <= DISC[1], "discovery read sealed data"
            z = np.sign(X) * (Y - Y.mean())
            res.append({"target": tg, "predictor": pr, "n": int(len(z)), "mean_bps": float(z.mean()), "sd_bps": float(z.std(ddof=1)),
                        "t": _t(z), "rule": "follow" if z.mean() > 0 else "fade"})
    res.sort(key=lambda r: -abs(r["t"]))
    carried = [r for r in res if abs(r["t"]) > 1.96]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_passes_5pct": round(0.05 * len(res), 1),
           "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests on {DISC[0]} -> {DISC[1]}; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res[:24]:
        print(f"  {r['target']:3} <- {r['predictor']:3} n {r['n']:4} {r['rule']:6} mean {r['mean_bps']:+6.2f} bps sd {r['sd_bps']:6.1f} t {r['t']:+5.2f}"
              f"{'  CARRIED' if abs(r['t']) > 1.96 else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--fetch", action="store_true"); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.fetch:
        fetch()
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
