"""D-series family 3 - the session relay (decisions.md 149): does a window that has FINISHED predict the direction of a later
window of the plan? A SCAN on 2010-06 -> 2017-12; carried tests are registered and validated once on sealed 2018-01 -> 2026-08.

    python -m futuresres.reporting.d3_relay --build        (window and pre-window returns for every date; cached)
    python -m futuresres.reporting.d3_relay --scan         (discovery: 80 tests, 2010-17 ONLY)

Prices are the close of the last 1-minute bar in the 15 minutes before each time. MNQ (NQ/MNQ spliced) and MGC from owned
Databento trades (a move whose two prices come from different contracts is dropped); NKD and DAX from free HistData CFD bars on
the corrected clock (New York time with DST, decisions.md 140), window opens and closes only; MCL from the owned daily bars
(roll-correct; crossover days dropped); ZS from Yahoo daily bars (open -> settlement). All returns in bps.
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
CACHE = ROOT / "data" / "cache"
TABLE = CACHE / "d3_relay_table.parquet"
OUT = ROOT / "reports" / "d3_discovery.json"
DISC = (dt.date(2010, 6, 1), dt.date(2017, 12, 31))
VAL = (dt.date(2018, 1, 1), dt.date(2026, 8, 31))
FX_DIR = ROOT / "data" / "fx_histdata"


# ------------------------------------------------------------------ prices
def _last_before(df: pl.DataFrame, tcol: str, tz: str, hh: int, mm: int, name: str, with_contract: bool) -> pl.DataFrame:
    """Per local date: the close (and contract) of the last bar starting in [T-15 min, T)."""
    T = hh * 60 + mm
    d = df.with_columns(pl.col(tcol).dt.convert_time_zone(tz).alias("lt"))
    d = d.with_columns(pl.col("lt").dt.date().alias("date"),
                       (pl.col("lt").dt.hour().cast(pl.Int32) * 60 + pl.col("lt").dt.minute().cast(pl.Int32)).alias("m"))
    d = d.filter((pl.col("m") >= T - 15) & (pl.col("m") < T)).sort(tcol)
    cols = [pl.col("close").last().alias(name)] + ([pl.col("contract").last().alias(name + "_ct")] if with_contract else [])
    return d.group_by("date").agg(cols)


def databento(path: Path, times: dict) -> pl.DataFrame:
    """times: name -> (hh, mm) New York. One frame keyed by New York date."""
    d = pl.read_parquet(path, columns=["ts_event", "close", "contract"])
    out = None
    for name, (hh, mm) in times.items():
        x = _last_before(d, "ts_event", "America/New_York", hh, mm, name, True)
        out = x if out is None else out.join(x, on="date", how="full", coalesce=True)
    del d
    return out.sort("date")


def histdata(sym: str, specs: dict) -> pl.DataFrame:
    """specs: name -> (tz, hh, mm); one zip at a time; keyed by each spec's LOCAL date."""
    parts = {k: [] for k in specs}
    for f in sorted(FX_DIR.glob(f"{sym}_*.zip")):
        z = zipfile.ZipFile(f); n = [x for x in z.namelist() if x.lower().endswith(".csv")][0]
        d = pl.read_csv(z.read(n), separator=";", has_header=False, new_columns=["ts", "close"], columns=[0, 4])
        d = d.with_columns(pl.col("ts").str.strptime(pl.Datetime, "%Y%m%d %H%M%S")
                           .dt.replace_time_zone("America/New_York", ambiguous="earliest", non_existent="null").alias("t")).drop("ts")
        d = d.drop_nulls("t")
        for name, (tz, hh, mm) in specs.items():
            parts[name].append(_last_before(d, "t", tz, hh, mm, name, False))
        del d
    out = None
    for name, ps in parts.items():
        x = pl.concat(ps).group_by("date").agg(pl.col(name).last())
        out = x if out is None else out.join(x, on="date", how="full", coalesce=True)
    return out.sort("date")


def _ser(dates, vals) -> dict:
    return {d: float(v) for d, v in zip(dates, vals) if v is not None and np.isfinite(v)}


