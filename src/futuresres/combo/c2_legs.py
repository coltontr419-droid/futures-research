"""C-family 1 (decisions.md 742): price executed Kalshi combos from their legs (independent-leg product of leg mids at the last 1-minute
candle before the combo opened); markup, calibration of the product, and a 1.15x quoter's P&L. Descriptive; no trial.

    python -m futuresres.combo.c2_legs [per_band]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import math
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "5")
from kalshi_api import Client  # noqa: E402

SERIES = ["KXMVESPORTSMULTIGAMEEXTENDED", "KXMVECROSSCATEGORY"]
OUT = ROOT / "data" / "kalshi" / "combo"
BANDS = [(.02, .05), (.05, .10), (.10, .20), (.20, .35), (.35, .65), (.65, .95)]


def T(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def sample(c: Client, per_band: int) -> list[dict]:
    f = OUT / "c2_sample.json"
    if f.exists():
        return json.loads(f.read_text())
    pool = []
    for s in SERIES:
        cur = None
        for _ in range(8):
            d = c.req("GET", f"/markets?series_ticker={s}&status=settled&limit=1000" + (f"&cursor={cur}" if cur else ""))
            for m in d.get("markets", []):
                legs = m.get("mve_selected_legs") or []; lp = m.get("last_price_dollars"); v = float(m.get("volume_fp") or 0)
                if m.get("result") in ("yes", "no") and lp and v > 0 and 2 <= len(legs) <= 6 and len({l["event_ticker"] for l in legs}) == len(legs):
                    pool.append({"ticker": m["ticker"], "series": s, "p": float(lp), "v": v, "y": m["result"] == "yes", "open": m["open_time"], "legs": legs})
            cur = d.get("cursor")
            if not cur or not d.get("markets"):
                break
    random.seed(742); out = []
    for lo, hi in BANDS:
        b = [x for x in pool if lo <= x["p"] < hi]; out += random.sample(b, min(per_band, len(b)))
    f.write_text(json.dumps(out)); print("pool", len(pool), "sample", len(out), flush=True)
    return out


def leg_mid(c: Client, leg: dict, at: dt.datetime, cache: dict):
    key = (leg["market_ticker"], int(at.timestamp()) // 60)
    if key in cache:
        return cache[key]
    s = leg["event_ticker"].split("-")[0]; t = int(at.timestamp())
    try:
        d = c.req("GET", f"/series/{s}/markets/{leg['market_ticker']}/candlesticks?start_ts={t - 1800}&end_ts={t}&period_interval=1")
    except Exception:
        cache[key] = None; return None
    cs = [x for x in d.get("candlesticks", []) if t - 300 <= x["end_period_ts"] <= t]     # a quote at most 5 minutes old
    mid = None
    for cd in reversed(cs):
        yb, ya = cd.get("yes_bid", {}).get("close_dollars"), cd.get("yes_ask", {}).get("close_dollars")
        if yb is not None and ya is not None and 0 < float(yb) < float(ya) < 1 and float(ya) - float(yb) <= 0.10:   # a real two-sided quote
            mid = (float(yb) + float(ya)) / 2; break
    if mid is not None and leg.get("side") == "no":
        mid = 1 - mid
    cache[key] = mid
    return mid


def fee(p):
    return math.ceil(7 * p * (1 - p)) / 100


def main(argv) -> int:
    c = Client(); OUT.mkdir(parents=True, exist_ok=True); S = sample(c, int(argv[0]) if argv else 250)
    cf = OUT / "c2_legcache_v2.json"; cache = {tuple(json.loads(k)): v for k, v in json.loads(cf.read_text()).items()} if cf.exists() else {}
    rows = []
    for i, x in enumerate(S):
        at = T(x["open"]); mids = [leg_mid(c, l, at, cache) for l in x["legs"]]
        if any(m is None for m in mids):
            continue
        rows.append({**x, "fair": math.prod(mids)})
        if i % 100 == 0:
            cf.write_text(json.dumps({json.dumps(list(k)): v for k, v in cache.items()})); print(i, len(rows), flush=True)
    cf.write_text(json.dumps({json.dumps(list(k)): v for k, v in cache.items()}))
    (ROOT / "reports" / "c2_legs.json").write_text(json.dumps(rows) + "\n")
    print(f"\npriced {len(rows)} of {len(S)} sampled combos (all legs had a live quote)")
    for lo, hi in BANDS:
        b = [r for r in rows if lo <= r["p"] < hi]
        if not b:
            continue
        V = sum(r["v"] for r in b)
        ex = sum(r["v"] * r["p"] for r in b) / V; fa = sum(r["v"] * r["fair"] for r in b) / V; y = sum(r["v"] * r["y"] for r in b) / V
        q = [(max(r["fair"] * 1.15, r["fair"] + 0.01), r) for r in b]
        won = [(qq, r) for qq, r in q if qq < r["p"]]
        pnl = sum(r["v"] * (qq - r["y"]) for qq, r in won); pnl_fee = sum(r["v"] * (qq - r["y"] - fee(qq)) for qq, r in won)
        print(f"price {lo:.2f}-{hi:.2f}: n {len(b):3} | executed {ex:.3f} vs leg-product fair {fa:.3f} (markup x{ex/max(fa,1e-9):.2f}) | YES rate {y:.3f} "
              f"(fair {'over' if fa > y else 'under'}-predicts by {abs(fa-y):.3f}) | 1.15x quoter wins {len(won)}/{len(b)}: P&L ${pnl:,.0f} (after a taker-size fee ${pnl_fee:,.0f}) on {sum(r['v'] for _, r in won):,.0f} contracts")
    allw = [(max(r["fair"] * 1.15, r["fair"] + 0.01), r) for r in rows]; allw = [(qq, r) for qq, r in allw if qq < r["p"]]
    print(f"ALL: 1.15x quoter P&L ${sum(r['v']*(qq-r['y']) for qq, r in allw):,.0f} on {sum(r['v'] for _, r in allw):,.0f} contracts "
          f"(premium ${sum(r['v']*qq for qq, r in allw):,.0f}); with fee ${sum(r['v']*(qq-r['y']-fee(qq)) for qq, r in allw):,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
