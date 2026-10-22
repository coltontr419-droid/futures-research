"""X2: record crossed cross-exchange crypto books every ~60 s with top-of-book depth; dollars capturable after base-tier taker fees.
Screen only — no money. Symbol collisions (venue prices > 1.5x apart) dropped.

    python -m futuresres.xarb.x2_record record HOURS
    python -m futuresres.xarb.x2_record                # readout
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
import time
from pathlib import Path

from futuresres.xarb.x1_snapshot import TAKER, binanceus, bitstamp, cryptocom, get, gemini_books, kraken

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "xarb" / "x2.jsonl"


def top(venue: str, coin: str) -> tuple[float, float, float, float] | None:
    """(bid, bid_qty, ask, ask_qty)."""
    try:
        if venue == "kraken":
            r = get(f"https://api.kraken.com/0/public/Depth?pair={coin.replace('BTC', 'XBT')}USD&count=1")["result"]; d = next(iter(r.values()))
            return float(d["bids"][0][0]), float(d["bids"][0][1]), float(d["asks"][0][0]), float(d["asks"][0][1])
        if venue == "binanceus":
            d = get(f"https://api.binance.us/api/v3/depth?symbol={coin}USD&limit=5")
        elif venue == "bitstamp":
            d = get(f"https://www.bitstamp.net/api/v2/order_book/{coin.lower()}usd/")
        elif venue == "gemini":
            d = get(f"https://api.gemini.com/v1/book/{coin.lower()}usd?limit_bids=1&limit_asks=1")
            return float(d["bids"][0]["price"]), float(d["bids"][0]["amount"]), float(d["asks"][0]["price"]), float(d["asks"][0]["amount"])
        elif venue == "cryptocom":
            d = get(f"https://api.crypto.com/exchange/v1/public/get-book?instrument_name={coin}_USD&depth=1")["result"]["data"][0]
        return float(d["bids"][0][0]), float(d["bids"][0][1]), float(d["asks"][0][0]), float(d["asks"][0][1])
    except Exception:
        return None


def sweep() -> list[dict]:
    V = {}
    for name, fn in (("kraken", kraken), ("binanceus", binanceus), ("bitstamp", bitstamp), ("cryptocom", cryptocom), ("gemini", gemini_books)):
        try:
            V[name] = fn()
        except Exception:
            pass
    out = []
    for c in set().union(*V.values()):
        q = {v: V[v][c] for v in V if c in V[v] and V[v][c][0] > 0 and V[v][c][1] > 0}
        for buy, (_, ask, _) in q.items():
            for sell, (bid, _, _) in q.items():
                if buy != sell and bid / ask - 1 - TAKER[buy] - TAKER[sell] > 0 and bid / ask < 1.5:
                    a, b = top(buy, c), top(sell, c)
                    if a and b:
                        px_a, qa = a[2], a[3]; px_b, qb = b[0], b[1]
                        net = px_b / px_a - 1 - TAKER[buy] - TAKER[sell]
                        out.append({"coin": c, "buy": buy, "sell": sell, "ask": px_a, "bid": px_b, "net": net, "usd_top": min(qa * px_a, qb * px_b),
                                    "profit_top": max(net, 0) * min(qa * px_a, qb * px_b)})
    return out


def record(hours: float) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True); end = time.time() + hours * 3600
    while time.time() < end:
        t0 = time.time()
        try:
            rows = sweep()
        except Exception as e:
            rows = []; print("error", repr(e)[:100], flush=True)
        with open(OUT, "a") as f:
            f.write(json.dumps({"t": dt.datetime.now(dt.timezone.utc).isoformat(), "rows": rows}) + "\n")
        time.sleep(max(5, 60 - (time.time() - t0)))


def readout() -> None:
    S = [json.loads(l) for l in open(OUT)]; hrs = (dt.datetime.fromisoformat(S[-1]["t"]) - dt.datetime.fromisoformat(S[0]["t"])).total_seconds() / 3600
    by = collections.defaultdict(lambda: [0, 0.0, 0.0]); prev = set(); episodes = 0; ep_profit = 0.0
    for s in S:
        cur = set()
        for r in s["rows"]:
            if r["net"] <= 0:
                continue
            k = (r["coin"], r["buy"], r["sell"]); cur.add(k); by[k][0] += 1; by[k][1] = max(by[k][1], r["net"]); by[k][2] += r["profit_top"]
            if k not in prev:
                episodes += 1; ep_profit += r["profit_top"]
        prev = cur
    print(f"sweeps {len(S)} over {hrs:.1f} h; new crossed episodes {episodes}; top-of-book profit at episode starts ${ep_profit:,.2f} "
          f"(~${ep_profit / max(hrs, 1e-9) * 24:,.0f}/day)")
    for k, (n, mx, p) in sorted(by.items(), key=lambda x: -x[1][2])[:25]:
        print(f"  {k[0]:8} {k[1]:9} -> {k[2]:9}: sweeps crossed {n:4}, max net {mx*100:+.2f}%, sum top-of-book profit ${p:,.2f}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["record"]:
        record(float(sys.argv[2]))
    else:
        readout()
