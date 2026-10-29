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
BINANCE = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT"}
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


def ensemble(closes: np.ndarray, s0: float, model: str, rng, n=1000, steps=288, slot0: int = 0, k: float = 1.0, stride: int = 5, day0: int = 0) -> np.ndarray:
    """1,000 paths of 289 prices at 5-minute steps from the 1-minute closes before t0 (closes end at t0 - 1 min, aligned to 5-minute slots;
    slot0 = t0's 5-minute slot of the UTC day)."""
    r5 = np.diff(np.log(closes[::stride]))                  # 5-minute log returns, oldest first
    if model.startswith("tod"):                              # time-of-day vol profile x EWMA level, bootstrapped standardised shocks
        m = len(r5); slots = (slot0 - m + np.arange(m)) % 288
        if "_wk" in model:                                   # separate weekday / weekend profiles (day0 = weekday of t0's UTC day, Mon=0)
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
        if "_ou" in model:                                  # mean reversion of log price toward the start: x_{t+1} = (1 - theta) x_t + z_t
            th = float(model.split("_ou")[1].split("_")[0]) / 1e4; x = np.zeros((n, steps + 1))
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


def main(asset: str, days: int, models=("boot_7d", "tod_1d", "tod_6h", "tod_6h@0.9", "tod_6h@1.1")) -> dict:
    P = prompts(asset, days)
    starts = sorted(P)
    t_lo = int(dt.datetime.fromisoformat(starts[0].replace("Z", "+00:00")).timestamp() * 1000) - 32 * 86400000
    t_hi = int(dt.datetime.fromisoformat(starts[-1].replace("Z", "+00:00")).timestamp() * 1000)
    hl = asset in HYPERLIQUID
    M = hl5(asset) if hl else minutes(asset, t_lo, t_hi)
    keys = np.array(sorted(M)); vals = np.array([M[k] for k in keys])
    stride, look = (1, 6 * 288) if hl else (5, 31 * 1440)
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
        ours = {m: crps_sum(ensemble(hist, s0, m.split("@")[0], rng, slot0=slot0, k=float(m.split("@")[1]) if "@" in m else 1.0, stride=stride, day0=day0),
                            np.array(real, float), 300, INTERVALS) for m in models}
        rows.append({"start": st, "field": P[st], **ours})
    out = summarise(rows, models)
    (CACHE / f"bt_{asset}_{days}.json").write_text(json.dumps({"summary": out, "n_prompts": len(rows)}, indent=1))
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
