"""BTC-USD hourly candles from Coinbase's public API (free), 2018 -> today; data/crypto/btc_1h.npz (decisions.md 684)."""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "crypto" / "btc_1h.npz"


def main() -> None:
    rows = {}; t = dt.datetime(2018, 1, 1, tzinfo=dt.timezone.utc); end = dt.datetime.now(dt.timezone.utc)
    while t < end:
        t2 = min(t + dt.timedelta(hours=300), end)
        u = f"https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=3600&start={t.isoformat()}&end={t2.isoformat()}"
        for k in range(5):
            try:
                d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "futures-research"}), timeout=30).read()); break
            except Exception:
                time.sleep(2 * (k + 1)); d = []
        for ts, lo, hi, op, cl, vol in d:
            rows[int(ts)] = (op, hi, lo, cl)
        t = t2; time.sleep(0.35)
    ts = np.array(sorted(rows)); v = np.array([rows[x] for x in ts], float)
    np.savez(OUT, ts=ts, o=v[:, 0], h=v[:, 1], l=v[:, 2], c=v[:, 3])
    print(len(ts), "hours", dt.datetime.fromtimestamp(ts[0], dt.timezone.utc), "->", dt.datetime.fromtimestamp(ts[-1], dt.timezone.utc))


if __name__ == "__main__":
    main()
