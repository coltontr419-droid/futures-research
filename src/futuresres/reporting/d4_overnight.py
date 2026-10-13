"""D-series family 4 - the overnight state at the open (decisions.md 152): does the state just before the plan's entry predict
the direction of the MNQ (09:30-16:00) and MGC (03:00-11:30) windows? Owned Databento 1-minute TRADES with volume.

    python -m futuresres.reporting.d4_overnight --build MNQ|MGC   (segments per day, one market per process)
    python -m futuresres.reporting.d4_overnight --scan        (discovery: 24 tests, 2010-17 ONLY)
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

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "cache"
TABLE = CACHE / "d4_overnight_table.parquet"
OUT = ROOT / "reports" / "d4_discovery.json"
DISC = (dt.date(2010, 6, 1), dt.date(2017, 12, 31))
VAL = (dt.date(2018, 1, 1), dt.date(2026, 8, 31))
#: market -> (file, {segment: (start minute, end minute) New York; start > end wraps from the previous day})
MARKETS = {
    "MNQ": ("NQ_MNQ_spliced.parquet", {"ON": (18 * 60, 9 * 60 + 30), "PRE": (9 * 60, 9 * 60 + 30),
                                       "WIN": (9 * 60 + 30, 16 * 60), "LH": (15 * 60, 16 * 60)}),
    "MGC": ("MGC.parquet", {"ON": (11 * 60 + 30, 3 * 60), "PRE": (2 * 60 + 30, 3 * 60),
                            "WIN": (3 * 60, 11 * 60 + 30), "LH": (10 * 60 + 30, 11 * 60 + 30)}),
}


def _next_weekday(col: pl.Expr) -> pl.Expr:
    nd = col + pl.duration(days=1)
    return pl.when(nd.dt.weekday() == 6).then(nd + pl.duration(days=2)).when(nd.dt.weekday() == 7).then(nd + pl.duration(days=1)).otherwise(nd)


def segments(market: str) -> pl.DataFrame:
    """Per segment and day: open, close, high, low, return, close location, volume and variance ratios. Lazy and one segment
    at a time (the 2.7 GB machine)."""
    fname, segs = MARKETS[market]
    base = (pl.scan_parquet(ROOT / "data" / "continuous" / fname)
            .select("ts_event", pl.col("open").cast(pl.Float32), pl.col("high").cast(pl.Float32), pl.col("low").cast(pl.Float32),
                    pl.col("close").cast(pl.Float32), pl.col("volume").cast(pl.Int32), pl.col("contract").cast(pl.Categorical))
            .with_columns(pl.col("ts_event").dt.convert_time_zone("America/New_York").alias("t")).sort("t")
            .with_columns(pl.col("t").dt.date().alias("date"),
                          (pl.col("t").dt.hour().cast(pl.Int32) * 60 + pl.col("t").dt.minute().cast(pl.Int32)).alias("m"),
                          pl.col("close").log().diff().cast(pl.Float32).fill_null(0.0).alias("lr"))
            .drop("ts_event", "t"))
    out = []
    for name, (a, b) in segs.items():
        if a < b:
            x = base.filter((pl.col("m") >= a) & (pl.col("m") < b)).with_columns(pl.col("date").alias("D"))
        else:
            x = base.filter((pl.col("m") >= a) | (pl.col("m") < b)).with_columns(
                pl.when(pl.col("m") >= a).then(_next_weekday(pl.col("date"))).otherwise(pl.col("date")).alias("D"))
        g = (x.group_by("D").agg(pl.col("open").first().alias("o"), pl.col("close").last().alias("c"), pl.col("high").max().alias("h"),
                                 pl.col("low").min().alias("l"), pl.col("volume").sum().alias("v"), (pl.col("lr").slice(1) ** 2).sum().alias("rv"),
                                 pl.col("contract").n_unique().alias("nct"), pl.len().alias("bars"))
             .filter((pl.col("nct") == 1) & (pl.col("D").dt.weekday() <= 5)).sort("D")
             .with_columns(((pl.col("c") / pl.col("o") - 1) * 1e4).alias("ret"),
                           pl.when(pl.col("h") > pl.col("l")).then((pl.col("c") - pl.col("l")) / (pl.col("h") - pl.col("l")) - 0.5).alias("loc"),
                           (pl.col("v") / pl.col("v").shift(1).rolling_mean(20)).alias("vratio"),
                           (pl.col("rv") / pl.col("rv").shift(1).rolling_mean(20)).alias("rvratio"))
             .select(pl.lit(market).alias("market"), pl.lit(name).alias("seg"), "D", "o", "c", "h", "l", "ret", "loc", "vratio", "rvratio", "bars")
             .collect())
        out.append(g)
    return pl.concat(out)


def build(market: str) -> None:
    t = segments(market)
    t.write_parquet(CACHE / f"d4_overnight_{market}.parquet")
    for (m, s), g in t.group_by(["market", "seg"], maintain_order=True):
        print(f"{m} {s:3} {g.height:5} days {g['D'].min()} -> {g['D'].max()}  ret mean {g['ret'].mean():+6.2f} sd {g['ret'].std():6.1f}  "
              f"bars median {g['bars'].median():.0f}", flush=True)


# ------------------------------------------------------------------ tests
def frame(market: str) -> dict:
    """D -> {segment fields}, with the bad-print rule of decisions.md 149 on every segment return."""
    t = pl.read_parquet(CACHE / f"d4_overnight_{market}.parquet")
    out: dict = {}
    for (s,), g in t.group_by(["seg"]):
        r = g["ret"].to_numpy(); med = np.nanmedian(r); rsd = 1.4826 * np.nanmedian(np.abs(r - med))
        for row, ok in zip(g.iter_rows(named=True), np.abs(r - med) <= 15 * rsd):
            if ok:
                out.setdefault(row["D"], {})[s] = row
    return out


#: (name, predictor field, gate) - gate None = every day; "strong" = |predictor| > its 2010-17 median; ("ratio", seg, field) =
#: that ratio above its 2010-17 median; "outside" = the entry price outside the previous window's range
TESTS = [("ON_loc", ("ON", "loc", "same"), None), ("ON_loc", ("ON", "loc", "same"), "strong"),
         ("ON_ret|vol", ("ON", "ret", "same"), ("ON", "vratio")), ("ON_ret|rv", ("ON", "ret", "same"), ("ON", "rvratio")),
         ("PRE_ret", ("PRE", "ret", "same"), None), ("PRE_ret", ("PRE", "ret", "same"), "strong"),
         ("PRE_ret|vol", ("PRE", "ret", "same"), ("PRE", "vratio")),
         ("prevWIN_loc", ("WIN", "loc", "prev"), None), ("prevWIN_loc", ("WIN", "loc", "prev"), "strong"),
         ("prevLH_ret", ("LH", "ret", "prev"), None), ("prevLH_ret", ("LH", "ret", "prev"), "strong"),
         ("ON_ret|outside", ("ON", "ret", "same"), "outside")]


def rows(F: dict, pred, lo: dt.date, hi: dt.date):
    """dates, target window return (bps), predictor, gate values for one market's frame."""
    seg, field, when = pred
    days = sorted(F); prev = {d: days[i - 1] for i, d in enumerate(days) if i}
    D, Y, X, G = [], [], [], []
    for d in days:
        if not (lo <= d <= hi) or "WIN" not in F[d]:
            continue
        src = F[d] if when == "same" else F.get(prev.get(d), {})
        if seg not in src or src[seg][field] is None:
            continue
        p = prev.get(d)
        out = None
        if p is not None and "WIN" in F[p]:
            e = F[d]["WIN"]["o"]; out = bool(e > F[p]["WIN"]["h"] or e < F[p]["WIN"]["l"])
        D.append(d); Y.append(F[d]["WIN"]["ret"]); X.append(src[seg][field]); G.append({"outside": out, **{
            f"{s}:{k}": F[d][s][k] for s in ("ON", "PRE") if s in F[d] for k in ("vratio", "rvratio")}})
    return np.array(D), np.array(Y, float), np.array(X, float), G


