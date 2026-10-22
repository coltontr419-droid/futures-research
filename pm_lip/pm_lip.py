"""Polymarket US standing-order incentive test (decisions.md 879-880). One empty rewarded market, 7,500 @ 0.1c on each side, $15 hard stop.

    python pm_lip.py status               # balance, open orders, positions, recent activities
    python pm_lip.py pick                 # list empty rewarded markets (public data)
    python pm_lip.py place SLUG           # preview, then place both sides (maker only)
    python pm_lip.py monitor              # every 5 min: log fills/activities/balance; cancel all past the $15 stop
    python pm_lip.py cancel               # cancel all open orders

Keys: /opt/pm-lip/.env (PM_KEY_ID, PM_SECRET_KEY) — never printed.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API, GW = "https://api.polymarket.us", "https://gateway.polymarket.us"
SIZE, BID, STOP_USD = 7500, "0.001", 15.0
LOG = HERE / "pm_lip_log.jsonl"


def env() -> None:
    for l in (HERE / ".env").read_text().splitlines():
        if "=" in l and not l.strip().startswith("#"):
            k, v = l.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def log(**kw) -> None:
    with open(LOG, "a") as f:
        f.write(json.dumps({"t": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **kw}) + "\n")


class PM:
    def __init__(self) -> None:
        env()
        from cryptography.hazmat.primitives.asymmetric import ed25519
        self.kid = os.environ["PM_KEY_ID"]
        self.key = ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(os.environ["PM_SECRET_KEY"])[:32])

    def req(self, method: str, path: str, body: dict | None = None):
        ts = str(int(time.time() * 1000)); sig = base64.b64encode(self.key.sign(f"{ts}{method}{path.split('?')[0]}".encode())).decode()
        h = {"X-PM-Access-Key": self.kid, "X-PM-Timestamp": ts, "X-PM-Signature": sig, "Content-Type": "application/json", "User-Agent": "pm-lip"}
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urllib.request.urlopen(urllib.request.Request(API + path, data=data, method=method, headers=h), timeout=30) as r:
                t = r.read().decode(); return json.loads(t) if t else {}
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path} -> {e.code} {e.read().decode()[:400]}") from None


def gw(path: str):
    return json.loads(urllib.request.urlopen(urllib.request.Request(GW + path, headers={"User-Agent": "pm-lip"}), timeout=30).read())


def order(slug: str, side: str) -> dict:
    """side 'yes': buy YES at 0.1c; side 'no': buy NO at 0.1c = sell-short YES at 99.9c (prices are always the YES price)."""
    return {"marketSlug": slug, "type": "ORDER_TYPE_LIMIT", "quantity": SIZE, "tif": "TIME_IN_FORCE_GOOD_TILL_CANCEL", "participateDontInitiate": True,
            "manualOrderIndicator": "MANUAL_ORDER_INDICATOR_AUTOMATIC",
            "intent": "ORDER_INTENT_BUY_LONG" if side == "yes" else "ORDER_INTENT_BUY_SHORT",
            "price": {"value": BID if side == "yes" else f"{1 - float(BID):.3f}", "currency": "USD"}}


def status() -> None:
    c = PM()
    b = c.req("GET", "/v1/account/balances"); print("balances:", json.dumps(b)[:600])
    print("open orders:", json.dumps(c.req("GET", "/v1/orders/open"))[:800])
    print("positions:", json.dumps(c.req("GET", "/v1/portfolio/positions"))[:800])
    print("activities:", json.dumps(c.req("GET", "/v1/portfolio/activities"))[:1500])


def pick(n: int = 15) -> None:
    progs, tok = [], None
    for _ in range(40):
        d = gw("/v1/incentives" + (f"?pageToken={tok}" if tok else "")); progs += d.get("programs", []); tok = d.get("nextPageToken")
        if not tok:
            break
    out = []
    for m in progs:
        t = next((t for t in m["timePeriods"] if t.get("status") == "active"), None)
        if not t or t["rewardPool"] < 27:
            continue
        try:
            b = gw(f"/v1/markets/{m['marketSlug']}/book")["marketData"]
        except Exception:
            continue
        nb, no = sum(float(x["qty"]) for x in b.get("bids", [])), sum(float(x["qty"]) for x in b.get("offers", []))
        if nb == 0 and no == 0:
            out.append((m["marketSlug"], t["rewardPool"], t["targetSize"], t["programId"]))
        if len(out) >= n:
            break
    for x in out:
        print(*x)


def place(slug: str) -> None:
    c = PM()
    for side in ("yes", "no"):
        o = order(slug, side)
        pv = c.req("POST", "/v1/order/preview", {"request": o}); print(side, "preview:", json.dumps(pv)[:700]); log(event="preview", side=side, slug=slug, resp=pv)
    if input("Previews OK? type PLACE to place both orders: ").strip() != "PLACE":
        print("not placed"); return
    for side in ("yes", "no"):
        r = c.req("POST", "/v1/orders", order(slug, side)); print(side, "placed:", r); log(event="place", side=side, slug=slug, resp=r)


def cancel_all() -> None:
    r = PM().req("POST", "/v1/orders/open/cancel", {}); print("cancel all:", r); log(event="cancel_all", resp=r)


def monitor() -> None:
    c = PM(); seen = set()
    while not (HERE / "STOP").exists():
        try:
            b = c.req("GET", "/v1/account/balances"); acts = c.req("GET", "/v1/portfolio/activities")
            A = acts.get("activities") or acts.get("data") or []
            new = [a for a in A if json.dumps(a, sort_keys=True) not in seen]
            for a in new:
                seen.add(json.dumps(a, sort_keys=True)); log(event="activity", a=a)
            pos = c.req("GET", "/v1/portfolio/positions"); log(event="snapshot", balances=b, positions=pos)
            log(event="earnings", e=c.req("GET", "/v1/incentives/earnings"))
            cost = 0.0
            for p in (pos.get("positions") or {}).values() if isinstance(pos.get("positions"), dict) else (pos.get("positions") or []):
                try:
                    cost += abs(float((p.get("cost") or {}).get("value", 0)))
                except Exception:
                    pass
            orders = c.req("GET", "/v1/orders/open").get("orders", [])
            filled = sum(float(o.get("cumQuantity") or 0) * (float(o["price"]["value"]) if o.get("intent") == "ORDER_INTENT_BUY_LONG" else 1 - float(o["price"]["value"]))
                         for o in orders)
            missing = {o["id"] for o in orders}
            log(event="orders", n=len(orders), filled_usd=round(filled, 2), ids=sorted(missing))
            cost = max(cost, filled)
            if cost > STOP_USD or (orders == [] and (HERE / "placed.flag").exists()):   # all our orders gone = filled or removed: stop
                log(event="stop", cost=cost); cancel_all(); (HERE / "STOP").write_text("fill stop"); break
        except Exception as e:
            log(event="error", err=str(e)[:300])
        time.sleep(300)


if __name__ == "__main__":
    cmd = sys.argv[1:2]
    {"status": status, "pick": pick, "cancel": cancel_all, "monitor": monitor}.get(cmd[0] if cmd else "status", status)() if cmd != ["place"] else place(sys.argv[2])
