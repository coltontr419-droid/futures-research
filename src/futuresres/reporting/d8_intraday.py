"""D-series family 8 - short-horizon reactions to large intraday moves (decisions.md 166): after a k-minute move beyond 2 sigma,
does the market continue or reverse over the next h minutes, net of costs? MNQ and MGC, owned Databento 1-minute trades.

    python -m futuresres.reporting.d8_intraday --build MARKET SESSION     (a days x minutes grid per session; cached)
    python -m futuresres.reporting.d8_intraday --scan                     (discovery: 72 tests, 2013-2017 ONLY)
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
OUT = ROOT / "reports" / "d8_discovery.json"
DISC = (dt.date(2013, 1, 1), dt.date(2017, 12, 31))
VAL = (dt.date(2018, 1, 1), dt.date(2026, 8, 31))
FILES = {"MNQ": "NQ_MNQ_spliced.parquet", "MGC": "MGC.parquet"}
#: (market, session) -> (start minute, end minute) New York; start > end wraps (the session is dated by its END day)
SESSIONS = {("MNQ", "day"): (570, 960), ("MNQ", "night"): (1080, 570), ("MGC", "london"): (180, 690), ("MGC", "asia"): (1080, 180)}
#: grids built for later families, outside family 8's scan (decisions.md 293): MNQ after the cash close, 16:00 -> 16:55
EXTRA_SESSIONS = {("MNQ", "post"): (960, 1015)}
COST = {"MNQ": 1.41, "MGC": 0.432}            # points per round trip: commission + one tick
KS, HS = (5, 15, 30), (5, 15, 30)
FFILL = 5                                      # a missing minute takes the last close only within 5 minutes


def _grid_path(market, session):
    return CACHE / f"d8_{market}_{session}.npz"


def build(market: str, session: str) -> None:
    a, b = {**SESSIONS, **EXTRA_SESSIONS}[(market, session)]
    T = (b - a) % 1440
    lf = (pl.scan_parquet(ROOT / "data" / "continuous" / FILES[market])
          .select("ts_event", pl.col("close").cast(pl.Float32), pl.col("volume").cast(pl.Int32), "contract")
          .with_columns(pl.col("ts_event").dt.convert_time_zone("America/New_York").alias("t"))
          .with_columns(pl.col("t").dt.date().alias("date"),
                        (pl.col("t").dt.hour().cast(pl.Int32) * 60 + pl.col("t").dt.minute().cast(pl.Int32)).alias("m"))
          .with_columns(((pl.col("m") - a) % 1440).alias("off"))
          .filter(pl.col("off") < T))
    if a > b:                                  # the evening part belongs to the next weekday's session
        nd = pl.col("date") + pl.duration(days=1)
        nd = pl.when(nd.dt.weekday() == 6).then(nd + pl.duration(days=2)).when(nd.dt.weekday() == 7).then(nd + pl.duration(days=1)).otherwise(nd)
        lf = lf.with_columns(pl.when(pl.col("m") >= a).then(nd).otherwise(pl.col("date")).alias("D"))
    else:
        lf = lf.with_columns(pl.col("date").alias("D"))
    # contract id = year * 12 + month index, from the symbol ("NQH2011" -> 2011 * 12 + 2): the same in every grid (decisions.md 169)
    month = pl.col("contract").str.slice(-5, 1).replace_strict({c: i for i, c in enumerate("FGHJKMNQUVXZ")}, return_dtype=pl.Int32)
    ct = pl.col("contract").str.slice(-4, 4).cast(pl.Int32) * 12 + month
    d = lf.filter(pl.col("D").dt.weekday() <= 5).select("D", "off", "close", "volume", ct.alias("ct")).collect()
    days = np.array(sorted(set(d["D"].to_list())))
    di = {x: i for i, x in enumerate(days)}
    C = np.full((len(days), T), np.nan, np.float32); V = np.zeros((len(days), T), np.float32); K = np.full((len(days), T), -1, np.int32)
    r = np.array([di[x] for x in d["D"].to_list()]); o = d["off"].to_numpy()
    C[r, o] = d["close"].to_numpy(); V[r, o] = d["volume"].to_numpy(); K[r, o] = d["ct"].to_numpy()
    del d
    for j in range(1, T):                      # forward fill within FFILL minutes
        miss = np.isnan(C[:, j])
        for g in range(1, FFILL + 1):
            if j - g < 0:
                break
            src = miss & ~np.isnan(C[:, j - g])
            C[src, j] = C[src, j - g]; K[src, j] = K[src, j - g]; miss &= ~src
    np.savez(_grid_path(market, session), days=days.astype("datetime64[D]"), C=C, V=V, K=K)
    print(market, session, len(days), "days x", T, "minutes;", f"{np.isfinite(C).mean():.0%} filled", flush=True)


def load(market: str, session: str):
    z = np.load(_grid_path(market, session))
    return z["days"].astype("datetime64[D]").astype(object), z["C"], z["V"], z["K"]


def kret(C, K, k):
    """k-minute price change (points) ending at each minute; NaN unless both ends exist and are one contract."""
    R = np.full(C.shape, np.nan, np.float32)
    R[:, k:] = C[:, k:] - C[:, :-k]
    R[:, k:][K[:, k:] != K[:, :-k]] = np.nan
    return R


def kvol(V, k):
    cs = np.cumsum(V, axis=1, dtype=np.float64); out = np.full(V.shape, np.nan)
    out[:, k:] = cs[:, k:] - cs[:, :-k]
    return out


def events(market: str, session: str, k: int, h: int, volcond: str, lo: dt.date, hi: dt.date, direction: int = 1,
           C=None, V=None, K=None, days=None):
    """Non-overlapping trades: (day, entry minute, net points). direction +1 follow / -1 fade."""
    if C is None:
        days, C, V, K = load(market, session)
    R = kret(C, K, k); Q = kvol(V, k)
    n, T = C.shape
    sig = np.full(n, np.nan); vbar = np.full(n, np.nan)
    rs = np.nanstd(R, axis=1); vm = np.nanmean(Q, axis=1)
    for i in range(20, n):                     # the previous 20 sessions
        sig[i] = np.sqrt(np.nanmean(rs[i - 20:i] ** 2)); vbar[i] = np.nanmean(vm[i - 20:i])
    out = []
    for i in range(n):
        if not (lo <= days[i] <= hi) or not np.isfinite(sig[i]):
            continue
        r = R[i]; big = np.abs(np.nan_to_num(r)) > 2 * sig[i]
        rel = Q[i] / vbar[i]
        vc = (rel > 1) if volcond == "high" else (rel <= 1)
        cand = np.where(big & vc)[0]
        last_exit = -1
        for t in cand:
            if t < last_exit:
                continue
            ex = min(t + h, T - 1)
            if ex <= t or not (np.isfinite(C[i, ex]) and K[i, ex] == K[i, t]):
                continue
            gross = direction * np.sign(r[t]) * (C[i, ex] - C[i, t])
            out.append((days[i], int(t), float(gross - COST[market])))
            last_exit = ex
    return out


def stats(tr: list) -> dict:
    if len(tr) < 30:
        return {"trades": len(tr), "net": float("nan"), "t": float("nan")}
    x = np.array([v for _, _, v in tr]); d = {}
    for day, _, v in tr:
        d[day] = d.get(day, 0.0) + v
    ds = np.array(list(d.values()))
    t = float(ds.mean() / (ds.std(ddof=1) / math.sqrt(len(ds)))) if len(ds) > 2 else float("nan")
    return {"trades": len(tr), "days_traded": len(ds), "per_day": len(tr) / len(ds), "net": float(x.mean()), "t_day_clustered": t,
            "net_per_day": float(ds.mean())}


def scan() -> dict:
    res = []
    for (m, sess) in SESSIONS:
        days, C, V, K = load(m, sess)
        for k in KS:
            for vc in ("high", "low"):
                for h in HS:
                    fol = events(m, sess, k, h, vc, *DISC, 1, C, V, K, days)
                    assert all(d <= DISC[1] for d, _, _ in fol), "discovery read sealed data"
                    gross_follow = np.mean([v for _, _, v in fol]) + COST[m] if fol else 0.0
                    direction = 1 if gross_follow > 0 else -1
                    tr = fol if direction == 1 else events(m, sess, k, h, vc, *DISC, -1, C, V, K, days)
                    st = stats(tr)
                    res.append({"market": m, "session": sess, "k": k, "volume": vc, "h": h, "rule": "follow" if direction == 1 else "fade",
                                "gross_follow_pts": float(gross_follow), **st})
                    print(f"  {m} {sess:6} k {k:2} vol {vc:4} h {h:2} {res[-1]['rule']:6} trades {st['trades']:6} "
                          f"net {st['net']:+6.2f} pts t {st.get('t_day_clustered', float('nan')):+5.2f}", flush=True)
        del C, V, K
    for r in res:
        r["carried"] = bool(abs(r.get("t_day_clustered", 0) or 0) > 1.96 and r["net"] > 0)
    res.sort(key=lambda r: -(r.get("t_day_clustered") or -99))
    carried = [r for r in res if r["carried"]]
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(res), "expected_chance_passes_5pct": round(0.05 * len(res), 1),
           "carried": carried, "all": res}
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"{len(res)} tests; carried {len(carried)} (|t| > 1.96 and net > 0 after costs)", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--build", nargs=2); ap.add_argument("--scan", action="store_true")
    a = ap.parse_args(argv)
    if a.build:
        build(*a.build)
    if a.scan:
        scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
