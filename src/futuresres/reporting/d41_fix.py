"""D-series family 41 - the London 16:00 FX fix (decisions.md 252): does the move into the fix (15:30 -> 16:00 London) continue or
unwind over 16:00 -> 16:30? Six currency futures from free HistData minute bars on the corrected clock (decisions.md 140).
Recent-period design: discovery 2018-01 -> 2022-12; validation 2023-01 -> 2026-08 sealed.

    python -m futuresres.reporting.d41_fix --scan
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
FX = ROOT / "data" / "fx_histdata"
OUT = ROOT / "reports" / "d41_discovery.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
#: future -> (HistData symbol, +1 if the pair is quoted like the future, -1 if inverted, cost bps)
PAIRS = {"6E": ("eurusd", 1, 0.3), "6B": ("gbpusd", 1, 0.5), "6J": ("usdjpy", -1, 0.5), "6A": ("audusd", 1, 0.5),
         "6C": ("usdcad", -1, 0.5), "6S": ("usdchf", -1, 0.5)}
MARKS = (900, 930, 960, 990)                 # 15:00, 15:30, 16:00, 16:30 London


def _files(sym: str, lo: dt.date, hi: dt.date):
    for f in sorted(FX.glob(f"{sym}_*.zip")):
        y = int(f.stem.split("_")[1][:4])
        if lo.year <= y <= hi.year:
            yield f


def marks(sym: str, lo: dt.date, hi: dt.date) -> dict:
    """date -> {minute: last close at or before that London minute (within 5 minutes)}; bars are stamped at their open."""
    out = {}
    for f in _files(sym, lo, hi):
        z = zipfile.ZipFile(f); n = [x for x in z.namelist() if x.lower().endswith(".csv")][0]
        d = pl.read_csv(z.read(n), separator=";", has_header=False, new_columns=["ts", "o", "h", "l", "c"], columns=[0, 1, 2, 3, 4])
        d = d.with_columns(pl.col("ts").str.strptime(pl.Datetime, "%Y%m%d %H%M%S").dt.replace_time_zone("America/New_York", ambiguous="earliest", non_existent="null")
                           .dt.convert_time_zone("Europe/London").alias("t")).drop_nulls("t")
        d = d.with_columns(pl.col("t").dt.date().alias("date"),
                           (pl.col("t").dt.hour().cast(pl.Int32) * 60 + pl.col("t").dt.minute().cast(pl.Int32) + 1).alias("m"))
        d = d.filter(pl.col("m").is_between(MARKS[0] - 5, MARKS[-1]) & (pl.col("t").dt.weekday() <= 5) & pl.col("date").is_between(lo, hi))
        for (date,), g in d.group_by(["date"]):
            m = g["m"].to_numpy(); c = g["c"].to_numpy(); o = np.argsort(m); m, c = m[o], c[o]
            v = {}
            for x in MARKS:
                k = np.where((m <= x) & (m > x - 5))[0]
                v[x] = float(c[k[-1]]) if len(k) else None
            out[date] = v
    return out


def rows(fut: str, lo: dt.date, hi: dt.date, pre=(930, 960), tgt=(960, 990)):
    """(dates, pre-window bps, target bps) in the future's direction."""
    sym, sg, _ = PAIRS[fut]; M = marks(sym, lo, hi); D, X, Y = [], [], []
    for d in sorted(M):
        v = M[d]
        if None in (v[pre[0]], v[pre[1]], v[tgt[0]], v[tgt[1]]):
            continue
        D.append(d); X.append(sg * (v[pre[1]] / v[pre[0]] - 1) * 1e4); Y.append(sg * (v[tgt[1]] / v[tgt[0]] - 1) * 1e4)
    return np.array(D), np.array(X), np.array(Y)


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for fut, (_, _, cost) in PAIRS.items():
        D, X, Y = rows(fut, *DISC); assert D.max() <= DISC[1], "discovery read sealed data"
        med = float(np.median(np.abs(X)))
        for form, mask in (("all", np.ones(len(X), bool)), ("strong", np.abs(X) > med)):
            g = np.sign(X[mask]) * Y[mask]; dirn = 1 if g.mean() > 0 else -1; net = dirn * g - cost
            r = {"pair": fut, "form": form, "median_abs_pre_bps": med, "n": int(mask.sum()), "rule": "follow" if dirn == 1 else "fade",
                 "gross_bps": float(dirn * g.mean()), "net_bps": float(net.mean()), "t": _t(net)}
            r["carried"] = bool(r["t"] > 1.96 and r["net_bps"] > 0); res.append(r)
            print(f"{fut} {form:6}: n {r['n']:4} {r['rule']:6} gross {r['gross_bps']:+5.2f} net {r['net_bps']:+5.2f} bps t {r['t']:+5.2f}"
                  f"{'  CARRIED' if r['carried'] else ''}", flush=True)
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--scan", action="store_true")
    if ap.parse_args(argv).scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
