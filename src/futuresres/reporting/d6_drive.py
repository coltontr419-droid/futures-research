"""D-series family 6 - the opening drive (decisions.md 158): does a window's first 30 / 60 minutes predict the rest of it?
MNQ, MGC (owned Databento trades), NKD, DAX (corrected HistData CFD minute bars). Discovery 2010-06 -> 2017-12 only.

    python -m futuresres.reporting.d6_drive --build MNQ|MGC|NKD|DAX     (one market per process)
    python -m futuresres.reporting.d6_drive --scan
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
OUT = ROOT / "reports" / "d6_discovery.json"
DISC, VAL = d3.DISC, d3.VAL
#: market -> (source, tz, start, +30, +60, end) as (hh, mm) local
SPEC = {"MNQ": ("NQ_MNQ_spliced.parquet", "America/New_York", (9, 30), (10, 0), (10, 30), (16, 0)),
        "MGC": ("MGC.parquet", "America/New_York", (3, 0), (3, 30), (4, 0), (11, 30)),
        "NKD": ("jpxjpy", "Asia/Tokyo", (9, 0), (9, 30), (10, 0), (15, 0)),
        "DAX": ("grxeur", "Europe/Berlin", (9, 0), (9, 30), (10, 0), (17, 30))}


def build(market: str) -> None:
    src, tz, a, b, c, e = SPEC[market]
    times = {"p0": a, "p30": b, "p60": c, "pe": e}
    if market in ("MNQ", "MGC"):
        f = d3.databento(ROOT / "data" / "continuous" / src, times)
        ok = (pl.col("p0_ct") == pl.col("pe_ct")) & (pl.col("p30_ct") == pl.col("pe_ct")) & (pl.col("p60_ct") == pl.col("pe_ct"))
        f = f.filter(ok).select("date", *times)
    else:
        f = d3.histdata(src, {k: (tz, *v) for k, v in times.items()}).filter(pl.col("date").dt.weekday() <= 5)
    f = f.drop_nulls().with_columns(
        ((pl.col("p30") / pl.col("p0") - 1) * 1e4).alias("x30"), ((pl.col("pe") / pl.col("p30") - 1) * 1e4).alias("y30"),
        ((pl.col("p60") / pl.col("p0") - 1) * 1e4).alias("x60"), ((pl.col("pe") / pl.col("p60") - 1) * 1e4).alias("y60"))
    f.write_parquet(CACHE / f"d6_drive_{market}.parquet")
    print(market, f.height, "days", f["date"].min(), "->", f["date"].max(),
          {k: round(float(f[k].std()), 1) for k in ("x30", "y30", "x60", "y60")}, flush=True)


def load(market: str) -> pl.DataFrame:
    """The market's days, bad prints removed (decisions.md 149 rule on every column)."""
    f = pl.read_parquet(CACHE / f"d6_drive_{market}.parquet")
    keep = np.ones(f.height, bool)
    for k in ("x30", "y30", "x60", "y60"):
        v = f[k].to_numpy(); med = np.median(v); rsd = 1.4826 * np.median(np.abs(v - med))
        keep &= np.abs(v - med) <= 15 * rsd
    return f.filter(pl.Series(keep))


def days(market: str, k: int, lo: dt.date, hi: dt.date):
    f = load(market).filter((pl.col("date") >= lo) & (pl.col("date") <= hi)).sort("date")
    return np.array(f["date"].to_list()), f[f"y{k}"].to_numpy(), f[f"x{k}"].to_numpy()


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for m in SPEC:
        for k in (30, 60):
            D, Y, X = days(m, k, *DISC)
            assert D.max() <= DISC[1], "discovery read sealed data"
            med = float(np.median(np.abs(X))); ydm = Y - Y.mean()
            for form in ("all", "strong"):
                msk = np.ones(len(X), bool) if form == "all" else np.abs(X) > med
                z = np.sign(X[msk]) * ydm[msk]
                res.append({"market": m, "k": k, "form": form, "median_abs_pred": med, "n": int(msk.sum()), "mean_bps": float(z.mean()),
                            "sd_bps": float(z.std(ddof=1)), "t": _t(z), "rule": "follow" if z.mean() > 0 else "fade"})
    res.sort(key=lambda r: -abs(r["t"]))
    carried = [r for r in res if abs(r["t"]) > 1.96]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_passes_5pct": round(0.05 * len(res), 1),
           "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests on {DISC[0]} -> {DISC[1]}; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for r in res:
        print(f"  {r['market']} first {r['k']:2} min ({r['form']:6}) n {r['n']:5} {r['rule']:6} mean {r['mean_bps']:+6.2f} bps t {r['t']:+5.2f}"
              f"{'  CARRIED' if abs(r['t']) > 1.96 else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--build", choices=tuple(SPEC)); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.build:
        build(a.build)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