def gate_mask(gate, X, G, thresholds: dict) -> np.ndarray:
    if gate is None:
        return np.ones(len(X), bool)
    if gate == "strong":
        return np.abs(X) > thresholds["abs_pred"]
    if gate == "outside":
        return np.array([g["outside"] is True for g in G])
    key = f"{gate[0]}:{gate[1]}"
    v = np.array([g.get(key) if g.get(key) is not None else np.nan for g in G], float)
    return np.nan_to_num(v, nan=-1) > thresholds["gate"]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    res = []
    for m in MARKETS:
        F = frame(m)
        for name, pred, gate in TESTS:
            D, Y, X, G = rows(F, pred, *DISC)
            assert D.max() <= DISC[1], "discovery read sealed data"
            ok = np.isfinite(X); D, Y, X = D[ok], Y[ok], X[ok]; G = [g for g, k in zip(G, ok) if k]
            th = {"abs_pred": float(np.median(np.abs(X)))}
            if isinstance(gate, tuple):
                v = np.array([g.get(f"{gate[0]}:{gate[1]}") for g in G], float); th["gate"] = float(np.nanmedian(v))
            msk = gate_mask(gate, X, G, th)
            ydm = Y - Y.mean(); z = np.sign(X[msk]) * ydm[msk]
            res.append({"market": m, "test": name, "predictor": list(pred), "gate": gate if not isinstance(gate, tuple) else list(gate),
                        "thresholds": th, "n": int(msk.sum()), "mean_bps": float(z.mean()), "sd_bps": float(z.std(ddof=1)), "t": _t(z),
                        "rule": "follow" if z.mean() > 0 else "fade"})
    res.sort(key=lambda r: -abs(r["t"]))
    carried = [r for r in res if abs(r["t"]) > 1.96]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_passes_5pct": round(0.05 * len(res), 1),
           "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"{len(res)} tests on {DISC[0]} -> {DISC[1]}; ~{0.05 * len(res):.1f} pass by chance; carried {len(carried)}", flush=True)
    for r in res:
        g = r["gate"] if r["gate"] is None or isinstance(r["gate"], str) else f"{r['gate'][0]} {r['gate'][1]} > median"
        print(f"  {r['market']} {r['test']:15} gate {str(g):22} n {r['n']:5} {r['rule']:6} mean {r['mean_bps']:+6.2f} t {r['t']:+5.2f}"
              f"{'  CARRIED' if abs(r['t']) > 1.96 else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--build", choices=tuple(MARKETS)); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.build:
        build(a.build)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