def build() -> None:
    S = {}
    # MNQ / NQ (Databento trades)
    q = databento(ROOT / "data" / "continuous" / "NQ_MNQ_spliced.parquet", {"o0930": (9, 30), "c1600": (16, 0)})
    dd = q["date"].to_list(); o, c = q["o0930"].to_numpy(), q["c1600"].to_numpy(); oc, cc = q["o0930_ct"].to_list(), q["c1600_ct"].to_list()
    S["MNQ_win"] = _ser(dd, [(c[i] / o[i] - 1) * 1e4 if oc[i] == cc[i] and o[i] and c[i] else None for i in range(len(dd))])
    S["MNQ_on"] = _ser(dd, [(o[i] / c[i - 1] - 1) * 1e4 if i and oc[i] == cc[i - 1] and o[i] and c[i - 1] else None for i in range(len(dd))])
    # MGC (Databento trades)
    g = databento(ROOT / "data" / "continuous" / "MGC.parquet", {"o0300": (3, 0), "m0930": (9, 30), "c1130": (11, 30)})
    dd = g["date"].to_list(); o, m_, c = (g[k].to_numpy() for k in ("o0300", "m0930", "c1130"))
    oc, mc, cc = (g[k + "_ct"].to_list() for k in ("o0300", "m0930", "c1130"))
    S["MGC_win"] = _ser(dd, [(c[i] / o[i] - 1) * 1e4 if oc[i] == cc[i] and o[i] and c[i] else None for i in range(len(dd))])
    S["MGC_morn"] = _ser(dd, [(m_[i] / o[i] - 1) * 1e4 if oc[i] == mc[i] and o[i] and m_[i] else None for i in range(len(dd))])
    S["MGC_pre"] = _ser(dd, [(o[i] / c[i - 1] - 1) * 1e4 if i and oc[i] == cc[i - 1] and o[i] and c[i - 1] else None for i in range(len(dd))])
    del q, g
    # NKD (HistData jpxjpy, Tokyo clock)
    n = histdata("jpxjpy", {"o": ("Asia/Tokyo", 9, 0), "c": ("Asia/Tokyo", 15, 0)})
    n = n.filter(pl.col("date").dt.weekday() <= 5)
    dd = n["date"].to_list(); o, c = n["o"].to_numpy(), n["c"].to_numpy()
    S["NKD_win"] = _ser(dd, [(c[i] / o[i] - 1) * 1e4 if o[i] and c[i] else None for i in range(len(dd))])
    S["NKD_pre"] = _ser(dd, [(o[i] / c[i - 1] - 1) * 1e4 if i and o[i] and c[i - 1] else None for i in range(len(dd))])
    # DAX (HistData grxeur, Frankfurt clock; the morning so far at 09:30 New York)
    x = histdata("grxeur", {"o": ("Europe/Berlin", 9, 0), "c": ("Europe/Berlin", 17, 30), "m": ("America/New_York", 9, 30)})
    x = x.filter(pl.col("date").dt.weekday() <= 5)
    dd = x["date"].to_list(); o, c, m_ = x["o"].to_numpy(), x["c"].to_numpy(), x["m"].to_numpy()
    S["DAX_win"] = _ser(dd, [(c[i] / o[i] - 1) * 1e4 if o[i] and c[i] else None for i in range(len(dd))])
    S["DAX_pre"] = _ser(dd, [(o[i] / c[i - 1] - 1) * 1e4 if i and o[i] and c[i - 1] else None for i in range(len(dd))])
    S["DAX_morn"] = _ser(dd, [(m_[i] / o[i] - 1) * 1e4 if o[i] and m_[i] else None for i in range(len(dd))])
    # MCL (owned daily bars, roll-correct)
    from futuresres.data.daily_bars import load_market
    mk = load_market("CL")
    keep = ~mk.crossover & (mk.ret != 0)
    S["MCL"] = _ser([d.astype(object) for d in mk.dates[keep].astype("datetime64[D]")], mk.ret[keep] * 1e4)
    # ZS (Yahoo daily, open -> settlement)
    import futuresres.reporting.a22_more_markets as a22
    z = a22.load("ZS=F", "1d").with_columns(pl.col("ts").dt.date().alias("date"))
    r = ((z["c"] / z["o"] - 1) * 1e4).to_numpy()
    S["ZS"] = _ser(z["date"].to_list(), [v if abs(v) < 2500 else None for v in r])
    rows = [{"series": k, "date": d, "bps": v} for k, s in S.items() for d, v in s.items()]
    pl.DataFrame(rows).write_parquet(TABLE)
    for k, s in S.items():
        v = np.array(list(s.values())); ds = sorted(s)
        print(f"{k:9} {len(s):5} days {ds[0]} -> {ds[-1]}  mean {v.mean():+6.2f} bps  sd {v.std():6.1f}", flush=True)


