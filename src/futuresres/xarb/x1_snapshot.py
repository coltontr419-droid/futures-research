"""X1: cross-exchange crypto top-of-book snapshot (US KYC'd venues, public endpoints, no key). Screen only — no money.

    python -m futuresres.xarb.x1_snapshot
"""

from __future__ import annotations

import json
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}
TAKER = {"kraken": 0.0040, "coinbase": 0.0120, "gemini": 0.0040, "binanceus": 0.0060, "bitstamp": 0.0040, "cryptocom": 0.0050}  # base tiers (approx.)


def get(u: str):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read())


def kraken() -> dict:
    pairs = get("https://api.kraken.com/0/public/AssetPairs")["result"]; out = {}
    m = {k: v["wsname"] for k, v in pairs.items() if v.get("wsname", "").endswith("/USD")}
    t = get("https://api.kraken.com/0/public/Ticker")["result"]
    for k, v in t.items():
        if k in m:
            out[m[k].split("/")[0].replace("XBT", "BTC").replace("XDG", "DOGE")] = (float(v["b"][0]), float(v["a"][0]), float(v["v"][1]) * float(v["c"][0]))
    return out


def coinbase() -> dict:
    out = {}
    for p in get("https://api.exchange.coinbase.com/products"):
        if p["quote_currency"] == "USD" and p["status"] == "online":
            out[p["base_currency"]] = p["id"]
    return out


def gemini() -> dict:
    out = {}
    for d in get("https://api.gemini.com/v1/pricefeed"):
        pass
    return out


def binanceus() -> dict:
    out = {}
    for x in get("https://api.binance.us/api/v3/ticker/24hr"):
        s = x["symbol"]
        if s.endswith("USD") and not s.endswith("BUSD"):
            b, a = float(x["bidPrice"]), float(x["askPrice"])
            if b > 0 and a > 0:
                out[s[:-3]] = (b, a, float(x["quoteVolume"]))
    return out


def bitstamp() -> dict:
    out = {}
    for x in get("https://www.bitstamp.net/api/v2/ticker/"):
        p = x.get("pair", "")
        if p.endswith("/USD") and x.get("bid") and x.get("ask"):
            out[p.split("/")[0]] = (float(x["bid"]), float(x["ask"]), float(x["volume"]) * float(x["last"]))
    return out


def cryptocom() -> dict:
    out = {}
    for x in get("https://api.crypto.com/exchange/v1/public/get-tickers")["result"]["data"]:
        i = x["i"]
        if i.endswith("_USD") and x.get("b") and x.get("k"):
            out[i[:-4]] = (float(x["b"]), float(x["k"]), float(x.get("vv") or 0))
    return out


def gemini_books() -> dict:
    out = {}
    syms = [s for s in get("https://api.gemini.com/v1/symbols") if s.endswith("usd") and len(s) <= 10]
    for s in syms:
        try:
            t = get(f"https://api.gemini.com/v2/ticker/{s}")
            out[s[:-3].upper()] = (float(t["bid"]), float(t["ask"]), 0.0)
        except Exception:
            pass
    return out


def main() -> int:
    V = {}
    for name, fn in (("kraken", kraken), ("binanceus", binanceus), ("bitstamp", bitstamp), ("cryptocom", cryptocom), ("gemini", gemini_books)):
        try:
            V[name] = fn(); print(name, len(V[name]), file=sys.stderr)
        except Exception as e:
            print(name, "failed", repr(e)[:120], file=sys.stderr)
    rows = []
    coins = set().union(*V.values())
    for c in coins:
        q = {v: V[v][c] for v in V if c in V[v] and V[v][c][0] > 0 and V[v][c][1] > 0}
        for buy, (_, ask, _) in q.items():
            for sell, (bid, _, _) in q.items():
                if buy != sell:
                    net = bid / ask - 1 - TAKER[buy] - TAKER[sell]
                    if net > 0:
                        rows.append((net, c, buy, ask, sell, bid))
    rows.sort(reverse=True)
    print(f"coins {len(coins)}; crossed after base-tier taker fees: {len(rows)}")
    for r in rows[:30]:
        print(f"  {r[1]:8} buy {r[2]:9} @ {r[3]:.6g}  sell {r[4]:9} @ {r[5]:.6g}  net {r[0]*100:+.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
