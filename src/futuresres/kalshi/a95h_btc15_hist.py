"""A95h (decisions.md 779, descriptive supplement): Kalshi BTC 15-minute markets' last-minute TRADES against a fair value rebuilt
from Coinbase trade history. Outcome-free except the proxy check against Kalshi's own expiration_value.

For each recently settled KXBTC15M market with real last-minute trading: Coinbase BTC-USD trades over the open minute and the last
two minutes (paged back by trade id), per-second last price as the BRTI proxy, per-second sigma from 1-minute candles, basis =
proxy open-minute mean − floor_strike. Each Kalshi trade in the last 60 s is scored: taker edge = fair − price (YES taker) or
price − fair (NO taker), minus the taker fee.

    python -m futuresres.kalshi.a95h_btc15_hist [N_MARKETS]
"""

from __future__ import annotations

import bisect
import datetime as dt
import json
import math
import statistics as st
import sys
import time
import urllib.request
from pathlib import Path

from futuresres.kalshi.download import get
from futuresres.kalshi.k1_longshot import fee

ROOT = Path(__file__).resolve().parents[3]
CB = "https://api.exchange.coinbase.com/products/BTC-USD"
UTC = dt.timezone.utc


def T(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def cb(path: str):
    for k in range(5):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(CB + path, headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read())
        except Exception:
            time.sleep(1 + k)
    return []


class Trades:
    """Coinbase trades by time, located by interpolating on trade id."""

    def __init__(self):
        top = cb("/trades?limit=1")[0]; self.ref = (int(top["trade_id"]), T(top["time"]))

    def window(self, t0: dt.datetime, t1: dt.datetime) -> list[tuple[dt.datetime, float]]:
        tid, tt = self.ref; guess = int(tid - (tt - t1).total_seconds() * 6.6) + 200
        for _ in range(15):                                     # a page (ids <= guess, newest first) whose newest trade is just past t1
            page = cb(f"/trades?limit=1000&after={guess + 1}")
            if not page:
                return []
            newest, oldest = T(page[0]["time"]), T(page[-1]["time"])
            rate = max(1.0, len(page) / max((newest - oldest).total_seconds(), 1))
            if newest < t1:
                guess += int((t1 - newest).total_seconds() * rate) + 50
            elif (newest - t1).total_seconds() > 30:
                guess -= int((newest - t1).total_seconds() * rate) - 50
            else:
                break
        out, after = [], guess + 1
        for _ in range(40):
            page = cb(f"/trades?limit=1000&after={after}")
            if not page:
                break
            out += [(T(x["time"]), float(x["price"])) for x in page]
            if T(page[-1]["time"]) < t0:
                break
            after = int(page[-1]["trade_id"])
        return sorted(p for p in out if t0 <= p[0] <= t1)


def per_second(tr, t0, t1):
    """Last trade price at each whole second in [t0, t1)."""
    ts = [t for t, _ in tr]; out = []
    for i in range(int((t1 - t0).total_seconds())):
        s = t0 + dt.timedelta(seconds=i + 1); j = bisect.bisect_right(ts, s) - 1
        out.append(tr[j][1] if j >= 0 else None)
    return out


def main(argv) -> int:
    n = int(argv[0]) if argv else 40
    ms = get("/markets?series_ticker=KXBTC15M&status=settled&limit=200")["markets"]; trd = Trades(); res = []
    for m in ms:
        if len(res) >= n:
            break
        close = T(m["close_time"]); opn = close - dt.timedelta(minutes=15)
        kt = []; cur = None
        for _ in range(30):
            d = get(f"/markets/trades?ticker={m['ticker']}&limit=1000&min_ts={int(close.timestamp()) - 60}" + (f"&cursor={cur}" if cur else ""))
            kt += d.get("trades", []); cur = d.get("cursor")
            if not cur or not d.get("trades"):
                break
        kt = [x for x in kt if T(x["created_time"]) >= close - dt.timedelta(seconds=60)]
        risk = sum(float(x["count_fp"]) * min(float(x["yes_price_dollars"]), 1 - float(x["yes_price_dollars"])) for x in kt)
        if risk < 1000:
            continue                                            # decided before the last minute
        o = [p for p in per_second(trd.window(opn - dt.timedelta(seconds=61), opn), opn - dt.timedelta(seconds=60), opn) if p]
        last = trd.window(close - dt.timedelta(seconds=121), close)
        if len(o) < 50 or len(last) < 50:
            continue
        sec = per_second(last, close - dt.timedelta(seconds=60), close)
        candles = cb(f"/candles?granularity=60&start={opn.isoformat()}&end={close.isoformat()}")
        closes = [c[4] for c in sorted(candles)]
        if len(closes) < 10:
            continue
        sig = st.pstdev([math.log(b / a) for a, b in zip(closes, closes[1:])]) / math.sqrt(60) * closes[-1]
        basis = st.mean(o) - float(m["floor_strike"]); strike = float(m["floor_strike"])
        proxy_final = st.mean([p for p in sec if p]) - basis
        tot = 0.0; big = 0; edges = []
        for x in kt:
            t = T(x["created_time"]); k = (close - t).total_seconds(); i = 60 - int(math.ceil(k))
            known = [p for p in sec[:max(i, 0)] if p]; now_p = next((p for tt, p in reversed(last) if tt <= t), None)
            if now_p is None:
                continue
            mean = ((st.mean(known) if known else now_p) * (60 - k) + now_p * k) / 60 - basis
            sd = sig * math.sqrt(max(k, 0.5) ** 3 / 3) / 60
            fair = 0.5 * (1 + math.erf((mean - strike) / (sd * math.sqrt(2))))
            p = float(x["yes_price_dollars"]); q = float(x["count_fp"])
            e = (fair - p - fee(p)) if x["taker_side"] == "yes" else (p - fair - fee(1 - p))
            tot += e * q * (1 if e > 0 else 1); edges.append(e)
            big += abs(fair - p) > 0.03
        res.append({"ticker": m["ticker"], "result": m["result"], "last_minute_risk": risk, "proxy_err_usd": proxy_final - float(m.get("expiration_value") or proxy_final),
                    "takers_net_usd": tot, "trades": len(kt), "share_off_fair_3c": big / max(len(kt), 1),
                    "median_taker_edge_c": st.median(edges) * 100 if edges else None})
        r = res[-1]
        print(f"{r['ticker']} {r['result']}: last-min risk ${risk:,.0f}, proxy err ${r['proxy_err_usd']:+.1f}, takers net ${tot:+,.0f} on {len(kt)} trades, "
              f"{r['share_off_fair_3c']:.0%} > 3c off fair, median taker edge {r['median_taker_edge_c']:+.2f}c", flush=True)
    (ROOT / "reports" / "a95h_btc15_hist.json").write_text(json.dumps(res, indent=1) + "\n")
    if res:
        print(f"markets {len(res)}; takers' net value median ${st.median([r['takers_net_usd'] for r in res]):,.0f}, total ${sum(r['takers_net_usd'] for r in res):,.0f}; "
              f"proxy |err| median ${st.median([abs(r['proxy_err_usd']) for r in res]):.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
