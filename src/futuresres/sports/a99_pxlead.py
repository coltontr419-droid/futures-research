"""A99 (decisions.md 804): does Kalshi's NBA moneyline lag ProphetX's moves? Records only, no orders.

    python -m futuresres.sports.a99_pxlead record     # service futres-a99
    python -m futuresres.sports.a99_pxlead            # readout
"""

from __future__ import annotations

import asyncio
import collections
import datetime as dt
import json
import statistics as st
import sys
import time
from pathlib import Path

import websockets

from futuresres.kalshi.k1_longshot import fee
from futuresres.sports import a96_prophetx as a
from futuresres.sports.a97_pxstream import WS

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "sports" / "a99"
KB = "https://api.elections.kalshi.com/trade-api/v2"
UTC = dt.timezone.utc


def now() -> dt.datetime:
    return dt.datetime.now(UTC)


def log(kind: str, row: dict) -> None:
    with open(OUT / f"{kind}_{now():%Y%m%d}.jsonl", "a") as f:
        f.write(json.dumps({"t": now().isoformat(), **row}) + "\n")


def nba_events() -> dict:
    evs, nxt = [], None
    for _ in range(80):
        d = a.get(f"{a.PX}/v1/events" + (f"?next={nxt}" if nxt else "")) or {}
        evs += d.get("data") or []; nxt = d.get("next")
        if not nxt or not d.get("data"):
            break
    out = {}
    for e in evs:
        st_ = dt.datetime.fromisoformat(e["scheduled"].replace("Z", "+00:00"))
        if e["tournament"]["name"] != "NBA" or e.get("status") not in ("not_started", "live") or not -dt.timedelta(hours=4) < st_ - now() < dt.timedelta(hours=14):
            continue
        ms = ((a.get(f"{a.PX}/v2/events/{e['id']}/markets") or {}).get("data") or {}).get("markets") or []; time.sleep(1.5)
        ml = next((m for m in ms if m.get("subType") == "moneyline"), None)
        if ml:
            out[e["id"]] = {"start": e["scheduled"], "mid": ml["id"], "comp": {c["id"]: a.norm(c["name"]) for c in e.get("competitors", [])},
                            "day": st_.astimezone(dt.timezone(dt.timedelta(hours=-4))).strftime("%y%b%d").upper(), "best": {}}
            for side in ml.get("selections") or []:
                if side:
                    b = max(side, key=lambda s: a.dec(s["odds"])); out[e["id"]]["best"][b.get("competitorId")] = a.dec(b["odds"])
    return out


def kalshi_books() -> dict:
    d = a.get(f"{KB}/markets?series_ticker=KXNBAGAME&status=open&limit=1000") or {}
    ev = collections.defaultdict(dict)
    for m in d.get("markets", []):
        ev[m["event_ticker"].split("-")[1][:7]].setdefault(m["event_ticker"], {})[a.norm(m.get("yes_sub_title") or "")] = (
            float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 1))
    return ev


def fair(e: dict) -> dict | None:
    if len(e["best"]) != 2:
        return None
    q = {k: 1 / v for k, v in e["best"].items()}; s = sum(q.values())
    return {e["comp"].get(k, ""): v / s for k, v in q.items()}


async def record() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            E = await asyncio.to_thread(nba_events); last_ev = time.time(); last_k = 0.0
            async with websockets.connect(WS, ping_interval=None, max_size=2 ** 23) as ws:
                await ws.recv()
                for eid in E:
                    await ws.send(json.dumps({"event": "pusher:subscribe", "data": {"channel": f"public-broadcast-service=1-device_type=1-event={eid}"}}))
                print(f"{now():%H:%MZ} subscribed {len(E)} NBA events", flush=True)
                while time.time() - last_ev < 1800:
                    if time.time() - last_k >= 3:
                        K = await asyncio.to_thread(kalshi_books); last_k = time.time()
                        for eid, e in E.items():
                            for evt, mk in K.get(e["day"], {}).items():
                                got = {t: mk[c] for t in e["comp"].values() for c in mk if c and (t.startswith(c) or c in t)}
                                if len(got) == 2:
                                    log("kalshi", {"event": eid, "books": got})
                        if int(time.time()) % 120 < 3:
                            await ws.send(json.dumps({"event": "pusher:ping", "data": {}}))
                    try:
                        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=1))
                    except asyncio.TimeoutError:
                        continue
                    if m.get("event") != "liquidity_change":
                        continue
                    d = json.loads(m["data"]) if isinstance(m["data"], str) else m["data"]; e = E.get(d.get("sport_event_id"))
                    if not e or d.get("market_id") != e["mid"]:
                        continue
                    inplay = now().isoformat() >= e["start"].replace("Z", "+00:00")      # A99b (decisions.md 820)
                    for ln in d.get("marketLines") or [{"selections": d.get("selections")}]:
                        for side in ln.get("selections") or []:
                            if side:
                                b = max(side, key=lambda s: a.dec(s["odds"])); e["best"][b.get("competitorId")] = a.dec(b["odds"])
                    f = fair(e)
                    if f:
                        log("px", {"event": d["sport_event_id"], "fair": f, "inplay": inplay})
        except Exception as ex:
            print(f"{now():%H:%MZ} error {ex!r}; restarting", flush=True); await asyncio.sleep(10)


def readout() -> dict:
    px = [json.loads(l) for p in sorted(OUT.glob("px_*.jsonl")) for l in open(p)]
    ks = [json.loads(l) for p in sorted(OUT.glob("kalshi_*.jsonl")) for l in open(p)]
    T = lambda s: dt.datetime.fromisoformat(s)
    kb = collections.defaultdict(list)
    for k in ks:
        kb[k["event"]].append((T(k["t"]), k["books"]))
    opp = collections.defaultdict(list); bye = collections.defaultdict(list)
    for r in px:
        bye[r["event"]].append((T(r["t"]), r["fair"]))
    for ev, v in bye.items():
        v.sort(key=lambda x: x[0]); kk = sorted(kb.get(ev, []), key=lambda x: x[0])
        for i in range(1, len(v)):
            t1, f1 = v[i]; prev = [f for t, f in v[:i] if (t1 - t).total_seconds() <= 60]
            if not prev:
                continue
            for team, p1 in f1.items():
                p0 = prev[0].get(team)
                if p0 is None or abs(p1 - p0) < 0.02:
                    continue
                for lag in (3, 10, 30, 60):
                    k = next((b for t, b in kk if (t - t1).total_seconds() >= lag), None)
                    if k and team in k:
                        bid, ask = k[team]
                        opp[lag].append((p1 - ask - fee(ask)) if p1 > p0 else (bid - p1 - fee(bid)))
    if not opp:
        print(f"px rows {len(px)}, kalshi rows {len(ks)}: no ProphetX moves >= 2 pts yet"); return {}
    for lag, v in sorted(opp.items()):
        print(f"+{lag:2d}s: moves {len(v)}, median opportunity {st.median(v)*100:+.2f}c, >= 1c on {sum(x >= 0.01 for x in v)/len(v):.0%}")
    return {}


if __name__ == "__main__":
    asyncio.run(record()) if sys.argv[1:2] == ["record"] else readout()
