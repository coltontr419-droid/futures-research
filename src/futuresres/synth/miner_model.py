"""SN50 (Synth) miner forecast: generate_simulations() for any validator prompt, using the variants that beat the median miner in the backtests
(decisions.md §1164-§1168). Live data: Binance's public market-data mirror (BTC/ETH/SOL/XRP, 1-minute) and Hyperliquid (HYPE and the
commodities/equities, 5-minute + 1-hour). Not deployed: a Synth miner would call this from its forward(); wallet, registration and the axon are the
user's (decisions.md §1168).

    python -m futuresres.synth.miner_model          # self-test: one forecast per asset and competition, checked against the validator's format rule
"""

from __future__ import annotations

import datetime as dt
import json
import math
import time

import numpy as np
from curl_cffi import requests

import futuresres.synth.s50_backtest as b24
import futuresres.synth.s50_1h as b1

LIVE = b24.CACHE / "live"
MODEL_24H_CRYPTO = ("todg_12_36_c_ou20", 0.95)
MODEL_24H_HL = ("todg_12_36_c_wk", 1.0)
MODEL_24H_YP = {"XAU": ("todg_12_36_c_yp", 1.0)}               # Yahoo 60-day weekday profile (decisions.md §1169)
MODEL_1H = ("tod1_120_240", 1.0)


def _binance_minutes(asset: str, days: int = 32) -> np.ndarray:
    """Last `days` of 1-minute closes ending with the last closed minute (cached and topped up)."""
    LIVE.mkdir(parents=True, exist_ok=True); f = LIVE / f"bnc_{asset}.json"
    have = {int(k): v for k, v in json.loads(f.read_text()).items()} if f.exists() else {}
    now = int(time.time() * 1000) // 60000 * 60000; start = now - days * 86400000
    t = max([start] + [k + 60000 for k in have if k >= start])
    while t < now - 60000:
        rows = requests.get("https://data-api.binance.vision/api/v3/klines", params={"symbol": b24.BINANCE[asset], "interval": "1m", "startTime": t, "limit": 1000},
                            timeout=30, impersonate="chrome").json()
        if not rows:
            break
        for k in rows:
            if int(k[6]) < now:                                   # closed candles only
                have[int(k[0])] = float(k[4])
        t = int(rows[-1][0]) + 60000
    have = {k: v for k, v in have.items() if k >= start}; f.write_text(json.dumps(have))
    return np.array([have[k] for k in sorted(have)])


def _round8(x: float) -> float:
    return float(f"{x:.7e}")


def generate_simulations(asset: str, start_time: str, time_increment: int, time_length: int, num_simulations: int = 1000, seed: int | None = None) -> tuple:
    """Validator format: (start unix, time_increment, path_1, ..., path_N), each path time_length / time_increment + 1 prices."""
    t0d = dt.datetime.fromisoformat(start_time.replace("Z", "+00:00")); t0d = t0d.replace(tzinfo=t0d.tzinfo or dt.timezone.utc); t0 = int(t0d.timestamp() * 1000)
    rng = np.random.default_rng(seed); steps = time_length // time_increment
    if time_length == 3600:                                       # Crypto-1h (1-minute steps)
        hist = _binance_minutes(asset, 32)[-31 * 1440:]
        paths = b1.ensemble(hist, float(hist[-1]), (t0 // 60000) % 1440, MODEL_1H[0], rng, MODEL_1H[1], n=num_simulations, steps=steps)
    elif asset in b24.HYPERLIQUID:                                # Com/Equ-24h and HYPE (5-minute Hyperliquid candles)
        M = b24.hl5(asset); keys = sorted(M); hist = np.array([M[k] for k in keys])[-6 * 288:]
        model, k = MODEL_24H_YP.get(asset, MODEL_24H_HL); hp = None
        if asset in MODEL_24H_YP:
            h = b24.hour_profile(b24.hl1h(asset), t0); hp = (h[0], h[1], b24.yahoo_profile(b24.yahoo5(asset), t0))
        paths = b24.ensemble(hist, float(hist[-1]), model, rng, n=num_simulations, steps=steps, slot0=(t0 // 300000) % 288, k=k,
                             stride=1, day0=t0d.weekday(), hprof=hp)
    else:                                                         # Crypto-24h
        hist = _binance_minutes(asset, 32)[-31 * 1440:]
        paths = b24.ensemble(hist, float(hist[-1]), MODEL_24H_CRYPTO[0], rng, n=num_simulations, steps=steps, slot0=(t0 // 300000) % 288, k=MODEL_24H_CRYPTO[1])
    return tuple([int(t0d.timestamp()), time_increment] + [[_round8(p) for p in row] for row in paths])


def _valid(pred: tuple, steps: int, n: int) -> bool:
    ok = len(pred) == n + 2 and all(len(r) == steps + 1 for r in pred[2:])
    return ok and all(math.isfinite(p) and p > 0 and float(f"{p:.7e}") == p for r in pred[2:3] for p in r)


if __name__ == "__main__":
    start = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)).replace(second=0, microsecond=0).isoformat()
    for asset, ti, tl in (("BTC", 300, 86400), ("ETH", 60, 3600), ("SP500", 300, 86400), ("XAU", 300, 86400)):
        t = time.time(); p = generate_simulations(asset, start, ti, tl, 1000, seed=1)
        print(asset, ti, tl, "paths", len(p) - 2, "points", len(p[2]), "valid", _valid(p, tl // ti, 1000), "start", p[2][0], f"{time.time() - t:.1f}s")
