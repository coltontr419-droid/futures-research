"""A2: cross-series consistency on Kalshi — an "above K" market (INXU / NASDAQ100U / BTCD / ETHD) against the sum of the range
brackets (INX / NASDAQ100 / BTC / ETH) above K, same expiry. Riskless if: YES bid(above K) > sum of bracket YES asks above K + fees
(sell the threshold, buy the brackets), or sum of bracket YES bids above K > YES ask(above K) + fees (the reverse). Top of book.

    python -m futuresres.arb.a2_cross
"""

from __future__ import annotations

import collections
import datetime as dt
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "8")
from kalshi_api import Client  # noqa: E402

PAIRS = [("KXINXU", "KXINX"), ("KXNASDAQ100U", "KXNASDAQ100"), ("KXBTCD", "KXBTC"), ("KXETHD", "KXETH")]


def fee(p):
    return math.ceil(7 * p * (1 - p)) / 100


def markets(c, s):
    out, cur = [], None
    for _ in range(20):
        d = c.req("GET", f"/markets?series_ticker={s}&status=open&limit=1000" + (f"&cursor={cur}" if cur else ""))
        out += d.get("markets", []); cur = d.get("cursor")
        if not cur or not d.get("markets"):
            return out
    return out


def f(m, k):
    v = m.get(f"{k}_dollars")
    return float(v) if v not in (None, "") else None


def main() -> int:
    c = Client(); found = 0; checked = 0
    for up, rng in PAIRS:
        U = collections.defaultdict(list); R = collections.defaultdict(list)
        for m in markets(c, up):
            if m.get("strike_type") == "greater" and m.get("floor_strike") is not None:
                U[m["close_time"]].append(m)
        for m in markets(c, rng):
            if m.get("strike_type") == "between" and m.get("floor_strike") is not None and m.get("cap_strike") is not None:
                R[m["close_time"]].append(m)
            elif m.get("strike_type") == "greater" and m.get("floor_strike") is not None:      # the open-ended top bracket
                R[m["close_time"]].append({**m, "cap_strike": 1e18})
        for close, ums in U.items():
            br = sorted(R.get(close, []), key=lambda m: float(m["floor_strike"]))
            if not br:
                continue
            for u in ums:
                K = float(u["floor_strike"])
                above = [b for b in br if float(b["floor_strike"]) >= K - 1e-9]
                # brackets must tile (K, inf) exactly: the first starts at K, each next starts where the last ended
                if not above or abs(float(above[0]["floor_strike"]) - K) > 0.02 * max(1, abs(K)) / 100:
                    continue
                checked += 1
                ub, ua = f(u, "yes_bid"), f(u, "yes_ask")
                asks = [f(b, "yes_ask") for b in above]; bids = [f(b, "yes_bid") for b in above]
                if ub and all(a for a in asks):
                    e = ub - sum(asks) - fee(1 - ub) - sum(fee(a) for a in asks)
                    if e > 0:
                        found += 1; print(f"  SELL {u['ticker']} bid {ub} vs {len(asks)} brackets asks sum {sum(asks):.3f}: edge {e:+.3f}")
                if ua and all(b is not None for b in bids):
                    e = sum(bids) - ua - fee(ua) - sum(fee(1 - b) for b in bids if b)
                    if e > 0:
                        found += 1; print(f"  BUY  {u['ticker']} ask {ua} vs {len(bids)} brackets bids sum {sum(bids):.3f}: edge {e:+.3f}")
    print(f"{dt.datetime.now(dt.timezone.utc):%H:%M}Z threshold markets checked against their brackets: {checked}; riskless gaps after fees: {found}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
