"""A1: a snapshot scan of every open Kalshi event for riskless structural arbitrage at the top of book, net of taker fees.
(1) Mutually exclusive events: sum of YES bids > 1 -> buy NO on every market (at most one resolves YES); payout >= n - 1.
(2) Threshold ladders ("above K" in one event): YES ask at a lower K below the YES bid at a higher K -> buy YES(low) + NO(high).

    python -m futuresres.arb.a1_scan
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "8")
from kalshi_api import Client  # noqa: E402

OUT = ROOT / "data" / "kalshi" / "arb"


def fee(p: float) -> float:
    return math.ceil(7 * p * (1 - p)) / 100        # per contract at price p (1-lot, rounded up: conservative)


def events(c: Client) -> list[dict]:
    out, cur = [], None
    for _ in range(400):
        for attempt in range(5):
            try:
                d = c.req("GET", "/events?status=open&with_nested_markets=true&mve_filter=exclude&limit=200" + (f"&cursor={cur}" if cur else "")); break
            except Exception:                                              # noqa: BLE001  (dropped connections are not retried by req)
                import time; time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError("events page failed 5 times")
        out += d.get("events", []); cur = d.get("cursor")
        if not cur or not d.get("events"):
            return out
    return out


def px(m: dict, k: str):
    v = m.get(f"{k}_dollars")
    return float(v) if v not in (None, "") else None


def main() -> int:
    c = Client(); OUT.mkdir(parents=True, exist_ok=True); evs = events(c); now = dt.datetime.now(dt.timezone.utc)
    ex, lad = [], []
    for e in evs:
        ms = [m for m in e.get("markets", []) if m.get("status") == "active"]
        if len(ms) < 2:
            continue
        if e.get("mutually_exclusive") and all(m.get("close_time") and dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")) > now for m in ms):
            bids = [px(m, "yes_bid") for m in ms]
            if all(b is not None for b in bids):
                edge = sum(bids) - 1 - sum(fee(1 - b) for b in bids)
                if edge > 0:
                    ex.append({"event": e["event_ticker"], "n": len(ms), "sum_bids": round(sum(bids), 3), "edge_per_set": round(edge, 4),
                               "title": e.get("title", "")[:70]})
        live = [m for m in ms if m.get("close_time") and dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")) > now]
        # a ladder is one side of one quantity: same ticker stem (e.g. "...-SMU3", "...-SMU5"), never the opposite team's markets
        stems = collections.defaultdict(list)
        for m in live:
            if m.get("strike_type") == "greater" and m.get("floor_strike") is not None:
                stems[re.sub(r"-?[\d.]+$", "", m["ticker"])].append(m)     # "...-GSKTHORNTON5-10" -> "...-GSKTHORNTON5"; "...-SMU3" -> "...-SMU"
        pairs = []
        for g in stems.values():
            g.sort(key=lambda m: float(m["floor_strike"])); pairs += [(a, b) for i, a in enumerate(g) for b in g[i + 1:]]
        for lo, hi in pairs:
            a, b = px(lo, "yes_ask"), px(hi, "yes_bid")
            if a is None or b is None or a <= 0 or b <= 0:
                continue
            edge = b - a - fee(a) - fee(1 - b)
            if edge > 0:
                lad.append({"event": e["event_ticker"], "low": lo["ticker"], "high": hi["ticker"], "ask_low": a, "bid_high": b, "edge": round(edge, 4)})
    res = {"ts": now.isoformat(), "events": len(evs), "mutually_exclusive_arbs": ex, "ladder_arbs": lad}
    (OUT / f"scan_{now:%Y%m%dT%H%M}.json").write_text(json.dumps(res, indent=1))
    print(f"{now:%H:%M}Z events {len(evs)} | mutually-exclusive arbs {len(ex)} | ladder arbs {len(lad)}")
    for x in sorted(ex, key=lambda x: -x["edge_per_set"])[:10]:
        print("  ME ", x)
    for x in sorted(lad, key=lambda x: -x["edge"])[:10]:
        print("  LAD", x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
