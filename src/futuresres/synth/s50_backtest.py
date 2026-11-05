"""SN50 (Synth) miner backtest: would a simple ensemble model have earned emissions? decisions.md §1164.

For every scored Crypto-24h prompt in a window: the validator's realized path (Synth API), every live miner's CRPS sum for that prompt, and our
own 1,000-path ensemble built only from data before the start (Binance global 1-minute closes via the public data mirror; start price = the last close available before t0). Our CRPS
uses the subnet's own code (crps_upstream.py, CRYPTO_24H intervals). Then the subnet's transform (cap at the 90th percentile, subtract the best),
the asset-weighted average over the window, and the softmax (beta 0.15) give our share of the competition against the field.

    python -m futuresres.synth.s50_backtest BTC 10      # asset, days
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
from curl_cffi import requests

from futuresres.synth.fast_crps import crps_sum

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "synth"
API = "https://api.synthdata.co"
INTERVALS = {"5min": 300, "30min": 1800, "3hour": 10800, "24hour_abs": 86400}
BINANCE = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT", "HYPE": "HYPEUSDT"}   # HYPE: validator scores Hyperliquid spot; Binance carries the history
HYPERLIQUID = {"HYPE": "@107", "XAU": "xyz:GOLD", "NVDAX": "xyz:NVDA", "TSLAX": "xyz:TSLA", "AAPLX": "xyz:AAPL", "GOOGLX": "xyz:GOOGL", "SP500": "xyz:SP500",
               "SPCX": "xyz:SPCX", "WTIOIL": "xyz:CL"}                     # the validator's feeds (synth/miner/price_simulation.py)


def hl5(asset: str) -> dict:
    """Hyperliquid 5-minute closes {open_ms: close}: the API serves the latest ~5,000 candles (~17 days); merged into a growing cache."""
    f = CACHE / f"hl5_{asset}.json"
    have = {int(k): v for k, v in json.loads(f.read_text()).items()} if f.exists() else {}
    now = int(time.time() * 1000)
    for back in (17, 9, 1):
        t0 = now - back * 86400000
        try:
            rows = requests.post("https://api.hyperliquid.xyz/info", json={"type": "candleSnapshot", "req": {"coin": HYPERLIQUID[asset], "interval": "5m",
                                 "startTime": t0, "endTime": min(now, t0 + 9 * 86400000)}}, timeout=60, impersonate="chrome").json()
            for c in rows:
                have[int(c["t"])] = float(c["c"])
        except Exception:
            pass
        time.sleep(0.5)
    CACHE.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(have))
    return have


def get(url, params=None, required=True):
    err = ""
    for k in range(5):
        try:
            r = requests.get(url, params=params, timeout=60, impersonate="chrome")
            if r.status_code == 200:
                return r.json()
            err = f"{r.status_code} {r.text[:200]}"
        except Exception as e:                                  # timeouts: retry, then skip
            err = repr(e)[:200]
        time.sleep(3 * (k + 1))
    if required:
        raise RuntimeError(f"{url} {err}")
    return None


def prompts(asset: str, days: int):
    """{prompt start (UTC iso): {uid: crps}} from the historical scores (prompt start = scored_time - 24 h)."""
    f = CACHE / f"scores_{asset}_{days}.json"
    if f.exists():
        return json.loads(f.read_text())
    end = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0); out = {}
    for h in range(days * 24):
        a = end - dt.timedelta(hours=h + 1); b = end - dt.timedelta(hours=h)
        rows = get(f"{API}/validation/scores/historical", {"from": a.strftime("%Y-%m-%dT%H:%M:%SZ"), "to": b.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                            "asset": asset, "time_increment": 300, "time_length": 86400}, required=False) or []
        for r in rows:
            st = (dt.datetime.fromisoformat(r["scored_time"].replace("Z", "+00:00")) - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            out.setdefault(st, {})[str(r["miner_uid"])] = r["crps"]
    CACHE.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(out))
    return out


def realized(asset: str, start: str):
    f = CACHE / f"real_{asset}_{start.replace(':', '')}.json"
    if f.exists():
        return json.loads(f.read_text())
    r = get(f"{API}/validation/realized-path", {"start_time": start, "asset": asset, "time_increment": 300, "time_length": 86400}, required=False)
    p = (r or {}).get("real_prices")
    if p:
        f.write_text(json.dumps(p))
    return p


def minutes(asset: str, t0: int, t1: int) -> dict:
    """Binance (global, public market-data mirror data-api.binance.vision) 1-minute closes {open_ms: close} over [t0, t1] (ms), cached."""
    f = CACHE / f"bnc_{asset}.json"
    have = {int(k): v for k, v in json.loads(f.read_text()).items()} if f.exists() else {}
    t = t0
    while t < t1:
        if all((t + 60000 * i) in have for i in range(0, 1000, 97)) and (t + 999 * 60000 > t1 or (t + 999 * 60000) in have):
            t += 1000 * 60000; continue
        rows = get("https://data-api.binance.vision/api/v3/klines", {"symbol": BINANCE[asset], "interval": "1m", "startTime": t, "limit": 1000})
        for k in rows:
            have[int(k[0])] = float(k[4])
        t = (int(rows[-1][0]) + 60000) if rows else t + 1000 * 60000
        time.sleep(0.2)
    f.write_text(json.dumps(have))
    return have


def hl1h(asset: str) -> dict:
    """Hyperliquid 1-hour closes {open_ms: close} (~5,000 h ≈ 208 days), cached."""
    f = CACHE / f"hl1h_{asset}.json"
    if f.exists() and time.time() - f.stat().st_mtime < 6 * 3600:
        return {int(k): v for k, v in json.loads(f.read_text()).items()}
    now = int(time.time() * 1000)
    rows = requests.post("https://api.hyperliquid.xyz/info", json={"type": "candleSnapshot", "req": {"coin": HYPERLIQUID[asset], "interval": "1h",
                         "startTime": now - 5000 * 3600000, "endTime": now}}, timeout=60, impersonate="chrome").json()
    have = {int(c["t"]): float(c["c"]) for c in rows}; f.write_text(json.dumps(have)); return have


YAHOO = {"SP500": "^GSPC", "XAU": "GC=F", "WTIOIL": "CL=F", "NVDAX": "NVDA", "TSLAX": "TSLA", "AAPLX": "AAPL", "GOOGLX": "GOOGL"}


def yahoo5(asset: str) -> dict:
    """Yahoo 5-minute closes {open_ms: close} (~60 days, pre/post included), cached 6 h."""
    f = CACHE / f"y5_{asset}.json"
    if f.exists() and time.time() - f.stat().st_mtime < 6 * 3600:
        return {int(k): v for k, v in json.loads(f.read_text()).items()}
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{YAHOO[asset]}", params={"interval": "5m", "range": "60d", "includePrePost": "true"},
                     timeout=60, impersonate="chrome").json()["chart"]["result"][0]
    have = {int(t) * 1000: c for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c}
    f.write_text(json.dumps(have)); return have


def yahoo_profile(Y: dict, t0: int) -> np.ndarray:
    """Weekday per-5-minute-slot vol from Yahoo bars before t0 (consecutive bars only), lightly smoothed; NaN where Yahoo has no bars."""
    ks = np.array(sorted(k for k in Y if k < t0)); v = np.log(np.array([Y[k] for k in ks]))
    ok = np.diff(ks) == 300000; r = np.diff(v)[ok]; ts = ks[1:][ok]
    slot = (ts // 300000) % 288; wd = np.array([dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).weekday() < 5 for t in ts])
    pr = np.array([np.sqrt(np.mean(r[(slot == j) & wd] ** 2)) if ((slot == j) & wd).sum() >= 10 else np.nan for j in range(288)])
    return pr


def hour_profile(H: dict, t0: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-5-minute-step vol (log units) by UTC hour, weekday and weekend, from hourly closes strictly before t0 (hour vol / sqrt(12))."""
    ks = np.array(sorted(k for k in H if k < t0 - 3600000)); v = np.array([H[k] for k in ks]); r = np.diff(np.log(v)); ks = ks[1:]
    tt = [dt.datetime.fromtimestamp(k / 1000, dt.timezone.utc) for k in ks]; hr = np.array([t.hour for t in tt]); we = np.array([t.weekday() >= 5 for t in tt])
    prof = lambda mask: np.array([np.sqrt(np.mean(r[(hr == h) & mask] ** 2)) if ((hr == h) & mask).sum() > 3 else np.nan for h in range(24)]) / np.sqrt(12)
    a, b2 = prof(~we), prof(we)
    return np.where(np.isnan(a), np.nanmedian(a), a), np.where(np.isnan(b2), np.nanmedian(b2), b2)


