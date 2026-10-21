"""A97 (decisions.md 787): ProphetX positive-EV offer episodes in real time, from its public websocket. Records only, no orders.

    python -m futuresres.sports.a97_pxstream record     # service futres-a97
    python -m futuresres.sports.a97_pxstream            # readout
"""

from __future__ import annotations

import asyncio
import collections
import datetime as dt
import difflib
import json
import statistics as st
import sys
import time
from pathlib import Path

import websockets

from futuresres.sports import a96_prophetx as a

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "sports" / "a97"
WS = "wss://ws.prophetx.co/app/c975574818f436e8dd4a?protocol=7&client=js&version=8.4.0&flash=false"
SPORTS = ("American Football", "Basketball", "Ice Hockey", "Tennis")
UTC = dt.timezone.utc


def now() -> dt.datetime:
    return dt.datetime.now(UTC)


class Book:
    def __init__(self):
        self.pins: dict = {}; self.events: dict = {}; self.best: dict = {}; self.open: dict = {}
        OUT.mkdir(parents=True, exist_ok=True)

    def log(self, row: dict) -> None:
        with open(OUT / f"{now():%Y%m%d}.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")

    def refresh_pins(self) -> None:
        self.pins = a.pinnacle()

    def pz(self, ev: dict):
        """Both ProphetX competitors -> their Pinnacle entries, only if they are the same Pinnacle matchup."""
        keys = [k[1] for k in self.pins if k[0] == ev["sport"]]; out = {}
        for me in ev["comp"].values():
            hit = me if (ev["sport"], me) in self.pins else (difflib.get_close_matches(me, keys, 1, 0.9) or [None])[0] if len(me) >= 8 else None
            if not hit:
                return None
            out[me] = self.pins[(ev["sport"], hit)]
        return out if len(out) == 2 and len({v["id"] for v in out.values()}) == 1 else None

    def refresh_events(self) -> list[int]:
        evs, nxt = [], None
        for _ in range(80):
            d = a.get(f"{a.PX}/v1/events" + (f"?next={nxt}" if nxt else "")) or {}
            evs += d.get("data") or []; nxt = d.get("next")
            if not nxt or not d.get("data"):
                break
        new = []
        for e in evs:
            st_ = dt.datetime.fromisoformat(e["scheduled"].replace("Z", "+00:00"))
            if e["sport"]["name"] not in SPORTS or e.get("status") != "not_started" or not dt.timedelta(0) < st_ - now() < dt.timedelta(days=3):
                continue
            if e["id"] in self.events:
                continue
            ms = ((a.get(f"{a.PX}/v2/events/{e['id']}/markets") or {}).get("data") or {}).get("markets") or []
            time.sleep(1.5)
            mk = {x["id"]: x.get("subType") for x in ms if x.get("subType") in ("moneyline", "spread", "total")
                  and (e["sport"]["name"] != "Tennis" or x.get("subType") == "moneyline")}   # tennis handicaps/totals are in sets
            self.events[e["id"]] = {"sport": e["sport"]["name"], "start": e["scheduled"], "markets": mk,
                                    "comp": {c["id"]: a.norm(c["name"]) for c in e.get("competitors", [])}}
            new.append(e["id"])
            for x in ms:                                         # seed: offers already resting when we subscribe
                if x["id"] in mk:
                    self.update(e["id"], x["id"], x.get("marketLines") or [{"selections": x.get("selections")}])
        for k in [k for k, v in self.events.items() if v["start"] < now().isoformat()]:
            self.events.pop(k)
        return new

    def fair(self, ev: dict, sub: str, o: dict) -> tuple[str, float] | None:
        pz = self.pz(ev)
        if not pz:
            return None
        who = ev["comp"].get(o.get("competitorId"), ""); nm = (o.get("name") or o.get("displayName") or "").lower(); line = o.get("line")
        if sub == "moneyline" and who in pz:
            return who, pz[who]["p"]
        if sub == "spread" and who in pz and pz[who]["spread"] and pz[who]["spread"][0] is not None and float(line) == float(pz[who]["spread"][0]):
            return f"{who} {line:+g}", pz[who]["spread"][1]
        if sub == "total" and nm[:4] in ("over", "unde"):
            t = next(iter(pz.values()))["total"]
            if t:
                ou = "over" if nm.startswith("over") else "under"; pt, pp = t[ou]
                if pt is not None and float(line) == float(pt):
                    return f"{ou} {line:g}", pp
        return None

    def update(self, eid: int, mid: int, lines: list) -> None:
        ev = self.events.get(eid)
        if not ev or mid not in ev["markets"] or now().isoformat() >= ev["start"].replace("Z", "+00:00"):
            return                                               # pre-match only
        sub = ev["markets"][mid]
        for ln in lines or []:
            for side in ln.get("selections") or []:
                if not side:
                    continue
                best = max(side, key=lambda s: a.dec(s["odds"]))
                f = self.fair(ev, sub, best)
                if not f:
                    continue
                key = (eid, mid, f[0]); self.best[key] = (best, sub)
                self.judge(key, ev, sub, a.dec(best["odds"]), f[1], float(best.get("value") or 0), best["odds"])

    def judge(self, key, ev, sub, D, p, val, odds, reason_if_close="offer") -> None:
        evv = p * (D - 1) * (1 - a.FEE) - (1 - p); t = now()
        if evv >= 0.02 and val >= 1:
            if key not in self.open:
                self.open[key] = {"start": t.isoformat(), "sport": ev["sport"], "market": sub, "side": key[2], "event": key[0], "odds": odds,
                                  "ev": round(evv, 4), "stake0": val, "stake_min": val, "p_start": round(p, 4)}
            else:
                o = self.open[key]; o["stake_min"] = min(o["stake_min"], val)
        elif key in self.open:
            o = self.open.pop(key); o.update(end=t.isoformat(), ev_end=round(evv, 4), reason=reason_if_close, p_end=round(p, 4), odds_end=odds,
                                             life_s=(t - dt.datetime.fromisoformat(o["start"])).total_seconds())
            self.log(o)

    def rejudge(self) -> None:                                    # after a Pinnacle refresh
        for key, (o, sub) in list(self.best.items()):
            ev = self.events.get(key[0])
            if not ev:
                self.best.pop(key, None); self.open.pop(key, None); continue
            f = self.fair(ev, sub, o)
            if f:
                self.judge(key, ev, sub, a.dec(o["odds"]), f[1], float(o.get("value") or 0), o["odds"], "pinnacle_moved")
            elif key in self.open:                                 # Pinnacle moved its main line away
                self.judge(key, ev, sub, a.dec(o["odds"]), 0.0, 0.0, o["odds"], "pinnacle_moved")


