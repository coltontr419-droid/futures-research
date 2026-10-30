"""Keep the Synth forecast caches warm (decisions.md §1189): Binance 1-minute closes for BTC/ETH/SOL/XRP, Hyperliquid 5-minute and 1-hour candles for
the Hyperliquid assets, Yahoo's 60-day profile for XAU. A cold cache costs ≈ 75 s on the first request, longer than a validator waits."""

import sys
import time

sys.path.insert(0, "/opt/synth/ours/src")

import futuresres.synth.miner_model as mm  # noqa: E402
import futuresres.synth.s50_backtest as b24  # noqa: E402

while True:
    t = time.time()
    for a in ("BTC", "ETH", "SOL", "XRP"):
        try:
            mm._binance_minutes(a, 32)
        except Exception as e:
            print("binance", a, type(e).__name__, e, flush=True)
    for a in b24.HYPERLIQUID:
        try:
            b24.hl5(a)
        except Exception as e:
            print("hl5", a, type(e).__name__, e, flush=True)
    for a in mm.MODEL_24H_YP:
        try:
            b24.hl1h(a); b24.yahoo5(a)
        except Exception as e:
            print("profile", a, type(e).__name__, e, flush=True)
    print(f"caches warm in {time.time() - t:.0f}s", flush=True)
    time.sleep(max(60, 240 - (time.time() - t)))
