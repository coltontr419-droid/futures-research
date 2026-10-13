"""A26 - D32 in the plan (decisions.md 163-164): a silver account trading the London window (03:00 -> 11:30 New York) with the
confirmed direction rule - follow silver's own overnight move (11:30 -> 03:00) on days it exceeds the 2010-17 median, long
otherwise - against the same account always long, alone and as a five-account book. A COMPUTATION; no trial.

    python -m futuresres.reporting.a26_silver --build       (window paths from HistData XAG/USD, corrected clock; cached)
    python -m futuresres.reporting.a26_silver --run

Paths: 1-minute window paths relative to the 03:00 price, drift REMOVED within each era (so the rule is credited only with
skill beyond drift; silver's 2024-26 rally is not counted), in dollars at today's SIL value (1,000 oz). Size by the plan's rule:
daily swing nearest $2,900, at most 30 micros; round trip $3.32 a contract (estimate, as MGC). Engine: A23 (reproduces the live
engine), the 50K Daily plan, stops at the stop price, 84-day back-to-back replay from every start date. Eras 2010-20 (contains
the 2010-17 discovery: in-sample for the rule) and 2021-26 (out of sample).
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

import futuresres.reporting.a21_more_accounts as a21
import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.d7_london as d7
import futuresres.signals.d_london as dl

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "cache"
ERAS = a21.ERAS
RT = 3.32


def build() -> None:
    tz = ZoneInfo("America/New_York"); T = 510
    sessions = {}
    for f in sorted(a21.FX_DIR.glob("xagusd_*.zip")):
        z = zipfile.ZipFile(f); n = [x for x in z.namelist() if x.lower().endswith(".csv")][0]
        d = pl.read_csv(z.read(n), separator=";", has_header=False, new_columns=["ts", "o", "h", "l", "c"], columns=[0, 1, 2, 3, 4])
        d = d.with_columns(pl.col("ts").str.strptime(pl.Datetime, "%Y%m%d %H%M%S")
                           .dt.replace_time_zone("America/New_York", ambiguous="earliest", non_existent="null").alias("t")).drop("ts").drop_nulls("t")
        d = d.with_columns(pl.col("t").dt.date().alias("date"),
                           (pl.col("t").dt.hour().cast(pl.Int32) * 60 + pl.col("t").dt.minute().cast(pl.Int32) - 180).alias("m"))
        d = d.filter((pl.col("m") >= 0) & (pl.col("m") < T) & (pl.col("t").dt.weekday() <= 5))
        for (date,), g in d.group_by(["date"], maintain_order=True):
            sessions[date] = g.select("m", "o", "h", "l", "c")
        del d
    for era, (lo, hi) in ERAS.items():
        D, H, L, C = [], [], [], []
        for date in sorted(sessions):
            if not (lo <= date <= hi):
                continue
            g = sessions[date].sort("m"); m = g["m"].to_numpy()
            if len(m) < 0.8 * T or m[0] > 5:
                continue
            p0 = float(g["o"][0])
            c = np.full(T, np.nan); h = c.copy(); l = c.copy()
            c[m] = g["c"].to_numpy(); h[m] = g["h"].to_numpy(); l[m] = g["l"].to_numpy()
            idx = np.where(np.isnan(c), 0, np.arange(T)); np.maximum.accumulate(idx, out=idx)
            c[0] = c[0] if not np.isnan(c[0]) else p0
            c = c[idx]; h = np.where(np.isnan(h), c, h); l = np.where(np.isnan(l), c, l)
            D.append(date); C.append(c / p0 - 1); H.append(h / p0 - 1); L.append(l / p0 - 1)
        H, L, C = (np.array(x, np.float64) for x in (H, L, C))
        adj = -C[:, -1].mean() * (np.arange(1, T + 1) / T)
        np.savez(CACHE / f"a26_SIL_{era}.npz", d=np.array(D, dtype="datetime64[D]"), h=(H + adj).astype(np.float32),
                 l=(L + adj).astype(np.float32), c=(C + adj).astype(np.float32))
        print("silver London window", era, len(D), "sessions; window SD", f"{C[:, -1].std() * 1e4:.1f} bps", flush=True)


def notional() -> float:
    return 1000.0 * a21._last_price("xagusd")


def paths(era: str, rule: bool):
    """One-SIL gross $ paths; with rule=True each strong day whose overnight move was down is flipped (a short)."""
    z = np.load(CACHE / f"a26_SIL_{era}.npz"); usd = np.float32(notional())
    h, l, c, d = z["h"] * usd, z["l"] * usd, z["c"] * usd, z["d"].astype("datetime64[D]")
    if rule:
        thr = dl.cells()["D32"]["median_abs_pred"]
        _, pre = d7.series("xagusd")
        x = np.array([pre.get(dd.astype(object), 0.0) for dd in d])
        short = (np.abs(x) > thr) & (x < 0)
        h, l, c = np.where(short[:, None], -l, h), np.where(short[:, None], -h, l), np.where(short[:, None], -c, c)
        return h, l, c, d, float(short.mean()), float((np.abs(x) > thr).mean())
    return h, l, c, d, 0.0, 0.0


def run() -> dict:
    import warnings
    warnings.filterwarnings("ignore")
    s = a23.specs()["50K Daily"]; out = {}
    sd1 = float(np.load(CACHE / "a26_SIL_post.npz")["c"][:, -1].std() * notional())
    n = int(min(range(1, 31), key=lambda k: abs(k * sd1 - 2900.0)))
    out["size"] = {"SIL": n, "one_contract_daily_sd": sd1, "notional_one": notional()}
    print(f"SIL: one contract ${notional():,.0f}, window SD ${sd1:,.0f}; size {n} (swing ${n * sd1:,.0f})", flush=True)
    A24 = {era: json.loads((CACHE / f"a24_replay_{era}.json").read_text()) for era in ERAS}
    for era in ERAS:
        out[era] = {}
        acc = {}
        for lab, rule in (("SIL always long", False), ("SIL with D32", True)):
            h, l, c, d, sh, strong = paths(era, rule)
            r = a23.replay(s, (h, l, c), n, RT)
            acc[lab] = {"date": d[r["start"]].astype(str).tolist(), "net": r["net"], "first": r["first"], "fees": r["fees"]}
            out[era][lab] = {"p_payout": float((r["first"] > 0).mean()), "mean_net": float(r["net"].mean()),
                             "p_net_positive": float((r["net"] > 0).mean()), "short_days": sh, "strong_days": strong}
            print(f"{era} {lab:16}: P(payout) {(r['first'] > 0).mean():.0%} mean net {r['net'].mean():+7,.0f} P(net>0) {(r['net'] > 0).mean():.0%}"
                  f"{f'  (rule: short on {sh:.0%} of days, acts on {strong:.0%})' if rule else ''}", flush=True)
        for m in ("MNQ", "MGC", "MCL", "NKD", "FDXM", "ZS"):
            x = A24[era][f"{m}|plan"]; acc[m] = {"date": x["date"], "net": np.array(x["net"]), "first": np.array(x["first"]), "fees": np.array(x["fees"])}
        books = {"5 live": ("MNQ", "MGC", "MCL", "NKD", "FDXM"),
                 "silver (always long) for crude": ("MNQ", "MGC", "SIL always long", "NKD", "FDXM"),
                 "silver with D32 for crude": ("MNQ", "MGC", "SIL with D32", "NKD", "FDXM"),
                 "5 with soybeans": ("MNQ", "MGC", "ZS", "NKD", "FDXM"),
                 "silver with D32 for crude, soybeans for DAX": ("MNQ", "MGC", "SIL with D32", "NKD", "ZS")}
        for name, keys in books.items():
            common = None
            for k in keys:
                common = set(acc[k]["date"]) if common is None else common & set(acc[k]["date"])
            common = sorted(common); net = 0; fees = 0
            for k in keys:
                ix = {dd: i for i, dd in enumerate(acc[k]["date"])}; ii = [ix[dd] for dd in common]
                net = net + np.asarray(acc[k]["net"])[ii]; fees = fees + np.asarray(acc[k]["fees"])[ii]
            row = {"starts": len(common), "mean_net": float(net.mean()), "median_net": float(np.median(net)), "p_net_positive": float((net > 0).mean()),
                   "net_p10": float(np.quantile(net, 0.1)), "worst": float(net.min()), "mean_fees": float(fees.mean())}
            out[era][name] = row
            print(f"{era} {name:45}: mean {row['mean_net']:+8,.0f} median {row['median_net']:+8,.0f} P(net>0) {row['p_net_positive']:.0%} "
                  f"p10 {row['net_p10']:+8,.0f} ({row['starts']} starts)", flush=True)
        # daily correlation of the silver window with the gold window
        zs = np.load(CACHE / f"a26_SIL_{era}.npz"); import futuresres.reporting.d3_relay as d3
        g = d3.series()["MGC_win"]; sv = dict(zip(zs["d"].astype("datetime64[D]").astype(object).tolist(), zs["c"][:, -1].tolist()))
        cm = sorted(set(g) & set(sv)); out[era]["corr_silver_gold_window"] = float(np.corrcoef([g[k] for k in cm], [sv[k] for k in cm])[0, 1])
        print(f"{era} silver-gold window correlation {out[era]['corr_silver_gold_window']:+.2f}", flush=True)
    for era in ERAS:
        for k in list(out[era]):
            if isinstance(out[era][k], dict):
                out[era][k] = {a: b for a, b in out[era][k].items() if not isinstance(b, np.ndarray)}
    (ROOT / "reports" / "a26_silver.json").write_text(json.dumps(out, indent=1) + "\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--build", action="store_true"); ap.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    if a.build:
        build()
    if a.run:
        run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
