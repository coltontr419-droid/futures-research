"""D-series family 16 - intraday momentum into the window's close (decisions.md 187): does the first 30 minutes, or the window so
far, predict the last 30 minutes? MNQ, MGC (owned trades), NKD, DAX (corrected HistData). Recent-period design.

    python -m futuresres.reporting.d16_close --build MNQ|MGC|NKD|DAX
    python -m futuresres.reporting.d16_close --scan
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
OUT = ROOT / "reports" / "d16_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
SPEC = {"MNQ": ("NQ_MNQ_spliced.parquet", "America/New_York", (9, 30), (10, 0), (15, 30), (16, 0)),
        "MGC": ("MGC.parquet", "America/New_York", (3, 0), (3, 30), (11, 0), (11, 30)),
        "NKD": ("jpxjpy", "Asia/Tokyo", (9, 0), (9, 30), (14, 30), (15, 0)),
        "DAX": ("grxeur", "Europe/Berlin", (9, 0), (9, 30), (17, 0), (17, 30))}
COST = {"MNQ": 0.56, "MGC": 1.0, "NKD": 0.4, "DAX": 0.5}


def build(market: str) -> None:
    src, tz, a, b, c, e = SPEC[market]
    times = {"p0": a, "p30": b, "pl": c, "pe": e}
    if market in ("MNQ", "MGC"):
        f = d3.databento(ROOT / "data" / "continuous" / src, times)
        ok = (pl.col("p0_ct") == pl.col("pe_ct")) & (pl.col("p30_ct") == pl.col("pe_ct")) & (pl.col("pl_ct") == pl.col("pe_ct"))
        f = f.filter(ok).select("date", *times)
    else:
        f = d3.histdata(src, {k: (tz, *v) for k, v in times.items()}).filter(pl.col("date").dt.weekday() <= 5)
    f = f.drop_nulls().with_columns(((pl.col("p30") / pl.col("p0") - 1) * 1e4).alias("first30"),
                                    ((pl.col("pl") / pl.col("p0") - 1) * 1e4).alias("sofar"),
                                    ((pl.col("pe") / pl.col("pl") - 1) * 1e4).alias("last30"))
    f.write_parquet(CACHE / f"d16_{market}.parquet")
    print(market, f.height, "days", f["date"].min(), "->", f["date"].max(), flush=True)


def load(market: str) -> pl.DataFrame:
    f = pl.read_parquet(CACHE / f"d16_{market}.parquet")
    keep = np.ones(f.height, bool)
    for k in ("first30", "sofar", "last30"):
        v = f[k].to_numpy(); med = np.median(v); rsd = 1.4826 * np.median(np.abs(v - med)); keep &= np.abs(v - med) <= 15 * rsd
    return f.filter(pl.Series(keep)).sort("date")


def rows(market: str, pred: str, lo, hi):
    f = load(market).filter((pl.col("date") >= lo) & (pl.col("date") <= hi))
    return np.array(f["date"].to_list()), f["last30"].to_numpy(), f[pred].to_numpy()


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for m in SPEC:
        for pred in ("first30", "sofar"):
            D, Y, X = rows(m, pred, *DISC)
            assert D.max() <= DISC[1] and D.min() >= DISC[0]
            med = float(np.median(np.abs(X)))
            for form in ("all", "strong"):
                msk = np.ones(len(X), bool) if form == "all" else np.abs(X) > med
                g = np.sign(X[msk]) * Y[msk]; direction = 1 if g.mean() > 0 else -1
                net = direction * g - COST[m]
                res.append({"market": m, "predictor": pred, "form": form, "median_abs_pred": med, "n": int(msk.sum()),
                            "rule": "follow" if direction == 1 else "fade", "gross_bps": float(direction * g.mean()), "net_bps": float(net.mean()), "t": _t(net)})
    for q in res:
        q["carried"] = bool(abs(q["t"]) > 1.96 and q["net_bps"] > 0)
    res.sort(key=lambda q: -q["t"])
    carried = [q for q in res if q["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests; ~{0.05 * len(res):.1f} by chance; carried {len(carried)}", flush=True)
    for q in res:
        print(f"  {q['market']} last 30 <- {q['predictor']:7} ({q['form']:6}) n {q['n']:4} {q['rule']:6} gross {q['gross_bps']:+6.2f} net {q['net_bps']:+6.2f} bps "
              f"t {q['t']:+5.2f}{'  CARRIED' if q['carried'] else ''}", flush=True)
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
