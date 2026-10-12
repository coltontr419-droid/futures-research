"""A22 - (1) the NKD and DAX accounts re-checked on real prices; (2) a sixth and seventh market. A COMPUTATION; zero
edge (drift removed); no trial. decisions.md 140.

    python -m futuresres.reporting.a22_more_markets --fetch            (Yahoo daily + hourly, cached in data/cache)
    python -m futuresres.reporting.a22_more_markets --proxy NKD|DAX    (A21's CFD proxy vs real prices, same dates)
    python -m futuresres.reporting.a22_more_markets --grid MARKET      (one candidate: sizes, both histories)
    python -m futuresres.reporting.a22_more_markets --corr | --portfolio

DATA. Free Yahoo Finance futures bars (continuous front month): daily since 2010, hourly for the last ~730 days. No
Databento API key is on this machine (only FTP delivery credentials), and A21's minute data for NKD and DAX is CFD bid
quotes. Yahoo has the real NKD (CME) but no Eurex futures, so DAX is checked against the official index (^GDAXI).

PATHS. One bar = three points in time order - the extreme nearer the bar's open first (the OHLC path rule, decisions.md
115-116), the other extreme, the close - so the standard bracket engine resolves a bar touching both levels by that rule.
Hourly bars: a session is its hourly bars from the session's first open; sessions with an internal jump > 1.5% between
one bar's close and the next bar's open (a roll inside the session in Yahoo's continuous series) are dropped. Daily
bars: one bar per session, open to close, so a roll never enters a path. Hourly is within ~10-15% of the minute answer,
one bar a day within ~30% (decisions.md 115-116): a go/no-go tool. Drift removed within each history, dollars at today's
contract value. The hourly history (~2024-05 -> 2026-10) is the main test for every candidate; a long history (2010-20,
2021-26) is added where Yahoo's daily bar matched the hourly-built session (DAILY_OK) - copper from the owned Databento file.

CANDIDATES, windows fixed before any result - each market's whole session (the bar Yahoo dates by trade date), entry at
the session's open: natural gas (micro MNG, 1,000 mmBtu), platinum (PL, 50 oz), copper (micro MHG, 2,500 lb), corn /
soybeans / wheat (ZC / ZS / ZW, 5,000 bu), live cattle / lean hogs (LE / HE, 40,000 lb), bitcoin (micro MBT, 0.1 BTC).
Tradeify lists CME equity, FX, energy, metals, grains, livestock and Eurex (decisions.md 115); bitcoin is not on that list
and is shown for reference. Caps 3 full-size / 30 micro contracts (the user's reading, decisions.md 138). Round trips
per contract (estimates): full-size $4.50, micro $3.32, MBT $4.50. Size fixed by the rule used for accounts 3-5: daily
swing nearest $2,900 (decisions.md 116, 137).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import sys
import time
import urllib.request
import warnings
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "cache"
ET = ZoneInfo("America/New_York")
ERAS = {"pre": (dt.date(2010, 1, 1), dt.date(2020, 12, 31)), "post": (dt.date(2021, 1, 1), dt.date(2026, 9, 30))}
SWING = 2900.0
#: market -> (Yahoo symbol, contract, $ per 1.0 of quoted price per contract, round trip, max contracts,
#:            hourly session: (first bar hh, previous evening?, last bar hh) in New York time)
CAND = {
    "NG": ("NG=F", "MNG", 1_000.0, 3.32, 30, (18, True, 16)),
    "PL": ("PL=F", "PL", 50.0, 4.50, 3, (18, True, 16)),
    "HG": ("HG=F", "MHG", 2_500.0, 3.32, 30, (18, True, 16)),
    "ZC": ("ZC=F", "ZC", 50.0, 4.50, 3, (20, True, 14)),
    "ZS": ("ZS=F", "ZS", 50.0, 4.50, 3, (20, True, 14)),
    "ZW": ("ZW=F", "ZW", 50.0, 4.50, 3, (20, True, 14)),
    "LE": ("LE=F", "LE", 400.0, 4.50, 3, (9, False, 14)),
    "HE": ("HE=F", "HE", 400.0, 4.50, 3, (9, False, 14)),
    "BTC": ("BTC=F", "MBT", 0.1, 4.50, 30, (18, True, 16)),
}
EXTRA = {"NKD": "NKD=F", "GDAXI": "^GDAXI"}


# ---------------------------------------------------------------- data
def _cache(sym: str, interval: str) -> Path:
    return CACHE / f"yh_{sym.replace('=', '').replace('^', '')}_{interval}.parquet"


def fetch(sym: str, interval: str) -> pl.DataFrame:
    q = ("interval=60m&range=730d" if interval == "1h" else
         f"interval=1d&period1={int(dt.datetime(2009, 12, 1).timestamp())}&period2={int(time.time())}")
    req = urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{q}", headers={"User-Agent": "Mozilla/5.0"})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())["chart"]["result"][0]
    qt = r["indicators"]["quote"][0]
    d = pl.DataFrame({"t": r["timestamp"], "o": qt["open"], "h": qt["high"], "l": qt["low"], "c": qt["close"],
                      "v": qt.get("volume") or [None] * len(r["timestamp"])},
                     schema={"t": pl.Int64, "o": pl.Float64, "h": pl.Float64, "l": pl.Float64, "c": pl.Float64, "v": pl.Float64})
    d = d.drop_nulls(["o", "h", "l", "c"]).filter((pl.col("h") >= pl.col("l")) & (pl.col("o") > 0))
    d.write_parquet(_cache(sym, interval))
    return d


def load(sym: str, interval: str) -> pl.DataFrame:
    d = pl.read_parquet(_cache(sym, interval))
    return d.with_columns(pl.from_epoch("t", "s").dt.replace_time_zone("UTC").dt.convert_time_zone("America/New_York").alias("ts"))


def points(o, h, l, c):
    """(S, B) bars -> (S, 3B) points relative to nothing (same units): nearer extreme, farther extreme, close."""
    hf = (h - o) <= (o - l)
    a = np.where(hf, h, l); b = np.where(hf, l, h)
    return np.stack([a, b, c], axis=2).reshape(o.shape[0], -1)


def _drift(p: np.ndarray) -> np.ndarray:
    T = p.shape[1]
    return p - p[:, -1].mean() * (np.arange(1, T + 1) / T)


def daily_paths(market: str, era: str):
    """One bar per session (Yahoo daily), relative to the session open, drift removed; $ per contract; dates."""
    sym, _, mult, *_ = CAND[market]
    d = load(sym, "1d").with_columns(pl.col("ts").dt.date().alias("date"))
    lo, hi = ERAS[era]
    d = d.filter((pl.col("date") >= lo) & (pl.col("date") <= hi) & (pl.col("ts").dt.weekday() <= 5))
    o, h, l, c = (d[k].to_numpy() for k in "ohlc")
    p = points(np.zeros((len(o), 1)), (h / o - 1)[:, None], (l / o - 1)[:, None], (c / o - 1)[:, None])
    keep = np.abs(p[:, -1]) < 0.25                     # Yahoo bad prints
    usd = notional(market)
    return (_drift(p[keep]) * usd).astype(np.float32), d["date"].to_numpy()[keep]


def notional(market: str) -> float:
    sym, _, mult, *_ = CAND[market]
    return float(load(sym, "1d")["c"][-1]) * mult


def session_bars(d: pl.DataFrame, first_hh: int, prev_evening: bool, last_hh: int, tz=ET) -> dict:
    """Hourly bars -> {session date: (o, h, l, c, v) arrays} for one fixed window (times in `tz`)."""
    d = d.with_columns(pl.col("ts").dt.convert_time_zone(str(tz)).alias("lt"))
    d = d.with_columns(pl.col("lt").dt.hour().alias("hh"), pl.col("lt").dt.date().alias("ld"))
    if prev_evening:
        d = d.with_columns(pl.when(pl.col("hh") >= first_hh).then(pl.col("ld") + pl.duration(days=1)).otherwise(pl.col("ld")).alias("sd"))
        d = d.filter((pl.col("hh") >= first_hh) | (pl.col("hh") <= last_hh))
        nb = (24 - first_hh) + last_hh + 1
    else:
        d = d.with_columns(pl.col("ld").alias("sd")).filter((pl.col("hh") >= first_hh) & (pl.col("hh") <= last_hh))
        nb = last_hh - first_hh + 1
    out = {}
    for (sd,), g in d.sort("t").group_by(["sd"], maintain_order=True):
        if g.height < 0.8 * nb:
            continue
        hh = g["hh"].to_numpy()
        if hh[0] != first_hh:                           # the session must start at its first bar
            continue
        out[sd] = tuple(g[k].to_numpy() for k in ("o", "h", "l", "c", "v"))
    return out


def hourly_rel(bars: dict, max_jump: float = 0.008):
    """Sessions -> (S, 3B) points relative to the first open (bars missing in a session carry the last close), dates.
    Drops sessions where Yahoo's continuous series switches contract inside the session: an open-vs-previous-close
    jump above max_jump, or any one-hour move above max(5%, 15x the market's median one-hour move) - Yahoo interleaves
    two contract months around rolls, sometimes inside one bar. The spike rule also drops a few genuine extreme hours
    (copper 2025-07-30); the counts are reported."""
    B = max(len(v[0]) for v in bars.values())
    hm = np.median(np.concatenate([np.abs(np.diff(np.concatenate([[v[0][0]], v[3]])) / v[3].mean()) for v in bars.values()]))
    spike = max(0.05, 15 * hm)
    rows, dates, dropped = [], [], 0
    for sd in sorted(bars):
        o, h, l, c, _ = bars[sd]
        steps = np.abs(np.concatenate([[c[0] / o[0] - 1], c[1:] / c[:-1] - 1]))
        if (len(o) > 1 and np.max(np.abs(o[1:] / c[:-1] - 1)) > max_jump) or steps.max() > spike:
            dropped += 1; continue
        p0 = o[0]
        r = [x / p0 - 1 for x in (o, h, l, c)]
        if len(o) < B:                                  # pad the end with the last close
            r = [np.concatenate([x, np.repeat(r[3][-1], B - len(o))]) for x in r]
        rows.append(points(*(x[None, :] for x in r))[0]); dates.append(sd)
    return np.array(rows), np.array(dates, dtype="datetime64[D]"), dropped


# ---------------------------------------------------------------- engine
def _policy():
    from futuresres.reporting.a21_more_accounts import _policy as p
    p()


def _set(p: np.ndarray, n: int, rt: float):
    import futuresres.reporting.a02_real as a2
    import futuresres.reporting.a08_gold as a8
    tot = np.float32(n * rt); x = p.astype(np.float32) * n
    a2._PATHS["p"] = ((x - (tot - a8.RT_ENGINE)).astype(np.float32), (x - tot).astype(np.float32), (x - tot).astype(np.float32))


def run(p: np.ndarray, n: int, rt: float, block: bool = True) -> dict:
    import futuresres.reporting.a02_real as a2
    _set(p, n, rt)
    r = a2.sequential(1, "replay")
    out = {"replay": [r["p_any_payout"], r["mean_net"], r["p_net_positive"]]}
    if block:
        bl = [a2.sequential(1, "block", traders=4000, seed=s) for s in (11, 12)]
        out["block"] = [float(np.mean([b[k] for b in bl])) for k in ("p_any_payout", "mean_net", "p_net_positive")]
    a2._PATHS.clear()
    return out


def per_start(p: np.ndarray, d: np.ndarray, n: int, rt: float) -> dict:
    import futuresres.reporting.a02_real as a2
    _set(p, n, rt)
    r = a2.sequential(1, "replay", per_trader=True); a2._PATHS.clear(); e = r["each"]
    return {"date": d[e["start"]].astype("datetime64[D]"), "net": e["net"], "first": e["first_payout_day"], "fees": e["fees"], "paid": e["paid"]}


def _fmt(r: dict) -> str:
    s = f"replay {r['replay'][0]:.0%} {r['replay'][1]:+,.0f}"
    if "block" in r:
        s += f" | block {r['block'][0]:.0%} {r['block'][1]:+,.0f} P(net>0) {r['block'][2]:.0%}"
    return s


# ---------------------------------------------------------------- (1) proxy check
def _proxy_minutes(market: str):
    """A21's proxy minute paths (relative returns, drift as cached - re-removed on the common dates below)."""
    z = np.load(CACHE / f"a21_{'NKD' if market == 'NKD' else 'DAX'}_post.npz")
    return z["h"], z["l"], z["c"], z["d"].astype("datetime64[D]")


def _coarse_rel(h, l, c, k):
    S, T = c.shape; nb = -(-T // k); pad = nb * k - T
    def p(x): return np.concatenate([x, np.repeat(x[:, -1:], pad, 1)], 1) if pad else x
    H, L_, C = p(h).reshape(S, nb, k).max(2), p(l).reshape(S, nb, k).min(2), p(c).reshape(S, nb, k)[:, :, -1]
    O = np.concatenate([np.zeros((S, 1)), C[:, :-1]], 1)
    return O, H, L_, C


def proxy(market: str) -> dict:
    """Real prices (NKD=F futures; ^GDAXI index for DAX) vs A21's CFD proxy on the same dates, both as hourly bars."""
    import futuresres.reporting.a21_more_accounts as a21
    warnings.filterwarnings("ignore")
    if market == "NKD":
        tz, first, last, sym, n, rt = ZoneInfo("Asia/Tokyo"), 9, 14, "NKD=F", 1, 4.0
    else:
        tz, first, last, sym, n, rt = ZoneInfo("Europe/Berlin"), 9, 17, "^GDAXI", 2, 4.0
    bars = session_bars(load(sym, "1h"), first, False, last, tz)
    real, rd, dropped = hourly_rel(bars)
    h, l, c, pd_ = _proxy_minutes(market)
    O, H, L_, C = _coarse_rel(h.astype(np.float64), l.astype(np.float64), c.astype(np.float64), 60)
    prox = points(O, H, L_, C)
    common = np.intersect1d(rd, pd_)
    ri = np.searchsorted(rd, common); pi = np.searchsorted(pd_, common)
    R, P = real[ri], prox[pi]
    if R.shape[1] != P.shape[1]:
        m = min(R.shape[1], P.shape[1]); R, P = R[:, :m], P[:, :m]
    usd = a21.notional("DAX" if market == "DAX" else "NKD")
    out = {"real_source": sym, "sessions_common": int(len(common)), "first": str(common[0]), "last": str(common[-1]),
           "real_sessions_dropped_jump": int(dropped)}
    rc, pc = R[:, -1], P[:, -1]
    rng_r = R.max(1) - R.min(1); rng_p = P.max(1) - P.min(1)
    out["corr_window_return"] = float(np.corrcoef(rc, pc)[0, 1])
    out["sd_ratio_real_over_proxy"] = float(rc.std() / pc.std())
    out["range_ratio_real_over_proxy"] = float(rng_r.mean() / rng_p.mean())
    out["real_daily_sd_usd_one"] = float(rc.std() * usd)
    if market == "NKD":
        vol = np.array([bars[k][4].sum() for k in [x.astype(object) for x in common]])
        out["nkd_window_volume_median"] = float(np.median(vol)); out["nkd_window_volume_p10"] = float(np.quantile(vol, 0.1))
    _policy()
    import futuresres.reporting.a02_real as a2
    a2.STOP_FILL = "level"
    for name, X in (("real", R), ("proxy", P)):
        out[name] = run((_drift(X) * usd).astype(np.float32), n, rt)
        print(f"{market} {name:5} {len(X)} sessions: {_fmt(out[name])}", flush=True)
    print(json.dumps({k: v for k, v in out.items() if k not in ("real", "proxy")}, indent=1), flush=True)
    return out


# ---------------------------------------------------------------- (2) candidates
#: daily bars usable for a long history: Yahoo's daily bar matched the hourly-built session (range ratio >= 0.85, SD
#: ratio >= 0.83: NG, BTC, ZC, ZS, ZW); copper from the owned Databento daily file (roll-correct). Platinum (flat
#: bars), hogs and cattle (range / SD 0.66-0.76) have the hourly history only.
DAILY_OK = ("NG", "BTC", "ZC", "ZS", "ZW", "HG")


def hourly_paths(market: str):
    """Cleaned hourly sessions (last ~2 years), $ per contract at today's value, drift removed; dates; sessions dropped."""
    sym, *_, (fh, pe, lh) = CAND[market]
    hp, hd, dropped = hourly_rel(session_bars(load(sym, "1h"), fh, pe, lh))
    return (_drift(hp) * notional(market)).astype(np.float32), hd, dropped


def long_paths(market: str, era: str):
    if market != "HG":
        p, d = daily_paths(market, era)
        return p, d.astype("datetime64[D]")
    from futuresres.data.daily_bars import load_market
    mk = load_market("HG"); lo, hi = ERAS[era]
    m = (mk.dates >= np.datetime64(lo)) & (mk.dates <= np.datetime64(hi)) & ~mk.crossover & (mk.ret != 0)
    r, rl, rh = mk.ret[m], np.minimum(mk.ret_low[m], mk.ret[m]), np.maximum(mk.ret_high[m], mk.ret[m])
    p = points(np.zeros((len(r), 1)), rh[:, None], rl[:, None], r[:, None])
    return (_drift(p) * notional("HG")).astype(np.float32), mk.dates[m].astype("datetime64[D]")


def _size(sd1: float, cap: int) -> int:
    return int(min(range(1, cap + 1), key=lambda k: abs(k * sd1 - SWING)))


def grid(market: str) -> dict:
    import futuresres.reporting.a02_real as a2
    warnings.filterwarnings("ignore")
    _policy(); a2.STOP_FILL = "level"
    sym, contract, mult, rt, cap, _ = CAND[market]
    out = {"contract": contract, "notional_one": notional(market), "rt": rt, "cap": cap}
    sizes = (1, 2, 3) if cap == 3 else (5, 10, 15, 20, 25, 30)
    hp, hd, dropped = hourly_paths(market)
    sd_h = float(hp[:, -1].std()); n = _size(sd_h, cap)
    out["risk_matched_n"] = n
    sets = {"hourly": (hp, hd)}
    if market in DAILY_OK:
        for era in ERAS:
            sets[era] = long_paths(market, era)
    for name, (p, d) in sets.items():
        sd1 = float(p[:, -1].std())
        out[name] = {"sessions": int(len(p)), "first": str(d[0]), "last": str(d[-1]), "one_contract_daily_sd": sd1, "sizes": {}}
        if name == "hourly":
            out[name]["sessions_dropped_contract_switch"] = int(dropped)
        for k in sorted(set(sizes) | {n}):
            r = run(p, k, rt); r["swing"] = k * sd1
            out[name]["sizes"][k] = r
            print(f"{market} {name:6} {k:2} {contract} (swing ${k*sd1:,.0f}){' *' if k == n else '  '}: {_fmt(r)}", flush=True)
    return out


def _live_series(era: str) -> dict:
    """Daily window results (relative, drift removed) of the five live accounts, keyed by date."""
    import futuresres.reporting.a08_gold as a8
    import futuresres.reporting.a15_crude as c15
    s = {}
    for prod, win in (("MNQ", "rth_0930_1600"), ("MGC", "london_0300_1130")):
        h, l, c, d = a8.era_paths(era, prod, win)
        s[prod] = dict(zip(np.asarray(d).astype("datetime64[D]").tolist(), c[:, -1].tolist())); del h, l, c
    h, l, c, d = c15.mcl_paths(era)
    s["MCL"] = dict(zip(d.astype("datetime64[D]").tolist(), c[:, 0].tolist()))
    for m in ("NKD", "DAX"):
        z = np.load(CACHE / f"a21_{m}_{era}.npz")
        s[m] = dict(zip(z["d"].astype("datetime64[D]").tolist(), z["c"][:, -1].tolist()))
    return s


def _cmat(s: dict, label: str) -> dict:
    names = list(s); mat = {}
    for a_ in names:
        for b_ in names:
            common = sorted(set(s[a_]) & set(s[b_]))
            if len(common) > 100:
                mat[f"{a_}|{b_}"] = float(np.corrcoef([s[a_][k] for k in common], [s[b_][k] for k in common])[0, 1])
    print(label, "      " + " ".join(f"{n:>5}" for n in names))
    for a_ in names:
        print(label, f"{a_:>5} " + " ".join(f"{mat.get(f'{a_}|{b_}', float('nan')):+5.2f}" for b_ in names), flush=True)
    return mat


def corr() -> dict:
    """Daily results of the candidates against the five live accounts: hourly sessions (2024-26, all candidates) and
    long daily histories (DAILY_OK)."""
    out = {}
    s = _live_series("post")
    for m in CAND:
        p, d, _ = hourly_paths(m)
        s[m] = dict(zip(d.tolist(), p[:, -1].tolist()))
    out["hourly_2024_26"] = _cmat(s, "h2y")
    for era in ERAS:
        s = _live_series(era)
        for m in DAILY_OK:
            p, d = long_paths(m, era)
            s[m] = dict(zip(d.tolist(), p[:, -1].tolist()))
        out[era] = _cmat(s, era)
    return out


def portfolio(cands: list[str], sizes: dict) -> dict:
    """The five live accounts, then + each candidate (six), + pairs (seven), and each candidate in place of each live
    account (five, swapped): joint replay on common start dates, 84 days, real order. Periods: the hourly history
    (2024-26, every candidate) and 2010-20 / 2021-26 for candidates with a long history."""
    import itertools
    import futuresres.reporting.a02_real as a2
    import futuresres.reporting.a12_joint as j
    import futuresres.reporting.a15_crude as c15
    import futuresres.reporting.a21_more_accounts as a21
    warnings.filterwarnings("ignore")
    _policy(); a2.STOP_FILL = "level"
    out = {}
    live = {}
    for era in ERAS:
        h, l, c, d = c15.mcl_paths(era); orig = a2._bracket_day
        a2._PATHS["p"], o = c15._engine(h, l, c, 10); a2._bracket_day = c15.one_bar_rule(o)
        rc = a2.sequential(1, "replay", per_trader=True); a2._bracket_day = orig; a2._PATHS.clear(); e = rc["each"]
        live[era] = {"MNQ": j.per_start(era, "MNQ"), "MGC": j.per_start(era, "MGC"),
                     "MCL": {"date": d[e["start"]], "net": e["net"], "first": e["first_payout_day"], "fees": e["fees"], "paid": e["paid"]},
                     "NKD": a21.per_start("NKD", era, 1), "DAX": a21.per_start("DAX", era, 2)}
    for period in ("hourly", "pre", "post"):
        acc = dict(live["post" if period == "hourly" else period])
        cs = list(cands) if period == "hourly" else [m for m in cands if m in DAILY_OK]
        for m in cs:
            p, dd = (hourly_paths(m)[:2] if period == "hourly" else long_paths(m, period))
            acc[m] = per_start(p, dd, sizes[m], CAND[m][3])
        common = None
        for v in acc.values():
            common = set(v["date"].tolist()) if common is None else common & set(v["date"].tolist())
        common = np.array(sorted(common), dtype="datetime64[D]")
        sel = {k: {f: v[f][np.searchsorted(v["date"], common)] for f in ("net", "first", "fees")} for k, v in acc.items()}
        res = {"common_starts": int(len(common)), "first": str(common[0]), "last": str(common[-1]), "rows": {}}
        five = ("MNQ", "MGC", "MCL", "NKD", "DAX")
        combos = [("5 live", five)] + [(f"+{m}", five + (m,)) for m in cs]
        combos += [(f"+{a}+{b}", five + (a, b)) for a, b in itertools.combinations(cs, 2)]
        combos += [(f"{m} for {x}", tuple(y for y in five if y != x) + (m,)) for m in cs for x in five]
        for label, keys in combos:
            net = sum(sel[k]["net"] for k in keys); fees = sum(sel[k]["fees"] for k in keys)
            pays = sum((sel[k]["first"] > 0).astype(int) for k in keys)
            res["rows"][label] = {"mean_net": float(net.mean()), "median_net": float(np.median(net)),
                                  "p_net_positive": float((net > 0).mean()), "net_p10": float(np.quantile(net, 0.1)),
                                  "worst": float(net.min()), "mean_fees": float(fees.mean()), "streams_paying": float(pays.mean())}
        for k in (*five, *cs):
            res["rows"][f"alone {k}"] = {"mean_net": float(sel[k]["net"].mean()), "p_payout": float((sel[k]["first"] > 0).mean()),
                                         "p_net_positive": float((sel[k]["net"] > 0).mean())}
        out[period] = res
        print(f"== {period}: {len(common)} common starts {common[0]} -> {common[-1]}", flush=True)
        for label, r in res["rows"].items():
            if "mean_fees" in r:
                print(f"{period} {label:14} mean {r['mean_net']:+7,.0f} median {r['median_net']:+7,.0f} P(net>0) {r['p_net_positive']:4.0%} "
                      f"p10 {r['net_p10']:+7,.0f} worst {r['worst']:+7,.0f} fees {r['mean_fees']:6,.0f}", flush=True)
            else:
                print(f"{period} {label:14} mean {r['mean_net']:+7,.0f} P(payout) {r['p_payout']:.0%} P(net>0) {r['p_net_positive']:.0%}", flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true"); ap.add_argument("--proxy"); ap.add_argument("--grid")
    ap.add_argument("--corr", action="store_true"); ap.add_argument("--portfolio", nargs="*")
    a = ap.parse_args(argv)
    if a.fetch:
        for s in [v[0] for v in CAND.values()] + list(EXTRA.values()):
            for iv in ("1d", "1h"):
                d = fetch(s, iv); print(s, iv, d.height, flush=True); time.sleep(0.5)
        return 0
    if a.proxy:
        (ROOT / "reports" / f"a22_proxy_{a.proxy}.json").write_text(json.dumps(proxy(a.proxy), indent=1) + "\n"); return 0
    if a.grid:
        (ROOT / "reports" / f"a22_{a.grid}.json").write_text(json.dumps(grid(a.grid), indent=1) + "\n"); return 0
    if a.corr:
        (ROOT / "reports" / "a22_corr.json").write_text(json.dumps(corr(), indent=1) + "\n"); return 0
    if a.portfolio is not None:
        sizes = {m: json.loads((ROOT / "reports" / f"a22_{m}.json").read_text())["risk_matched_n"] for m in a.portfolio}
        (ROOT / "reports" / "a22_portfolio.json").write_text(json.dumps(portfolio(a.portfolio, sizes), indent=1) + "\n"); return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