def _et_session(ms: int) -> int:
    """0 = US cash hours (09:30-16:00 New York, Mon-Fri), 1 = weekday closed, 2 = weekend (§1217)."""
    from zoneinfo import ZoneInfo
    t = dt.datetime.fromtimestamp(ms / 1000, ZoneInfo("America/New_York"))
    if t.weekday() >= 5:
        return 2
    m = t.hour * 60 + t.minute
    return 0 if 570 <= m < 960 else 1


def yahoo_ny_shape(Y: dict, t0: int) -> np.ndarray:
    """Weekday volatility SHAPE per New-York 5-minute slot (288) from Yahoo bars before t0 (≤ 60 days, consecutive bars, DST-correct);
    NaN where Yahoo has fewer than 10 bars (overnight for cash-only symbols) (§1218)."""
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
    ks = np.array(sorted(k for k in Y if k < t0)); v = np.log(np.array([Y[k] for k in ks]))
    ok = np.diff(ks) == 300000; r = np.diff(v)[ok]; ts = ks[1:][ok]
    slot = np.array([(lambda t: -1 if t.weekday() >= 5 else (t.hour * 60 + t.minute) // 5)(dt.datetime.fromtimestamp(x / 1000, NY)) for x in ts])
    return np.array([np.sqrt(np.mean(r[slot == j] ** 2)) if (slot == j).sum() >= 10 else np.nan for j in range(288)])


def ses_ensemble(closes: np.ndarray, s0: float, model: str, rng, t0: int, n=1000, steps=288, k: float = 1.0, Y: dict | None = None) -> np.ndarray:
    """'ses' (§1217): session-aware 5-minute model for Hyperliquid equity / commodity perps. Weekday volatility per New-York 5-minute slot
    (unsmoothed: keeps the cash open), weekends one level; profiles and the bootstrap pool from the validator's own feed (`closes`, 5-min,
    ending at t0). Options: _vv<pct> per-path vol-of-vol; _lv<hl> scales by the recent cash-session level vs the profile (EWMA half-life in
    cash bars)."""
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
    r5 = np.diff(np.log(closes)); m = len(r5)
    ts = t0 - (m - np.arange(m)) * 300000
    def key(ms):
        t = dt.datetime.fromtimestamp(ms / 1000, NY)
        return -1 if t.weekday() >= 5 else (t.hour * 60 + t.minute) // 5
    kh = np.array([key(int(x)) for x in ts]); kf = np.array([key(int(t0 + j * 300000)) for j in range(steps)])
    prof = np.full(288, np.nan)
    for j in range(288):
        x = r5[kh == j]
        if len(x) >= 3: prof[j] = np.sqrt(np.mean(x ** 2))
    prof = np.where(np.isnan(prof), np.nanmedian(prof), prof)
    if "_yc" in model and Y:                               # cash-hour SHAPE from 60 days of Yahoo (stable), LEVEL from the validator's feed (§1218)
        ys = yahoo_ny_shape(Y, t0); cash = np.arange(114, 192)
        good = cash[~np.isnan(ys[cash])]
        if len(good) > 40:
            hl_cash = np.sqrt(np.mean(r5[np.isin(kh, good)] ** 2)); ylev = np.sqrt(np.mean(ys[good] ** 2))
            prof[good] = ys[good] / ylev * hl_cash
    wk = r5[kh == -1]; wlev = np.sqrt(np.mean(wk ** 2)) if len(wk) > 20 else np.nanmedian(prof) * 0.4
    sig_h = np.where(kh == -1, wlev, prof[np.maximum(kh, 0)]); z = r5 / np.maximum(sig_h, 1e-12)
    lev = 1.0
    if "_lv" in model:
        hl = float(model.split("_lv")[1].split("_")[0]); cash = np.array([_et_session(int(x)) == 0 for x in ts])
        zc = z[cash]
        if len(zc) > 30:
            w = 0.5 ** (np.arange(len(zc))[::-1] / hl); lev = float(np.sqrt((w * zc ** 2).sum() / w.sum()))
    fut = np.where(kf == -1, wlev, prof[np.maximum(kf, 0)]) * k
    fut = np.where(kf == -1, fut, fut * lev)
    pool = z[-6000:] / np.sqrt(np.mean(z[-6000:] ** 2))
    if "_sp" in model:                                     # session-specific shock pools (§1217): weekend shocks from weekend bars (mostly flat
        sh = np.array([_et_session(int(x)) for x in ts])   # with rare jumps), cash from cash bars, closed from closed bars
        sf = np.array([_et_session(int(t0 + j * 300000)) for j in range(steps)]); inc = np.empty((n, steps))
        for sess in (0, 1, 2):
            zp = z[sh == sess]; zp = zp / np.sqrt(np.mean(zp ** 2)) if len(zp) > 50 else pool; cols = np.where(sf == sess)[0]
            if len(cols): inc[:, cols] = rng.choice(zp, (n, len(cols))) * fut[None, cols]
    else:
        inc = rng.choice(pool, (n, steps)) * fut[None, :]
    if "_cd" in model:                                     # per-path drift during cash hours: d ~ N(0, cd/100 × the bar's sd) per path, so
        cd = float(model.split("_cd")[1].split("_")[0].split("@")[0]) / 100.0   # some paths trend through the session (3-h cash spread)
        sf = np.array([_et_session(int(t0 + j * 300000)) for j in range(steps)])
        d = rng.normal(0, cd, (n, 1)) * fut[None, :] * (sf == 0)[None, :]
        inc = inc + d
    if "_vv" in model:
        vv = float(model.split("_vv")[1].split("_")[0]) / 100.0
        inc = inc * np.exp(rng.normal(-0.5 * vv ** 2, vv, (n, 1)))
    if "_oux" in model:                                    # mean reversion OUTSIDE cash hours only (§1218): closed / weekend perps oscillate around a
        th = float(model.split("_oux")[1].split("_")[0].split("@")[0]) / 1e3   # stable reference; theta per 5-min step (×1e-3) toward the start
        sf = np.array([_et_session(int(t0 + j * 300000)) for j in range(steps)]); x = np.zeros((n, steps + 1))
        for t in range(steps):
            x[:, t + 1] = (1 - (th if sf[t] != 0 else 0.0)) * x[:, t] + inc[:, t]
        return s0 * np.exp(x)
    return s0 * np.exp(np.concatenate([np.zeros((n, 1)), np.cumsum(inc, axis=1)], axis=1))


def ensemble(closes: np.ndarray, s0: float, model: str, rng, n=1000, steps=288, slot0: int = 0, k: float = 1.0, stride: int = 5, day0: int = 0,
             hprof: tuple | None = None) -> np.ndarray:
    """1,000 paths of 289 prices at 5-minute steps from the 1-minute closes before t0 (closes end at t0 - 1 min, aligned to 5-minute slots;
    slot0 = t0's 5-minute slot of the UTC day)."""
    r5 = np.diff(np.log(closes[::stride]))                  # 5-minute log returns, oldest first
    if model.startswith("tod"):                              # time-of-day vol profile x EWMA level, bootstrapped standardised shocks
        m = len(r5); slots = (slot0 - m + np.arange(m)) % 288
        if "_yp" in model and hprof is not None and len(hprof) == 3:   # weekday 5-min profile from Yahoo (60 days), gaps/weekends from the HL hourly profile
            dow = (day0 + (slot0 - m + np.arange(m)) // 288) % 7; wkd = dow >= 5
            P_wd = np.where(np.isnan(hprof[2]), np.repeat(hprof[0], 12), hprof[2]); P_we = np.repeat(hprof[1], 12)
            prof_hist = np.where(wkd, P_we[slots], P_wd[slots])
            fdow = (day0 + (slot0 + np.arange(steps)) // 288) % 7; fs = (slot0 + np.arange(steps)) % 288; fut_prof = np.where(fdow >= 5, P_we[fs], P_wd[fs])
        elif "_lh" in model and hprof is not None:            # long hourly weekday/weekend profile (Hyperliquid 1 h candles, ~200 days)
            dow = (day0 + (slot0 - m + np.arange(m)) // 288) % 7; wkd = dow >= 5
            P_wd = np.repeat(hprof[0], 12); P_we = np.repeat(hprof[1], 12); prof_hist = np.where(wkd, P_we[slots], P_wd[slots])
            fdow = (day0 + (slot0 + np.arange(steps)) // 288) % 7; fs = (slot0 + np.arange(steps)) % 288; fut_prof = np.where(fdow >= 5, P_we[fs], P_wd[fs])
        elif "_wk" in model:                                 # separate weekday / weekend profiles (day0 = weekday of t0's UTC day, Mon=0)
            dow = (day0 + (slot0 - m + np.arange(m)) // 288) % 7; wkd = dow >= 5
            def mk(mask):
                pr = np.array([np.sqrt(np.mean(r5[(slots == j) & mask] ** 2)) if ((slots == j) & mask).any() else np.nan for j in range(288)])
                pr = np.where(np.isnan(pr), np.nanmedian(pr), pr)
                if "_ns" in model:                           # no smoothing: keeps one-slot spikes such as the US cash open
                    return pr
                return np.convolve(np.r_[pr[-2:], pr, pr[:2]], np.ones(5) / 5, "valid")
            P_wd, P_we = mk(~wkd), mk(wkd); prof_hist = np.where(wkd, P_we[slots], P_wd[slots])
            fdow = (day0 + (slot0 + np.arange(steps)) // 288) % 7; fut_prof = np.where(fdow >= 5, P_we[(slot0 + np.arange(steps)) % 288], P_wd[(slot0 + np.arange(steps)) % 288])
        else:
            prof = np.array([np.sqrt(np.mean(r5[slots == j] ** 2)) for j in range(288)]); prof = np.convolve(np.r_[prof[-2:], prof, prof[:2]], np.ones(5) / 5, "valid")
            prof_hist = prof[slots]; fut_prof = prof[(slot0 + np.arange(steps)) % 288]
        z_hist = r5 / np.maximum(prof_hist, 1e-12)
        hl = 72.0 if model.startswith("tod_6h") else 288.0
        dec = 288.0
        if model.startswith("todg"):                         # todg_<half-life steps>_<decay steps>
            hl, dec = (float(x) for x in model.split("_")[1:3])
        if model.startswith("todv"):                         # todv_<half-life>_<long lookback steps>_<alpha>_<beta> (§1207)
            hl, lb, ga, gb = (float(x) for x in model.split("_")[1:5])
        w = 0.5 ** (np.arange(m)[::-1] / hl); level = np.sqrt((w * z_hist ** 2).sum() / w.sum())
        long = np.sqrt(np.mean(z_hist[-2016:] ** 2)); decay = np.exp(-np.arange(steps) / dec)         # level reverts to the 7-day mean over ~a day
        lev = long + (level - long) * decay
        fut = fut_prof * lev * k
        pool = z_hist[-8640:] / np.sqrt(np.mean(z_hist[-8640:] ** 2))
        if "_c" in model:                                    # conditional shape: residuals standardised by a causal local EWMA level as well
            a = 1 - 0.5 ** (1 / 12.0); v = np.empty(m); acc = np.mean(z_hist[:288] ** 2)
            for t in range(m):
                v[t] = acc; acc = (1 - a) * acc + a * z_hist[t] ** 2
            zc = z_hist / np.sqrt(v); pool = zc[-8640:] / np.sqrt(np.mean(zc[-8640:] ** 2))
        z = rng.choice(pool, (n, steps)) * fut[None, :]
        if model.startswith("todv"):                         # GARCH-style per-path variance in profile units: h' = (1-a-b)L^2 + a e^2 + b h,
            L2 = np.mean(z_hist[-int(lb):] ** 2)             # L = recent (lb steps) level, h0 = current EWMA level^2; e = the path's own shock
            h = np.full(n, level ** 2); eps = rng.choice(pool, (n, steps)); z = np.empty((n, steps))
            for t in range(steps):
                e = eps[:, t] * np.sqrt(h)
                z[:, t] = e * fut_prof[t] * k
                h = (1 - ga - gb) * L2 + ga * e ** 2 + gb * h
        if "_vv" in model:                                  # per-path vol-of-vol (§1216): each path draws a mean-one lognormal level multiplier,
            vv = float(model.split("_vv")[1].split("_")[0].split("@")[0]) / 100.0   # fattening the 24 h tails (realized 24 h tails 0.15-0.19 vs 0.10)
            z = z * np.exp(rng.normal(-0.5 * vv ** 2, vv, (n, 1)))
        hot = level > 1.15 * long                            # volatile regime: the recent level well above the 7-day level (§1218)
        if "_mo" in model and "_moa" not in model and hot:                           # momentum: drift per step = mo/100 × the last 3 h's mean 5-minute log return
            mo = float(model.split("_mo")[1].split("_")[0].split("@")[0]) / 100.0
            z = z + mo * float(np.mean(r5[-36:]))
        if "_moa" in model:                                  # ALWAYS-ON momentum (§1224): same drift as _mo without the hot-regime gate
            moa = float(model.split("_moa")[1].split("_")[0].split("@")[0]) / 100.0
            z = z + moa * float(np.mean(r5[-36:]))
        if "_ouc" in model and hot:                          # conditional mean reversion: off in the volatile regime
            model = model.replace("_ouc", "_nou")
        if "_ou" in model and "_nou" not in model:          # mean reversion of log price toward the start: x_{t+1} = (1 - theta) x_t + z_t
            th = float(model.split("_ou")[1].split("_")[0].replace("c", "")) / 1e4; x = np.zeros((n, steps + 1))
            for t in range(steps):
                x[:, t + 1] = (1 - th) * x[:, t] + z[:, t]
            return s0 * np.exp(x)
        if model.startswith("tod_mix"):                     # vol-of-vol: each path draws its own level multiplier (mean-one lognormal)
            vv = float(model.split("_")[-1]) / 100.0
            z = z * np.exp(rng.normal(-0.5 * vv ** 2, vv, (n, 1)))
        return s0 * np.exp(np.concatenate([np.zeros((n, 1)), np.cumsum(z, axis=1)], axis=1))
    if model == "gbm_24h":
        sig = r5[-288:].std()
        z = rng.standard_normal((n, steps)) * sig
    elif model == "gbm_7d":
        sig = r5[-2016:].std()
        z = rng.standard_normal((n, steps)) * sig
    elif model == "ewma_t":                                  # EWMA vol (half-life 1 day), Student-t(4) shocks scaled to unit variance
        w = 0.5 ** (np.arange(len(r5))[::-1] / 288.0); sig = np.sqrt((w * r5 ** 2).sum() / w.sum())
        z = rng.standard_t(4, (n, steps)) / np.sqrt(2.0) * sig
    elif model == "boot_7d":                                 # bootstrap of the last 7 days' 5-minute returns (keeps the fat tails)
        pool = r5[-2016:] - r5[-2016:].mean()
        z = rng.choice(pool, (n, steps))
    else:
        raise ValueError(model)
    paths = s0 * np.exp(np.concatenate([np.zeros((n, 1)), np.cumsum(z, axis=1)], axis=1))
    return paths


_DVOL = None


def iv_ratio(asset: str, t0: int, days: float = 7.0) -> float:
    """Deribit DVOL (30-day implied vol, hourly; data/synth/dvol.json) regime ratio at t0: the last hourly close known before t0 divided by
    the mean of the closes over the previous `days` (§1215). SOL / XRP / others use BTC's. 1.0 when unavailable."""
    global _DVOL
    if _DVOL is None:
        f = CACHE / "dvol.json"
        _DVOL = {c: sorted((int(k), v) for k, v in d.items()) for c, d in json.loads(f.read_text()).items()} if f.exists() else {}
    ser = _DVOL.get(asset if asset in ("BTC", "ETH") else "BTC")
    if not ser:
        return 1.0
    known = [v for ts, v in ser if ts + 3600000 <= t0]
    hist = [v for ts, v in ser if t0 - days * 86400000 <= ts + 3600000 <= t0]
    return known[-1] / (sum(hist) / len(hist)) if known and hist else 1.0


def main(asset: str, days: int, models=("boot_7d", "tod_1d", "tod_6h", "tod_6h@0.9", "tod_6h@1.1")) -> dict:
    P = prompts(asset, days)
    starts = sorted(P)
    t_lo = int(dt.datetime.fromisoformat(starts[0].replace("Z", "+00:00")).timestamp() * 1000) - 32 * 86400000
    t_hi = int(dt.datetime.fromisoformat(starts[-1].replace("Z", "+00:00")).timestamp() * 1000)
    hl = asset in HYPERLIQUID and asset not in BINANCE
    M = hl5(asset) if hl else minutes(asset, t_lo, t_hi)
    H = hl1h(asset) if hl else None
    Y = yahoo5(asset) if asset in YAHOO else None
    keys = np.array(sorted(M)); vals = np.array([M[k] for k in keys])
    stride, look = (1, 6 * 288) if hl else (5, 31 * 1440)
    if hl and any(m.startswith("ses") for m in models):
        look = int(__import__('os').environ.get('SES_LOOK', '16')) * 288   # the session model needs ≥ 1-2 weekends of the validator's feed (§1217)
    rng = np.random.default_rng(1164)
    rows = []
    for st in starts:
        real = realized(asset, st)
        if not real or len(real) < 289 or len(P[st]) < 100:
            continue
        t0 = int(dt.datetime.fromisoformat(st.replace("Z", "+00:00")).timestamp() * 1000)
        i = np.searchsorted(keys, t0 - (300000 if hl else 60000), side="right")   # last bar whose close is known at t0
        if i < look:
            continue
        hist = vals[i - look:i]; s0 = float(hist[-1]); slot0 = (t0 // 300000) % 288; day0 = dt.datetime.fromtimestamp(t0 / 1000, dt.timezone.utc).weekday()
        hp = hour_profile(H, t0) if H else None
        if hp is not None and Y is not None:
            hp = (hp[0], hp[1], yahoo_profile(Y, t0))
        ivr = iv_ratio(asset, t0)
        kk = lambda m: (float(m.split("@")[1]) if "@" in m else 1.0) * (ivr ** float(m.split("_iv")[1].split("@")[0].split("_")[0]) if "_iv" in m else 1.0)
        ens = lambda m: (ses_ensemble(hist, s0, m.split("@")[0], rng, t0, k=kk(m), Y=Y) if m.startswith("ses") else
                         ensemble(hist[-6 * 288:] if hl else hist, s0, m.split("@")[0], rng, slot0=slot0, k=kk(m), stride=stride, day0=day0, hprof=hp))
        def ensx(m):                                         # "mix:A|B[|wA]" — a mixture: wA of the paths from model A, the rest from B (§1222)
            if not m.startswith("mix:"):
                return ens(m)
            parts = m[4:].split("|"); wa = float(parts[2]) if len(parts) > 2 else 0.5
            pa, pb = ens(parts[0]), ens(parts[1]); na = int(round(wa * len(pa)))
            return np.concatenate([pa[:na], pb[:len(pb) - na]], axis=0)
        paths = {m: ensx(m) for m in models}
        ours = {m: crps_sum(paths[m], np.array(real, float), 300, INTERVALS) for m in models}
        rl = np.log(np.array(real, float)); row = {"start": st, "field": P[st], **ours, "_move24": float(rl[-1] - rl[0]),
                                                   "_rv": float(np.sqrt(np.sum(np.diff(rl) ** 2)))}
        if __import__("os").environ.get("S50_PIT"):           # calibration (§1229): where the realized log return sits in our paths, and our width
            for m in models:
                lp = np.log(paths[m])
                for h in (12, 72, 288):
                    f = lp[:, h] - lp[:, 0]; r = rl[h] - rl[0]
                    row[f"_pit_{m}_{h}"] = float(np.mean(f < r)); row[f"_sd_{m}_{h}"] = float(np.std(f))
        rows.append(row)
    out = summarise(rows, models)
    (CACHE / f"bt_{asset}_{days}.json").write_text(json.dumps({"summary": out, "n_prompts": len(rows)}, indent=1))
    (CACHE / f"rows_{asset}_{days}.json").write_text(json.dumps([{k: v for k, v in r.items() if k != "field"} | {"_field_median": float(np.median(
        [v for v in r["field"].values() if v > 0]))} for r in rows]))      # per-prompt diagnosis (§1205)
    return out


def summarise(rows, models, beta=0.15):
    """Per model: mean percentile rank in the field, and the softmax share our averaged transformed score would get vs the field's averages."""
    out = {}
    for m in models:
        pct, our_s, per_uid = [], [], {}
        for r in rows:
            uids = list(r["field"]); f = np.array([r["field"][u] for u in uids], float); allv = np.append(f, r[m])
            ok = allv > 0                                         # crps <= 0 marks an invalid submission: it gets the 90th percentile
            cap = np.percentile(allv[ok], 90); allv = np.where(ok, np.minimum(allv, cap), cap); allv = allv - allv.min()
            our_s.append(allv[-1]); pct.append(float((f[f > 0] < r[m]).mean() * 100))
            for u, v in zip(uids, allv[:-1]):
                per_uid.setdefault(u, []).append(v)
        L_us = float(np.mean(our_s)); L_field = np.array([np.mean(v) for v in per_uid.values() if len(v) >= 0.8 * len(rows)])
        wts = np.exp(-beta * np.append(L_field, L_us)); share = wts[-1] / wts.sum()
        out[m] = {"prompts": len(rows), "mean_pct_rank": round(float(np.mean(pct)), 1), "L_us": round(L_us, 2), "L_field_median": round(float(np.median(L_field)), 2),
                  "L_field_best": round(float(L_field.min()), 2), "share_pct": round(share * 100, 3), "median_share_pct": round(float(np.median(wts[:-1]) / wts.sum() * 100), 3)}
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], int(sys.argv[2]), *([tuple(sys.argv[3].split(","))] if len(sys.argv) > 3 else [])), indent=1))
