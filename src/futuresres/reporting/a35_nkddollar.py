"""A35 - the NKD dollar-week theme stress-tested (decisions.md 452). No trial.

    python -m futuresres.reporting.a35_nkddollar
"""

from __future__ import annotations

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
import futuresres.reporting.a34_daxdollar as a34
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
PER = {"2010-20": (dt.date(2010, 1, 1), dt.date(2020, 12, 31)), "2021-24": DISC, "2025-26": (dt.date(2025, 1, 1), dt.date(2026, 8, 31))}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def weak_dollar_week(source: str) -> dict:
    """+ = the dollar weakened over the 5 weekdays ending that date."""
    S = d111.predictor("6E=F") if source == "6E=F" else {d: -v for d, v in a34.dollar(source).items()}
    ds = sorted(d for d in S if d.weekday() < 5); r = np.array([S[d] for d in ds])
    return {ds[i]: float(r[i - 4:i + 1].sum()) for i in range(4, len(ds))}


def nikkei(source: str) -> dict:
    if source == "A21 window":
        return d111.target("NKD")
    z = a22.load("NKD=F", "1d").with_columns(pl.col("ts").dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5).unique("date", keep="last").sort("date")
    r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy(); md = np.nanmedian(r); rs = 1.4826 * np.nanmedian(np.abs(r - md))
    return {d: float(x) for d, x in zip(z["date"].to_list(), r) if np.isfinite(x) and abs(x - md) <= 15 * rs}


def independent() -> dict:
    out = {}
    for ds in ("6E=F", "DX-Y.NYB", "DTWEXBGS", "EURUSD"):
        W = weak_dollar_week(ds); med = float(np.median([abs(v) for d, v in W.items() if DISC[0] <= d <= DISC[1]]))
        for ts in ("A21 window", "NKD=F"):
            Y = nikkei(ts)
            for form in ("all", "strong"):
                for pn, (lo, hi) in PER.items():
                    g = np.array([np.sign(W[d3.prev_weekday(d)]) * y - 0.2 for d, y in Y.items() if lo <= d <= hi and d3.prev_weekday(d) in W
                                  and W[d3.prev_weekday(d)] != 0 and (form == "all" or abs(W[d3.prev_weekday(d)]) > med)])
                    k = f"{ds:9} -> {ts:10} | {form:6} | {pn}"
                    out[k] = {"n": int(len(g)), "net": float(g.mean()), "t": _t(g)}
                    print(f"{k}: n {len(g):4} net {g.mean():+6.2f} t {_t(g):+5.2f}", flush=True)
    return out


def overlay() -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; n, rt = a23.MARKETS["NKD"]; W = weak_dollar_week("6E=F")
    med = float(np.median([abs(v) for d, v in W.items() if DISC[0] <= d <= DISC[1]])); out = {}
    for era in ("pre", "post"):
        (h, l, c), d = a23.market_paths("NKD", era); dd = [x.astype(object) for x in d]
        x = np.array([W.get(d3.prev_weekday(v), 0.0) for v in dd])
        every = x < 0; strong = (x < 0) & (np.abs(x) > med)
        for name, pp, sh in (("plan", (h, l, c), 0.0), ("every-day", a27.flip(h, l, c, every), every.mean()), ("strong-only", a27.flip(h, l, c, strong), strong.mean())):
            r = a23.replay(s, pp, n, rt)
            row = {"p_payout": float((r["first"] > 0).mean()), "mean_net": float(r["net"].mean()), "p_net_positive": float((r["net"] > 0).mean()), "short_share": float(sh)}
            out[f"{era} | {name}"] = row
            print(f"NKD {era} {name:11}: P(payout) {row['p_payout']:.0%} mean {row['mean_net']:+7,.0f} P(net>0) {row['p_net_positive']:.0%} (short {sh:.0%})", flush=True)
    return out


def main(argv=None) -> int:
    res = {"independent": independent(), "overlay": overlay()}
    (ROOT / "reports" / "a35_nkddollar.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
