"""A21 - candidate 4th and 5th accounts for the two unused Tradeify funded slots (decisions.md 137): the zero-edge staking plan
(A01 policy, stops >= $500 as in the live plan) on markets with free 1-minute data. A COMPUTATION; zero edge; no trial.

    python -m futuresres.reporting.a21_more_accounts --build MARKET     (one market per process: builds the paths)
    python -m futuresres.reporting.a21_more_accounts --grid MARKET      (sizes, both histories, replay + block)
    python -m futuresres.reporting.a21_more_accounts --corr              (daily-result correlations with MNQ, MGC, MCL)

Windows fixed before any result, from each market's main session (local time): DAX (FDXM, EUR 5 a point) Xetra 09:00-17:30
Frankfurt; Nikkei (NKD, $5 a point) 09:00-15:00 Tokyo; EUR, GBP, AUD, JPY (6E, 6B, 6A, 6J) 08:00-16:00 London; silver (SI,
5,000 oz) COMEX 08:25-13:25 New York. None touches the 17:00-18:00 ET CME break. Paths: free HistData 1-minute bars (bid
quotes; EST without DST), relative to the window's first minute, drift removed within each era (2010-20, 2021-26), in dollars
at TODAY's contract value; entry long (6J long the yen). Assumed: at most 3 full-size contracts per account; commissions per
contract round trip FDXM $4.0, NKD $4.0, FX $4.5, SI $4.5 (estimates).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import sys
import warnings
import zipfile
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
FX_DIR = ROOT / "data" / "fx_histdata"
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "reports" / "a21_more_accounts.json"
ERAS = {"pre": (dt.date(2010, 1, 1), dt.date(2020, 12, 31)), "post": (dt.date(2021, 1, 1), dt.date(2026, 9, 30))}
#: market -> (HistData symbol, tz, start, end, contract, $ per 1.0 of relative return per contract computed at today's price,
#:            round trip per contract, max contracts)
MARKETS = {
    "DAX": ("grxeur", "Europe/Berlin", (9, 0), (17, 30), "FDXM", None, 4.0, 3),
    "NKD": ("jpxjpy", "Asia/Tokyo", (9, 0), (15, 0), "NKD", None, 4.0, 3),
    "6E": ("eurusd", "Europe/London", (8, 0), (16, 0), "6E", None, 4.5, 3),
    "6B": ("gbpusd", "Europe/London", (8, 0), (16, 0), "6B", None, 4.5, 3),
    "6A": ("audusd", "Europe/London", (8, 0), (16, 0), "6A", None, 4.5, 3),
    "6J": ("usdjpy", "Europe/London", (8, 0), (16, 0), "6J", None, 4.5, 3),
    "SI": ("xagusd", "America/New_York", (8, 25), (13, 25), "SI", None, 4.5, 3),
}


def _last_price(sym: str) -> float:
    f = sorted(FX_DIR.glob(f"{sym}_2026*.zip"))[-1]
    z = zipfile.ZipFile(f); n = [x for x in z.namelist() if x.lower().endswith(".csv")][0]
    return float(pl.read_csv(z.read(n), separator=";", has_header=False, columns=[4])[-1, 0])


def notional(market: str) -> float:
    """Today's USD value of one contract (per 1.0 of the underlying's relative return)."""
    eurusd = _last_price("eurusd")
    if market == "DAX":
        return 5.0 * _last_price("grxeur") * eurusd
    if market == "NKD":
        return 5.0 * _last_price("jpxjpy")
    if market == "6E":
        return 125_000 * eurusd
    if market == "6B":
        return 62_500 * _last_price("gbpusd")
    if market == "6A":
        return 100_000 * _last_price("audusd")
    if market == "6J":
        return 12_500_000 / _last_price("usdjpy")
    if market == "SI":
        return 5_000 * _last_price("xagusd")
    raise KeyError(market)


def build(market: str) -> None:
    """Per-era 1-minute window paths (relative returns), one HistData file at a time; cached as npz."""
    sym, tzname, (sh, sm), (eh, em), *_ = MARKETS[market]
    tz = ZoneInfo(tzname)
    T = (eh * 60 + em) - (sh * 60 + sm)
    sessions: dict = {}
    for f in sorted(FX_DIR.glob(f"{sym}_*.zip")):
        z = zipfile.ZipFile(f); n = [x for x in z.namelist() if x.lower().endswith(".csv")][0]
        d = pl.read_csv(z.read(n), separator=";", has_header=False, new_columns=["ts", "o", "h", "l", "c"], columns=[0, 1, 2, 3, 4])
        d = d.with_columns(pl.col("ts").str.strptime(pl.Datetime, "%Y%m%d %H%M%S").dt.replace_time_zone("Etc/GMT+5")
                           .dt.convert_time_zone(tzname).alias("t")).drop("ts")
        d = d.with_columns(pl.col("t").dt.date().alias("date"),
                           (pl.col("t").dt.hour().cast(pl.Int32) * 60 + pl.col("t").dt.minute().cast(pl.Int32) - (sh * 60 + sm)).alias("m"))
        d = d.filter((pl.col("m") >= 0) & (pl.col("m") < T) & (pl.col("t").dt.weekday() <= 5))
        for (date,), g in d.group_by(["date"], maintain_order=True):
            sessions[date] = g.select("m", "o", "h", "l", "c")
        del d
    sign = -1.0 if market == "6J" else 1.0
    for era, (lo, hi) in ERAS.items():
        D, H, L, C = [], [], [], []
        for date in sorted(sessions):
            if not (lo <= date <= hi):
                continue
            g = sessions[date].sort("m")
            m = g["m"].to_numpy()
            if len(m) < 0.8 * T or m[0] > 5:
                continue
            p0 = float(g["o"][0])
            c = np.full(T, np.nan); h = c.copy(); l = c.copy()
            c[m] = g["c"].to_numpy(); h[m] = g["h"].to_numpy(); l[m] = g["l"].to_numpy()
            idx = np.where(np.isnan(c), 0, np.arange(T)); np.maximum.accumulate(idx, out=idx)
            c = np.where(np.isnan(c[0]), p0, c[0]) if False else c
            c[0] = c[0] if not np.isnan(c[0]) else p0
            c = c[idx]; h = np.where(np.isnan(h), c, h); l = np.where(np.isnan(l), c, l)
            rc, rh, rl = c / p0 - 1, h / p0 - 1, l / p0 - 1
            if sign < 0:                                   # long the yen = short USD/JPY
                rc, rh, rl = -rc, -rl, -rh
            D.append(date); C.append(rc); H.append(rh); L.append(rl)
        H, L, C = (np.array(x, np.float64) for x in (H, L, C))
        mu = C[:, -1].mean()
        ramp = np.arange(1, T + 1) / T
        adj = -mu * ramp                                   # drift removed within the era (y01.window_paths)
        np.savez(CACHE / f"a21_{market}_{era}.npz", d=np.array(D, dtype="datetime64[D]"),
                 h=(H + adj).astype(np.float32), l=(L + adj).astype(np.float32), c=(C + adj).astype(np.float32))
        print(market, era, len(D), "sessions; daily window SD", f"{C[:, -1].std() * 1e4:.1f} bps", flush=True)


def paths(market: str, era: str):
    z = np.load(CACHE / f"a21_{market}_{era}.npz")
    usd = np.float32(notional(market))
    return z["h"] * usd, z["l"] * usd, z["c"] * usd, z["d"]


def _policy():
    import futuresres.reporting.a01_game as g
    import futuresres.reporting.a06_playbook as pb
    g.L_SET = pb.PLAN_L_SET
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)


def grid(market: str) -> dict:
    import futuresres.reporting.a02_real as a2
    import futuresres.reporting.a08_gold as a8
    warnings.filterwarnings("ignore")
    _policy(); a2.STOP_FILL = "level"
    rt, cap = MARKETS[market][6], MARKETS[market][7]
    out = {"notional_one_contract": notional(market)}
    for era in ERAS:
        h, l, c, d = paths(market, era)
        sd1 = float(c[:, -1].std())
        out[era] = {"sessions": int(len(c)), "one_contract_daily_sd": sd1, "sizes": {}}
        for n in range(1, cap + 1):
            tot = np.float32(n * rt)
            a2._PATHS["p"] = ((h * n - (tot - a8.RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32))
            rp = a2.sequential(1, "replay"); bl = [a2.sequential(1, "block", traders=4000, seed=s) for s in (11, 12)]
            out[era]["sizes"][n] = {"swing": n * sd1, "replay": [rp["p_any_payout"], rp["mean_net"], rp["p_net_positive"]],
                                    "block": [float(np.mean([b[k] for b in bl])) for k in ("p_any_payout", "mean_net", "p_net_positive")]}
            r, b = out[era]["sizes"][n]["replay"], out[era]["sizes"][n]["block"]
            print(f"{market} {era} {n} contracts (swing ${n*sd1:,.0f}): replay {r[0]:.0%} {r[1]:+,.0f} | block {b[0]:.0%} {b[1]:+,.0f} P(net>0) {b[2]:.0%}", flush=True)
        a2._PATHS.clear()
    sd_post = out["post"]["one_contract_daily_sd"]
    out["risk_matched_n"] = int(min(range(1, cap + 1), key=lambda n: abs(n * sd_post - 2900.0)))
    return out


def corr() -> dict:
    """Correlation of daily window results (relative returns, drift removed) between candidates and the three live
    accounts (MNQ 09:30-16:00, MGC 03:00-11:30 - A08 caches; MCL session - daily bars), paired by calendar date."""
    import futuresres.reporting.a08_gold as a8
    import futuresres.reporting.a15_crude as c15
    out = {}
    for era in ERAS:
        series = {}
        for prod, win in (("MNQ", "rth_0930_1600"), ("MGC", "london_0300_1130")):
            h, l, c, d = a8.era_paths(era, prod, win)
            series[prod] = dict(zip(np.asarray(d).astype("datetime64[D]").tolist(), c[:, -1].tolist()))
        h, l, c, d = c15.mcl_paths(era if era == "post" else "pre")
        series["MCL"] = dict(zip(d.astype("datetime64[D]").tolist(), c[:, 0].tolist()))
        for m in MARKETS:
            z = np.load(CACHE / f"a21_{m}_{era}.npz")
            series[m] = dict(zip(z["d"].astype("datetime64[D]").tolist(), z["c"][:, -1].tolist()))
        names = list(series)
        mat = {}
        for a_ in names:
            for b_ in names:
                common = sorted(set(series[a_]) & set(series[b_]))
                if len(common) > 100:
                    mat[f"{a_}|{b_}"] = float(np.corrcoef([series[a_][k] for k in common], [series[b_][k] for k in common])[0, 1])
        out[era] = mat
        print(era, "         " + " ".join(f"{n:>6}" for n in names))
        for a_ in names:
            print(era, f"{a_:>6}  " + " ".join(f"{mat.get(f'{a_}|{b_}', float('nan')):+6.2f}" for b_ in names))
    return out


def per_start(market: str, era: str, n: int) -> dict:
    """Back-to-back replay of one candidate account (n contracts), per start date (a12_joint.per_start's format)."""
    import futuresres.reporting.a02_real as a2
    import futuresres.reporting.a08_gold as a8
    h, l, c, d = paths(market, era)
    tot = np.float32(n * MARKETS[market][6])
    a2._PATHS["p"] = ((h * n - (tot - a8.RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32))
    r = a2.sequential(1, "replay", per_trader=True); a2._PATHS.clear(); e = r["each"]
    return {"date": d[e["start"]].astype("datetime64[D]"), "net": e["net"], "first": e["first_payout_day"], "fees": e["fees"], "paid": e["paid"]}


def portfolio() -> dict:
    """The three live accounts alone vs with NKD (1) and DAX (2 FDXM) added: joint replay on common start dates."""
    import futuresres.reporting.a02_real as a2
    import futuresres.reporting.a12_joint as j
    import futuresres.reporting.a15_crude as c15
    warnings.filterwarnings("ignore")
    _policy(); a2.STOP_FILL = "level"
    out = {}
    for era in ERAS:
        h, l, c, d = c15.mcl_paths(era); orig = a2._bracket_day
        a2._PATHS["p"], o = c15._engine(h, l, c, 10); a2._bracket_day = c15.one_bar_rule(o)
        rc = a2.sequential(1, "replay", per_trader=True); a2._bracket_day = orig; a2._PATHS.clear(); e = rc["each"]
        acc = {"MNQ": j.per_start(era, "MNQ"), "MGC": j.per_start(era, "MGC"),
               "MCL": {"date": d[e["start"]], "net": e["net"], "first": e["first_payout_day"], "fees": e["fees"], "paid": e["paid"]},
               "NKD": per_start("NKD", era, 1), "DAX": per_start("DAX", era, 2)}
        common = None
        for v in acc.values():
            common = set(v["date"].tolist()) if common is None else common & set(v["date"].tolist())
        common = np.array(sorted(common), dtype="datetime64[D]")
        sel = {k: {f: v[f][np.searchsorted(v["date"], common)] for f in ("net", "first", "fees", "paid")} for k, v in acc.items()}
        out[era] = {"common_starts": int(len(common)), "first": str(common[0]), "last": str(common[-1])}
        for label, keys in (("3 accounts (MNQ, MGC, MCL)", ("MNQ", "MGC", "MCL")), ("4 (+ NKD)", ("MNQ", "MGC", "MCL", "NKD")),
                            ("5 (+ NKD, DAX)", ("MNQ", "MGC", "MCL", "NKD", "DAX"))):
            net = sum(sel[k]["net"] for k in keys); fees = sum(sel[k]["fees"] for k in keys)
            pays = sum((sel[k]["first"] > 0).astype(int) for k in keys)
            out[era][label] = {"p_any_payout": float((pays > 0).mean()), "streams_paying": float(pays.mean()),
                               "mean_net": float(net.mean()), "median_net": float(np.median(net)), "p_net_positive": float((net > 0).mean()),
                               "net_p10": float(np.quantile(net, 0.1)), "worst": float(net.min()), "mean_fees": float(fees.mean())}
            r = out[era][label]
            print(f"{era} {label:28}: P(any payout) {r['p_any_payout']:.1%} paying {r['streams_paying']:.2f} | mean {r['mean_net']:+,.0f} median "
                  f"{r['median_net']:+,.0f} | P(net>0) {r['p_net_positive']:.0%} | p10 {r['net_p10']:+,.0f} worst {r['worst']:+,.0f} | fees {r['mean_fees']:,.0f}", flush=True)
    return out


def _out(market: str) -> Path:
    return ROOT / "reports" / f"a21_{market}.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build"); ap.add_argument("--grid"); ap.add_argument("--corr", action="store_true"); ap.add_argument("--portfolio", action="store_true")
    a = ap.parse_args(argv)
    if a.build:
        build(a.build); return 0
    if a.grid:
        _out(a.grid).write_text(json.dumps(grid(a.grid), indent=1) + "\n"); return 0
    if a.portfolio:
        (ROOT / "reports" / "a21_portfolio.json").write_text(json.dumps(portfolio(), indent=1) + "\n"); return 0
    if a.corr:
        (ROOT / "reports" / "a21_corr.json").write_text(json.dumps(corr(), indent=1) + "\n"); return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
