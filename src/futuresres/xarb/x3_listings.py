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
    listing() if sys.argv[1:2] == ["list"] else (None if sys.argv[1:2] == ["hedged"] else gaps())


def kraken_minutes(base: str, t0: int, t1: int) -> dict:
    """minute start -> (VWAP, USD volume) of Kraken trades in [t0, t1)."""
    out, since = {}, t0
    for _ in range(40):
        time.sleep(1.1)
        try:
            r = get(f"https://api.kraken.com/0/public/Trades?pair={base.replace('BTC', 'XBT')}USD&since={since}")["result"]
        except Exception:
            break
        tr = next(v for k, v in r.items() if k != "last")
        for x in tr:
            ts = float(x[2])
            if t0 <= ts < t1:
                m = int(ts // 60 * 60); pv, v = out.get(m, (0.0, 0.0)); out[m] = (pv + float(x[0]) * float(x[1]), v + float(x[1]))
        if not tr or float(tr[-1][2]) >= t1:
            break
        since = r["last"]
    return {m: (pv / v, pv) for m, (pv, v) in out.items() if v > 0}


def hedged() -> None:
    """decisions.md 844."""
    rows = []
    for L in listing():
        day = dt.datetime.fromtimestamp(L["first_day"], dt.timezone.utc)
        c = []
        for k in range(5):
            c += candles(L["id"], day + dt.timedelta(minutes=300 * k), 60, 300)
        c = sorted(x for x in c if x[5] > 0)
        if not c:
            continue
        t_open = int(c[0][0]); first = [x for x in c if x[0] < t_open + 1800]
        K = kraken_minutes(L["base"], t_open, t_open + 1800)
        cap = 0.0; gaps_ = []
        for x in first:
            k = K.get(int(x[0]))
            if not k:
                continue
            g = x[4] / k[0] - 1 - FEES; gaps_.append(g)
            if g > 0:
                cap += min(0.1 * x[4] * x[5], 0.1 * k[1]) * g
        if gaps_:
            rows.append({**L, "open": dt.datetime.fromtimestamp(t_open, dt.timezone.utc).isoformat(), "minutes": len(gaps_), "median_gap": st.median(gaps_),
                         "max_gap": max(gaps_), "capturable_usd": cap})
            print(f"{L['base']:8} {rows[-1]['open'][:16]}: matched minutes {len(gaps_):2}, median net gap {st.median(gaps_)*100:+.1f}%, "
                  f"max {max(gaps_)*100:+.1f}%, capturable at 10% ${cap:,.0f}", flush=True)
    (ROOT / "reports" / "x3_hedged.json").write_text(json.dumps(rows, indent=0))
    for half, lo, hi in (("to 2025-12", "2025", "2026-01-01"), ("2026", "2026-01-01", "2027")):
        q = [r for r in rows if lo <= r["open"] < hi]
        if not q:
            continue
        t0 = min(r["open"] for r in q); t1 = max(r["open"] for r in q)
        months = max((dt.datetime.fromisoformat(t1) - dt.datetime.fromisoformat(t0)).days / 30.4, 1)
        tot = sum(r["capturable_usd"] for r in q)
        print(f"{half}: listings {len(q)}, capturable ${tot:,.0f} over {months:.1f} months = ${tot / months:,.0f}/month; "
              f"median per listing ${st.median(r['capturable_usd'] for r in q):,.0f}")


if __name__ == "__main__" and sys.argv[1:2] == ["hedged"]:
    hedged()
