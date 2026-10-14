"""A33 - stress tests for D151 (ZS fades a ZM shock) and D139 (NKD fades a BTC=F shock), decisions.md 430. No trial.

    python -m futuresres.reporting.a33_stress
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
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def _ser_oc(sym, utc=False, cc=False):
    z = a22.load(sym, "1d")
    ts = z["ts"].dt.convert_time_zone("UTC") if utc else z["ts"]
    z = z.with_columns(ts.dt.date().alias("date")).filter(pl.col("date").dt.weekday() <= 5).unique("date", keep="last").sort("date")
    ds = z["date"].to_list()
    r = (np.r_[np.nan, np.diff(np.log(z["c"].to_numpy()))] * 1e4) if cc else ((z["c"] / z["o"] - 1) * 1e4).to_numpy()
    md = np.nanmedian(r); rs = 1.4826 * np.nanmedian(np.abs(r - md))
    return {d: float(x) for d, x in zip(ds, r) if np.isfinite(x) and abs(x - md) <= 15 * rs}


def _shocks(S: dict, k: float) -> dict:
    ds = sorted(S); r = np.array([S[d] for d in ds]); out = {}
    for i in range(60, len(r)):
        if abs(r[i]) > k * r[i - 60:i].std(ddof=1):
            out[ds[i]] = float(r[i])
    return out


def _cell(sh, Y, lo, hi, cost, sign):
    g = np.array([sign * np.sign(x) * Y[d] - cost for p, x in sh.items() for d in [p + dt.timedelta(days=1 if p.weekday() < 4 else 3)]
                  if lo <= d <= hi and d in Y])
    return {"n": int(len(g)), "net": float(g.mean()) if len(g) else None, "t": _t(g) if len(g) > 2 else None}


def independent() -> dict:
    out = {}
    P = {"ZM (Yahoo)": _ser_oc("ZM=F")}
    T = {"ZS (Yahoo)": (d111.target("ZS"), 0.7), "SOYB": (_ser_oc("SOYB"), 0.0)}
    per = {"2010-20": (dt.date(2010, 1, 1), dt.date(2020, 12, 31)), "2021-24": (dt.date(2021, 1, 1), dt.date(2024, 12, 31)),
           "2025-26": (dt.date(2025, 1, 1), dt.date(2026, 8, 31))}
    for pn, S in P.items():
        for k in (1.5, 2.0, 2.5):
            sh = _shocks(S, k)
            for tn, (Y, cost) in T.items():
                for per_n, (lo, hi) in per.items():
                    out[f"D151 | {pn} -> {tn} | {k} | {per_n}"] = _cell(sh, Y, lo, hi, cost, -1)
    P = {"BTC=F": _ser_oc("BTC=F"), "BTC-USD spot": _ser_oc("BTC-USD", utc=True, cc=True)}
    T = {"NKD window (A21)": (d111.target("NKD"), 0.2), "NKD=F (Yahoo CME session)": (_ser_oc("NKD=F"), 0.2)}
    per = {"2018-20": (dt.date(2018, 1, 1), dt.date(2020, 12, 31)), "2021-24": (dt.date(2021, 1, 1), dt.date(2024, 12, 31)),
           "2025-26": (dt.date(2025, 1, 1), dt.date(2026, 8, 31))}
    for pn, S in P.items():
        for k in (1.5, 2.0, 2.5):
            sh = _shocks(S, k)
            for tn, (Y, cost) in T.items():
                for per_n, (lo, hi) in per.items():
                    out[f"D139 | {pn} -> {tn} | {k} | {per_n}"] = _cell(sh, Y, lo, hi, cost, -1)
    for k, v in out.items():
        print(f"{k:62}: n {v['n']:3} net {v['net'] if v['net'] is None else round(v['net'], 1):>7} t {v['t'] if v['t'] is None else round(v['t'], 2):>6}", flush=True)
    return out


def overlay() -> dict:
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; out = {}

    def short_days(S):
        sh = _shocks(S, 2.0)
        return {p + dt.timedelta(days=1 if p.weekday() < 4 else 3) for p, x in sh.items() if x > 0}
    for label, market, S in (("D151 ZS", "ZS", _ser_oc("ZM=F")), ("D139 NKD", "NKD", _ser_oc("BTC=F"))):
        sd = short_days(S); n, rt = a23.MARKETS[market]
        for era in ("pre", "post"):
            (h, l, c), d = a23.market_paths(market, era)
            dd = np.array([x.astype(object) for x in d]); mask = np.array([x in sd for x in dd])
            for name, pp in (("plan", (h, l, c)), ("overlay", a27.flip(h, l, c, mask))):
                r = a23.replay(s, pp, n, rt)
                row = {"p_payout": float((r["first"] > 0).mean()), "mean_net": float(r["net"].mean()), "p_net_positive": float((r["net"] > 0).mean()),
                       "short_share": float(mask.mean())}
                out[f"{label} | {era} | {name}"] = row
                print(f"{label} {era} {name:8}: P(payout) {row['p_payout']:.0%} mean {row['mean_net']:+7,.0f} P(net>0) {row['p_net_positive']:.0%} (short {mask.mean():.1%})", flush=True)
    return out


def main(argv=None) -> int:
    res = {"independent": independent(), "overlay": overlay()}
    (ROOT / "reports" / "a33_stress.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
