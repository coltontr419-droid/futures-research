"""A95 (decisions.md 779): Kalshi BTC 15-minute markets in their averaging minute. Records only, no orders.

    python -m futuresres.kalshi.a95_btc15 record HOURS     # Coinbase ticker every second; Kalshi book top in each market's last 120 s
    python -m futuresres.kalshi.a95_btc15                  # analysis
"""

from __future__ import annotations

import datetime as dt
import json
import math
import statistics as st
import sys
import time
import urllib.request
from pathlib import Path

from futuresres.kalshi.k1_longshot import fee

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "kalshi" / "a95"
KB = "https://api.elections.kalshi.com/trade-api/v2"
UTC = dt.timezone.utc


def get(url: str) -> dict | None:
    try:
        return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=5).read())
    except Exception:
        return None


def record(hours: float) -> None:
    OUT.mkdir(parents=True, exist_ok=True); end = time.time() + hours * 3600
    f = open(OUT / f"{dt.datetime.now(UTC):%Y%m%dT%H%M}.jsonl", "a"); market = None
    while time.time() < end:
        t0 = time.time(); now = dt.datetime.now(UTC)
        cb = get("https://api.exchange.coinbase.com/products/BTC-USD/ticker")
        row = {"rcv": now.isoformat(), "cb_bid": float(cb["bid"]) if cb else None, "cb_ask": float(cb["ask"]) if cb else None}
        close = now.replace(second=0, microsecond=0) + dt.timedelta(minutes=15 - now.minute % 15)
        if (close - now).total_seconds() <= 120:
            if not market or market["close_time"] != close.strftime("%Y-%m-%dT%H:%M:%SZ"):
                ms = (get(f"{KB}/markets?series_ticker=KXBTC15M&status=open&limit=20") or {}).get("markets", [])
                market = next((m for m in ms if m["close_time"] == close.strftime("%Y-%m-%dT%H:%M:%SZ")), None)
            if market:
                ob = (get(f"{KB}/markets/{market['ticker']}/orderbook") or {}).get("orderbook_fp") or {}
                yes = sorted(((float(p), float(q)) for p, q in ob.get("yes_dollars") or []), reverse=True)
                no = sorted(((float(p), float(q)) for p, q in ob.get("no_dollars") or []), reverse=True)
                row.update(ticker=market["ticker"], strike=market.get("floor_strike"), close=market["close_time"], k_rcv=dt.datetime.now(UTC).isoformat(),
                           bid=yes[0] if yes else None, ask=[round(1 - no[0][0], 4), no[0][1]] if no else None)
        f.write(json.dumps(row) + "\n"); f.flush()
        time.sleep(max(0.0, 1.0 - (time.time() - t0)))


def analyse() -> dict:
    rows = [json.loads(l) for p in sorted(OUT.glob("*.jsonl")) for l in open(p)]
    for r in rows:
        r["t"] = dt.datetime.fromisoformat(r["rcv"]); r["mid"] = (r["cb_bid"] + r["cb_ask"]) / 2 if r["cb_bid"] else None
    pts = [(r["t"], r["mid"]) for r in rows if r["mid"]]
    res = []
    for tk in sorted({r["ticker"] for r in rows if r.get("ticker")}):
        mk = [r for r in rows if r.get("ticker") == tk and r.get("bid") and r.get("ask")]
        close = dt.datetime.fromisoformat(mk[0]["close"].replace("Z", "+00:00")); opn = close - dt.timedelta(minutes=15)
        o = [p for t, p in pts if opn - dt.timedelta(seconds=60) <= t < opn]
        hist = [p for t, p in pts if opn <= t < close - dt.timedelta(seconds=60)]
        if len(o) < 50 or len(hist) < 600 or mk[0]["strike"] is None:
            continue
        basis = st.mean(o) - float(mk[0]["strike"])                       # Coinbase proxy minus BRTI over the open minute
        rets = [math.log(b / a) for a, b in zip(hist, hist[1:])]; sig = st.pstdev(rets) * hist[-1]
        best = []
        for r in mk:
            k = (close - r["t"]).total_seconds()
            if not 0 < k <= 60:
                continue
            known = [p for t, p in pts if close - dt.timedelta(seconds=60) <= t <= r["t"]]
            if not known:
                continue
            mean = (st.mean(known) * (60 - k) + r["mid"] * k) / 60 - basis
            sd = sig * math.sqrt(k ** 3 / 3) / 60
            fair = 0.5 * (1 + math.erf((mean - float(r["strike"])) / (sd * math.sqrt(2)))) if sd > 0 else float(mean >= float(r["strike"]))
            (bp, bq), (ap, aq) = r["bid"], r["ask"]
            buy = fair - ap - fee(ap); sell = bp - fair - fee(bp)
            best.append((max(buy, sell), (aq * ap) if buy >= sell else (bq * bp), k, fair, bp, ap))
        if best:
            b = max(best, key=lambda x: x[0]); ok = [x for x in best if x[0] >= 0.02 and x[1] >= 100]
            res.append({"ticker": tk, "best_edge": b[0], "best_size_usd": b[1], "at_k": b[2], "fair": b[3], "book": b[4:], "seconds_with_2c_100usd": len(ok)})
    share = sum(r["seconds_with_2c_100usd"] > 0 for r in res) / max(len(res), 1)
    med = st.median([r["best_edge"] for r in res]) if res else float("nan")
    print(f"markets {len(res)}; median best edge {med*100:+.2f}c; markets with >= 2c on >= $100: {share:.0%}")
    for r in res:
        print(f"  {r['ticker']}: best {r['best_edge']*100:+.2f}c on ${r['best_size_usd']:,.0f} at {r['at_k']:.0f}s left (fair {r['fair']:.3f}, book {r['book']}); 2c/$100 seconds {r['seconds_with_2c_100usd']}")
    (ROOT / "reports" / "a95_btc15.json").write_text(json.dumps(res, indent=1) + "\n")
    return {"markets": len(res), "median_best": med, "share": share}


if __name__ == "__main__":
    if sys.argv[1:2] == ["record"]:
        record(float(sys.argv[2]))
    else:
        analyse()
