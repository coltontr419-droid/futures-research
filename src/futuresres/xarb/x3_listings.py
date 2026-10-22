"""X3: Coinbase new listings of assets already on Kraken — does Coinbase's opening trade above Kraken by more than both fees?
Screen (public candles/trades, no key, no money).

    python -m futuresres.xarb.x3_listings list
    python -m futuresres.xarb.x3_listings           # gaps
"""

from __future__ import annotations

import datetime as dt
import json
import statistics as st
import sys
import time
from pathlib import Path

from futuresres.xarb.x1_snapshot import get, kraken

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "xarb" / "x3"
CB = "https://api.exchange.coinbase.com"
FEES = 0.012 + 0.004          # Coinbase base taker + Kraken base taker (both sides taker; conservative)


def candles(pid: str, start: dt.datetime, gran: int, n: int = 300) -> list:
    end = start + dt.timedelta(seconds=gran * n)
    time.sleep(0.35)
    try:
        return sorted(get(f"{CB}/products/{pid}/candles?granularity={gran}&start={start.isoformat()}&end={end.isoformat()}"))
    except Exception:
        return []


def listing() -> list[dict]:
    DIR.mkdir(parents=True, exist_ok=True); f = DIR / "listings.json"
    if f.exists():
        return json.loads(f.read_text())
    kr = kraken(); out = []
    prods = [p for p in get(f"{CB}/products") if p["quote_currency"] == "USD" and p["base_currency"] in kr]
    t0 = dt.datetime(2025, 3, 1, tzinfo=dt.timezone.utc)
    for p in prods:
        first = None; s = t0
        while s < dt.datetime.now(dt.timezone.utc):
            c = candles(p["id"], s, 86400)
            if c:
                first = c[0][0]; break
            s += dt.timedelta(days=300)
        if first and first > t0.timestamp() + 5 * 86400:
            out.append({"id": p["id"], "base": p["base_currency"], "first_day": first})
    f.write_text(json.dumps(out)); print("new Coinbase listings (on Kraken too):", len(out)); return out


def kraken_price(base: str, ts: int) -> float | None:
    time.sleep(1.1)
    try:
        r = get(f"https://api.kraken.com/0/public/Trades?pair={base.replace('BTC', 'XBT')}USD&since={ts - 900}")["result"]
        tr = next(v for k, v in r.items() if k != "last")
        px = [float(x[0]) for x in tr if ts - 900 <= float(x[2]) <= ts]
        return px[-1] if px else None
    except Exception:
        return None


def gaps() -> None:
    rows = []
    for L in listing():
        day = dt.datetime.fromtimestamp(L["first_day"], dt.timezone.utc)
        c = [x for x in candles(L["id"], day, 60, 300) + candles(L["id"], day + dt.timedelta(minutes=300), 60, 300) + candles(L["id"], day + dt.timedelta(minutes=600), 60, 300) + candles(L["id"], day + dt.timedelta(minutes=900), 60, 300) + candles(L["id"], day + dt.timedelta(minutes=1200), 60, 240) if x[5] > 0]
        if not c:
            continue
        t_open = c[0][0]; first30 = [x for x in c if x[0] < t_open + 1800]
        vwap = sum(x[4] * x[5] for x in first30) / sum(x[5] for x in first30); usd = sum(x[4] * x[5] for x in first30)
        k = kraken_price(L["base"], t_open)
        if not k:
            continue
        g = vwap / k - 1 - FEES
        rows.append({**L, "open": dt.datetime.fromtimestamp(t_open, dt.timezone.utc).isoformat(), "cb_vwap30": vwap, "kraken": k, "net_gap": g, "cb_usd_30min": usd})
        print(f"{L['base']:8} {rows[-1]['open'][:16]} Coinbase 30-min VWAP {vwap:.6g} vs Kraken {k:.6g}: net {g*100:+.1f}% on ${usd:,.0f} traded", flush=True)
    if rows:
        print(f"listings {len(rows)}, median net {st.median(r['net_gap'] for r in rows)*100:+.1f}%, positive {sum(r['net_gap'] > 0 for r in rows)}")
    (ROOT / "reports" / "x3_listings.json").write_text(json.dumps(rows, indent=0))


if __name__ == "__main__":
    listing() if sys.argv[1:2] == ["list"] else gaps()
