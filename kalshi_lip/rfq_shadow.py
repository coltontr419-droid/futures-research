"""Shadow logger for Kalshi combo RFQs (decisions.md 742-744): watches the authenticated `communications` WebSocket, records every
RFQ (legs, size, times) and, for combo RFQs, each leg's top of book at that moment. READ-ONLY: it never creates RFQs or quotes.
The executed price and the settlement are joined later from public data by `futuresres.combo.c3_shadow`.

    KALSHI_KEY_ID=... KALSHI_KEY_PATH=... python rfq_shadow.py
Env: RFQ_DIR (default ./rfq), BOOK_RATE (leg-book requests a second, default 4), QUEUE_MAX (default 200), SAMPLE (default 0.001), MIN_FREE_GB (default 10).
Kalshi broadcasts >1,000 RFQs a second (most deleted within the minute), so only a deterministic hash-sample of RFQ ids is logged.
"""

from __future__ import annotations

import asyncio
import shutil
import hashlib
import datetime as dt
import json
import os
import random
import time
from pathlib import Path

import websockets

from kalshi_api import Client

WS_URL = os.environ.get("KALSHI_WS", "wss://api.elections.kalshi.com/trade-api/ws/v2")
WS_PATH = "/trade-api/ws/v2"
DIR = Path(os.environ.get("RFQ_DIR", Path(__file__).with_name("rfq")))
BOOK_RATE = float(os.environ.get("BOOK_RATE", "4"))
SAMPLE = float(os.environ.get("SAMPLE", "0.001"))
MIN_FREE_GB = float(os.environ.get("MIN_FREE_GB", "10"))   # stop logging below this much free disk (the futures bot shares it)
_W = {"n": 0, "full": False}
QUEUE_MAX = int(os.environ.get("QUEUE_MAX", "200"))


def write(kind: str, rec: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    _W["n"] += 1
    if _W["n"] % 500 == 1:
        _W["full"] = shutil.disk_usage(DIR).free / 1e9 < MIN_FREE_GB
    if _W["full"] and kind not in ("heartbeat", "disconnected"):
        return
    rec = {"kind": kind, "recv": dt.datetime.now(dt.timezone.utc).isoformat(), **rec}
    with open(DIR / f"rfq_{dt.datetime.now(dt.timezone.utc):%Y%m%d}.jsonl", "a") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


def sampled(rfq_id: str) -> bool:
    return int(hashlib.sha1((rfq_id or "").encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < SAMPLE


def top(ob: dict) -> dict:
    yes = ob.get("yes_dollars") or []; no = ob.get("no_dollars") or []
    yb = max(yes, key=lambda x: float(x[0])) if yes else None; nb = max(no, key=lambda x: float(x[0])) if no else None
    return {"yes_bid": float(yb[0]) if yb else None, "yes_bid_size": float(yb[1]) if yb else None,
            "yes_ask": round(1 - float(nb[0]), 4) if nb else None, "yes_ask_size": float(nb[1]) if nb else None}


async def books(c: Client, q: asyncio.Queue) -> None:
    while True:
        rid, legs = await q.get()
        try:
            ob = await asyncio.to_thread(c.orderbooks, legs)
            write("legs", {"rfq_id": rid, "legs": {t: top(ob.get(t) or {}) for t in legs}})
        except Exception as e:                                             # noqa: BLE001
            write("legs_error", {"rfq_id": rid, "error": str(e)[:200]})
        await asyncio.sleep(1 / BOOK_RATE)


async def run() -> None:
    c = Client()
    assert c.authed, "KALSHI_KEY_ID / KALSHI_KEY_PATH not set"
    q: asyncio.Queue = asyncio.Queue(); asyncio.create_task(books(c, q)); dropped = 0; n = 0; last_beat = time.monotonic()
    while True:
        try:
            async with websockets.connect(WS_URL, additional_headers=c._sign("GET", WS_PATH), ping_interval=20, max_size=2 ** 22) as ws:
                await ws.send(json.dumps({"id": 1, "cmd": "subscribe", "params": {"channels": ["communications"]}}))
                write("connected", {})
                async for raw in ws:
                    m = json.loads(raw); t = m.get("type"); msg = m.get("msg") or {}
                    if t == "rfq_created":
                        n += 1
                        if not sampled(msg.get("id")):
                            continue
                        write("rfq", {k: msg.get(k) for k in ("id", "market_ticker", "event_ticker", "contracts_fp", "target_cost_dollars",
                                                              "created_ts", "mve_collection_ticker", "mve_selected_legs")})
                        legs = [x["market_ticker"] for x in (msg.get("mve_selected_legs") or [])]
                        if legs:
                            if q.qsize() >= QUEUE_MAX:
                                dropped += 1
                            else:
                                q.put_nowait((msg.get("id"), legs))
                    elif t == "rfq_deleted":
                        if not sampled(msg.get("id")):
                            continue
                        write("rfq_deleted", {"id": msg.get("id"), "market_ticker": msg.get("market_ticker"), "deleted_ts": msg.get("deleted_ts")})
                    elif t in ("error", "subscribed"):
                        write(t, {"msg": msg})
                    if time.monotonic() - last_beat > 300:
                        write("heartbeat", {"rfqs": n, "queue": q.qsize(), "dropped_leg_snapshots": dropped}); last_beat = time.monotonic()
        except Exception as e:                                             # noqa: BLE001
            write("disconnected", {"error": str(e)[:200]})
            await asyncio.sleep(5 + random.random() * 5)


if __name__ == "__main__":
    asyncio.run(run())
