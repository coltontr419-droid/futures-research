"""A31 - D122 (soybeans fall after the Brazilian real weakens) stress-tested before any use (decisions.md 382). No trial.
(1) Independent data: USD/BRL from Yahoo or FRED DEXBZUS; soybeans from Yahoo ZS=F or the SOYB ETF; 1.5 / 2 / 2.5 sigma; three periods.
(2) The ZS account overlay: A23 engine, 3 ZS, drift removed, plan (always long) vs short on the session after a 2-sigma real weakening.

    python -m futuresres.reporting.a31_d122
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
import futuresres.reporting.d10_universe as d10

ROOT = Path(__file__).resolve().parents[3]
PERIODS = {"2010-17": (dt.date(2010, 1, 1), dt.date(2017, 12, 31)), "2018-22": (dt.date(2018, 1, 1), dt.date(2022, 12, 31)),
           "2023-26": (dt.date(2023, 1, 1), dt.date(2026, 8, 31))}


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def brl(source: str) -> list:
    if source == "yahoo":
        z = a22.load("BRL=X", "1d").with_columns(pl.col("ts").dt.convert_time_zone("UTC").dt.date().alias("date")).unique("date", keep="last").sort("date")
        return list(zip(z["date"].to_list(), z["c"].to_list()))
    rows = [(dt.date.fromisoformat(a), float(b)) for a, b in list(csv.reader(open(ROOT / "data" / "cache" / "fred_DEXBZUS.csv")))[1:] if b not in ("", ".")]
    return rows


def shocks(source: str, k: float) -> dict:
    s = [(d, v) for d, v in brl(source) if v and v > 0]
    ds = [d for d, _ in s]; c = np.array([v for _, v in s]); ch = np.r_[np.nan, np.diff(np.log(c)) * 1e4]; out = {}
    for i in range(61, len(ds)):
        if np.isfinite(ch[i]) and ds[i].weekday() < 5:
            sd = np.nanstd(ch[i - 60:i], ddof=1)
            if abs(ch[i]) > k * sd:
                out[ds[i]] = float(ch[i])
    return out


def soy(source: str) -> dict:
    if source == "yahoo":
        return d10.series()["ZS"]
    z = a22.load("SOYB", "1d").with_columns(pl.col("ts").dt.date().alias("date"))
    r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy(); md = np.nanmedian(r); rs = 1.4826 * np.nanmedian(np.abs(r - md))
    return {d: float(x) for d, x in zip(z["date"].to_list(), r) if np.isfinite(x) and abs(x - md) <= 15 * rs}


def _nxt(d):
    return d + dt.timedelta(days=1 if d.weekday() < 4 else 3)


def independent() -> dict:
    out = {}
    for bsrc, ssrc, cost in (("yahoo", "yahoo", 0.7), ("fred", "yahoo", 0.7), ("yahoo", "soyb", 0.0), ("fred", "soyb", 0.0)):
        Y = soy(ssrc)
        for k in (1.5, 2.0, 2.5):
            sh = shocks(bsrc, k)
            for pn, (lo, hi) in PERIODS.items():
                g = np.array([-np.sign(x) * Y[_nxt(d)] - cost for d, x in sh.items() if lo <= d <= hi and _nxt(d) in Y])
                key = f"BRL {bsrc} x soy {ssrc} | {k} sigma | {pn}"
                out[key] = {"n": int(len(g)), "net_bps": float(g.mean()) if len(g) else None, "t": _t(g) if len(g) > 2 else None}
                print(f"{key:44}: n {len(g):3} net {g.mean() if len(g) else float('nan'):+7.2f} t {_t(g) if len(g) > 2 else float('nan'):+5.2f}", flush=True)
    return out


def overlay() -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; n, rt = a23.MARKETS["ZS"]; sh = shocks("yahoo", 2.0); out = {}
    short_days = {_nxt(d) for d, x in sh.items() if x > 0}            # the real weakened -> short the next session
    for era in ("pre", "post"):
        (h, l, c), d = a23.market_paths("ZS", era)
        dd = np.array([x.astype(object) for x in d]); mask = np.array([x in short_days for x in dd])
        for name, pp in (("plan, always long", (h, l, c)), ("overlay, D122 short days", a27.flip(h, l, c, mask))):
            r = a23.replay(s, pp, n, rt)
            row = {"p_payout": float((r["first"] > 0).mean()), "mean_net": float(r["net"].mean()), "p_net_positive": float((r["net"] > 0).mean()),
                   "short_share": float(mask.mean())}
            out[f"{era} | {name}"] = row
            print(f"{era} {name:26}: P(payout) {row['p_payout']:.0%} mean net {row['mean_net']:+7,.0f} P(net>0) {row['p_net_positive']:.0%} "
                  f"(short days {mask.mean():.1%})", flush=True)
    return out


def main(argv=None) -> int:
    res = {"independent": independent(), "overlay": overlay()}
    (ROOT / "reports" / "a31_d122.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
