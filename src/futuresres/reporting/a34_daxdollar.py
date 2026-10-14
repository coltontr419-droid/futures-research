"""A34 - the DAX-dollar theme stress-tested (decisions.md 446). No trial.

    python -m futuresres.reporting.a34_daxdollar
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import polars as pl

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3
import futuresres.reporting.hd_grid as hg

ROOT = Path(__file__).resolve().parents[3]
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
PER = {"2010-20": (dt.date(2010, 1, 1), dt.date(2020, 12, 31)), "2021-24": DISC, "2025-26": (dt.date(2025, 1, 1), dt.date(2026, 8, 31))}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def dollar(source: str) -> dict:
    if source == "DX-Y.NYB":
        return d111.predictor("DX-Y.NYB")
    if source == "DTWEXBGS":
        rows = [(dt.date.fromisoformat(a), float(b)) for a, b in list(csv.reader(open(ROOT / "data" / "cache" / "fred_DTWEXBGS.csv")))[1:] if b not in ("", ".")]
        return {rows[i][0]: (rows[i][1] / rows[i - 1][1] - 1) * 1e4 for i in range(1, len(rows))}
    # EUR/USD 16:55 ET close to close, inverted (dollar up = EUR/USD down)
    import futuresres.reporting.hd_grid as h
    if not (ROOT / "data" / "cache" / "hd_eurusd.npz").exists():
        h.build("eurusd")
    D, C = h.load("eurusd"); out = {}; prev = None
    for i, d in enumerate(D):
        if d.weekday() > 4:
            continue
        v = h.at(C, i, 1015)
        if np.isfinite(v) and prev is not None:
            out[d] = -(v / prev - 1) * 1e4
        prev = v if np.isfinite(v) else prev
    return out


def dax(source: str) -> dict:
    if source == "A21 window":
        return d111.target("DAX")
    z = a22.load("^GDAXI", "1d").with_columns(pl.col("ts").dt.date().alias("date")).unique("date", keep="last").sort("date")
    return {d: (c / o - 1) * 1e4 for d, o, c in zip(z["date"].to_list(), z["o"].to_list(), z["c"].to_list()) if o and c and o == o and c == c and o != c}


def independent() -> dict:
    out = {}
    for ds in ("DX-Y.NYB", "DTWEXBGS", "EURUSD"):
        P = dollar(ds); med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]]))
        for ts in ("A21 window", "^GDAXI"):
            Y = dax(ts)
            for form in ("all", "strong"):
                for pn, (lo, hi) in PER.items():
                    g = np.array([np.sign(P[d3.prev_weekday(d)]) * y - 0.3 for d, y in Y.items() if lo <= d <= hi and d3.prev_weekday(d) in P
                                  and P[d3.prev_weekday(d)] != 0 and (form == "all" or abs(P[d3.prev_weekday(d)]) > med)])
                    k = f"{ds:9} -> {ts:10} | {form:6} | {pn}"
                    out[k] = {"n": int(len(g)), "net": float(g.mean()), "t": _t(g)}
                    print(f"{k}: n {len(g):4} net {g.mean():+6.2f} t {_t(g):+5.2f}", flush=True)
    return out


def overlay() -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; n, rt = a23.MARKETS["FDXM"]; P = d111.predictor("DX-Y.NYB")
    med = float(np.median([abs(v) for d, v in P.items() if DISC[0] <= d <= DISC[1]])); out = {}
    for era in ("pre", "post"):
        (h, l, c), d = a23.market_paths("FDXM", era); dd = [x.astype(object) for x in d]
        x = np.array([P.get(d3.prev_weekday(v), 0.0) for v in dd])
        every = x < 0; strong = (x < 0) & (np.abs(x) > med)
        for name, pp in (("plan", (h, l, c)), ("every-day", a27.flip(h, l, c, every)), ("strong-only", a27.flip(h, l, c, strong))):
            r = a23.replay(s, pp, n, rt)
            row = {"p_payout": float((r["first"] > 0).mean()), "mean_net": float(r["net"].mean()), "p_net_positive": float((r["net"] > 0).mean())}
            out[f"{era} | {name}"] = row
            print(f"FDXM {era} {name:11}: P(payout) {row['p_payout']:.0%} mean {row['mean_net']:+7,.0f} P(net>0) {row['p_net_positive']:.0%} "
                  f"(short {every.mean() if name == 'every-day' else strong.mean() if name == 'strong-only' else 0:.0%})", flush=True)
    return out


def main(argv=None) -> int:
    res = {"independent": independent(), "overlay": overlay()}
    (ROOT / "reports" / "a34_daxdollar.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