# ------------------------------------------------------------------ tests
def series() -> dict:
    """Every series, bad prints removed: values more than 15 robust SDs (1.4826 x MAD) from the median are dropped - fixed
    before the scan (decisions.md 149 addendum); it removes the DAX CFD's +27,100 / -7,423 bps overnight prints."""
    t = pl.read_parquet(TABLE); out = {}
    for (k,), g in t.group_by(["series"]):
        v = g["bps"].to_numpy(); med = np.median(v); rsd = 1.4826 * np.median(np.abs(v - med))
        ok = np.abs(v - med) <= 15 * rsd
        out[k] = dict(zip(np.array(g["date"].to_list(), dtype=object)[ok].tolist(), v[ok].tolist()))
    return out


def prev_weekday(d: dt.date) -> dt.date:
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


#: (target, predictor, which date of the predictor: "same" = the target's date, "prev" = the previous weekday)
TESTS = [("NKD_win", p, "prev") for p in ("MNQ_win", "DAX_win", "MGC_win", "MCL", "ZS", "NKD_win")] + [("NKD_win", "NKD_pre", "same")] \
    + [("ZS", p, "prev") for p in ("MNQ_win", "DAX_win", "MGC_win", "MCL", "NKD_win", "ZS")] \
    + [("MCL", p, "prev") for p in ("MNQ_win", "DAX_win", "MGC_win", "ZS", "NKD_win", "MCL")] \
    + [("DAX_win", "NKD_win", "same")] + [("DAX_win", p, "prev") for p in ("MNQ_win", "MGC_win", "MCL", "ZS", "DAX_win")] + [("DAX_win", "DAX_pre", "same")] \
    + [("MGC_win", "NKD_win", "same")] + [("MGC_win", p, "prev") for p in ("MNQ_win", "DAX_win", "MCL", "ZS", "MGC_win")] + [("MGC_win", "MGC_pre", "same")] \
    + [("MNQ_win", p, "same") for p in ("NKD_win", "DAX_morn", "MGC_morn")] + [("MNQ_win", p, "prev") for p in ("MCL", "ZS", "MNQ_win")] + [("MNQ_win", "MNQ_on", "same")]
assert len(TESTS) == 40


def pairs(S: dict, target: str, pred: str, when: str, lo: dt.date, hi: dt.date):
    """(dates, target bps, predictor bps) on dates in [lo, hi] where both exist."""
    D, Y, X = [], [], []
    for d, y in S[target].items():
        if not (lo <= d <= hi):
            continue
        pd_ = d if when == "same" else prev_weekday(d)
        x = S[pred].get(pd_)
        if x is None:
            continue
        D.append(d); Y.append(y); X.append(x)
    o = np.argsort(D)
    return np.array(D)[o], np.array(Y)[o], np.array(X)[o]


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def scan() -> dict:
    S = series(); res = []
    for target, pred, when in TESTS:
        D, Y, X = pairs(S, target, pred, when, *DISC)
        assert len(D) == 0 or D.max() <= DISC[1], "discovery read sealed data"
        ydm = Y - Y.mean()                                   # the target demeaned within the period: skill beyond drift
        med = float(np.median(np.abs(X)))
        for form in ("all", "strong"):
            m = np.ones(len(X), bool) if form == "all" else np.abs(X) > med
            z = np.sign(X[m]) * ydm[m]
            res.append({"target": target, "predictor": pred, "when": when, "form": form, "median_abs_pred": med,
                        "n": int(m.sum()), "mean_bps": float(z.mean()), "sd_bps": float(z.std(ddof=1)), "t": _t(z),
                        "rule": "follow" if z.mean() > 0 else "fade"})
    res.sort(key=lambda r: -abs(r["t"]))
    carried = [r for r in res if abs(r["t"]) > 1.96]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_passes_5pct": round(0.05 * len(res), 1),
           "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(res)} tests on {DISC[0]} -> {DISC[1]}; ~{0.05 * len(res):.0f} pass |t| > 1.96 by chance; carried {len(carried)}", flush=True)
    for r in res[:20]:
        print(f"  {r['target']:8} <- {r['predictor']:9} ({r['when']:4}, {r['form']:6}) n {r['n']:5}  {r['rule']:6} mean {r['mean_bps']:+6.2f} bps "
              f"sd {r['sd_bps']:6.1f}  t {r['t']:+5.2f}{'  CARRIED' if abs(r['t']) > 1.96 else ''}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--build", action="store_true"); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.build:
        build()
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