async def run() -> None:
    b = Book(); b.refresh_pins(); last_pin = time.time(); last_ev = 0.0
    while True:
        try:
            async with websockets.connect(WS, ping_interval=None, max_size=2 ** 23) as ws:
                await ws.recv(); subs = set()
                while True:
                    if time.time() - last_ev > 3600 or not subs:
                        await asyncio.to_thread(b.refresh_events); last_ev = time.time()
                        for eid in b.events:
                            if eid not in subs:
                                await ws.send(json.dumps({"event": "pusher:subscribe", "data": {"channel": f"public-broadcast-service=1-device_type=1-event={eid}"}}))
                                subs.add(eid)
                        print(f"{now():%H:%MZ} subscribed {len(subs)} events", flush=True)
                    if time.time() - last_pin > 120:
                        await asyncio.to_thread(b.refresh_pins); b.rejudge(); last_pin = time.time()
                        print(f"{now():%H:%MZ} tracked sides {len(b.best)}, open +EV episodes {len(b.open)}", flush=True)
                        await ws.send(json.dumps({"event": "pusher:ping", "data": {}}))
                    try:
                        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                    except asyncio.TimeoutError:
                        continue
                    if m.get("event") != "liquidity_change":
                        continue
                    d = json.loads(m["data"]) if isinstance(m["data"], str) else m["data"]
                    b.update(d.get("sport_event_id"), d.get("market_id"), d.get("marketLines"))
        except Exception as e:                                   # reconnect
            print(f"{now():%H:%MZ} websocket error {e!r}; reconnecting", flush=True)
            await asyncio.sleep(10)


def readout() -> dict:
    rows = [json.loads(l) for p in sorted(OUT.glob("*.jsonl")) for l in open(p)]
    if not rows:
        print("no episodes yet"); return {}
    days = max(1 / 24, (max(dt.datetime.fromisoformat(r["end"]) for r in rows) - min(dt.datetime.fromisoformat(r["start"]) for r in rows)).total_seconds() / 86400)
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["sport"], r["market"])].append(r)
    for k, v in sorted(by.items()):
        life = [r["life_s"] for r in v]
        print(f"{k[0][:10]:10} {k[1]:9} episodes {len(v):4} ({len(v)/days:.0f}/day), stake at start ${sum(r['stake0'] for r in v)/days:,.0f}/day, "
              f"EV×stake ${sum(r['stake0']*r['ev'] for r in v)/days:,.0f}/day, median life {st.median(life):.0f}s, < 10 s {sum(x < 10 for x in life)/len(life):.0%}, "
              f"ended by {dict(collections.Counter(r['reason'] for r in v))}")
    return {"episodes": len(rows), "days": days}


if __name__ == "__main__":
    asyncio.run(run()) if sys.argv[1:2] == ["record"] else readout()
