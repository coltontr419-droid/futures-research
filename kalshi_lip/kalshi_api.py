"""Minimal Kalshi Trade API v2 client (decisions.md 694): request signing (Ed25519 or RSA-PSS), public reads, and the V2 order calls the
liquidity bot needs. The private key is read from a file path in the environment and never printed."""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = os.environ.get("KALSHI_BASE", "https://api.elections.kalshi.com")
PREFIX = "/trade-api/v2"
_lock = threading.Lock(); _next = [0.0]
RATE = float(os.environ.get("KALSHI_RATE", "8"))         # requests a second (well under the Basic tier)


def _pace():
    with _lock:
        now = time.monotonic(); t = max(now, _next[0]); _next[0] = t + 1.0 / RATE
    time.sleep(max(0.0, t - now))


class Client:
    def __init__(self, key_id: str | None = None, key_path: str | None = None):
        self.key_id = key_id or os.environ.get("KALSHI_KEY_ID", "")
        path = key_path or os.environ.get("KALSHI_KEY_PATH", "")
        self._key = None
        if self.key_id and path:
            from cryptography.hazmat.primitives import serialization
            with open(path, "rb") as fh:
                self._key = serialization.load_pem_private_key(fh.read(), password=None)

    @property
    def authed(self) -> bool:
        return self._key is not None

    def _sign(self, method: str, path: str) -> dict:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa
        ts = str(int(time.time() * 1000)); msg = (ts + method.upper() + path.split("?")[0]).encode()
        if isinstance(self._key, ed25519.Ed25519PrivateKey):
            sig = self._key.sign(msg)
        elif isinstance(self._key, rsa.RSAPrivateKey):
            sig = self._key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256().digest_size), hashes.SHA256())
        else:
            raise ValueError("unsupported key type")
        return {"KALSHI-ACCESS-KEY": self.key_id, "KALSHI-ACCESS-TIMESTAMP": ts, "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode()}

    def req(self, method: str, path: str, body: dict | None = None, auth: bool = False, tries: int = 4):
        full = PREFIX + path
        for k in range(tries):
            _pace()
            h = {"User-Agent": "lip-bot", "Content-Type": "application/json"}
            if auth:
                h.update(self._sign(method, full))
            data = json.dumps(body).encode() if body is not None else None
            try:
                with urllib.request.urlopen(urllib.request.Request(BASE + full, data=data, method=method, headers=h), timeout=30) as r:
                    txt = r.read().decode()
                    return json.loads(txt) if txt else {}
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and k + 1 < tries:
                    time.sleep(2 ** k); continue
                raise RuntimeError(f"{method} {path} -> {e.code} {e.read().decode()[:300]}") from None
            except (urllib.error.URLError, TimeoutError):
                if k + 1 < tries:
                    time.sleep(2 ** k); continue
                raise

    # ---- public
    def programmes(self, status: str = "active") -> list[dict]:
        out, cur = [], None
        while True:
            d = self.req("GET", f"/incentive_programs?status={status}&type=liquidity&limit=10000" + (f"&cursor={cur}" if cur else ""))
            out += d.get("incentive_programs", []); cur = d.get("next_cursor")
            if not cur or not d.get("incentive_programs"):
                return out

    def orderbooks(self, tickers: list[str]) -> dict:
        out = {}
        for i in range(0, len(tickers), 100):
            q = urllib.parse.urlencode([("tickers", t) for t in tickers[i:i + 100]])          # style: form, explode
            d = self.req("GET", f"/markets/orderbooks?{q}")
            for ob in d.get("orderbooks", []):
                out[ob.get("ticker")] = ob.get("orderbook_fp") or ob.get("orderbook") or ob
        return out

    # ---- authenticated
    def balance(self) -> dict:
        return self.req("GET", "/portfolio/balance", auth=True)

    def resting(self) -> list[dict]:
        out, cur = [], None
        while True:
            d = self.req("GET", "/portfolio/orders?status=resting&limit=1000" + (f"&cursor={cur}" if cur else ""), auth=True)
            out += d.get("orders", []); cur = d.get("cursor")
            if not cur or not d.get("orders"):
                return out

    def positions(self) -> list[dict]:
        d = self.req("GET", "/portfolio/positions?limit=1000", auth=True)
        return d.get("market_positions", [])

    _shard: dict = {}

    def shard(self, ticker: str) -> int:
        """The market's exchange shard (cached); funds and orders are per shard (docs: Exchange Sharding)."""
        if ticker not in self._shard:
            m = self.req("GET", f"/markets/{urllib.parse.quote(ticker)}").get("market") or {}
            self._shard[ticker] = int(m.get("exchange_index", 0) or 0)
        return self._shard[ticker]

    def place(self, ticker: str, outcome: str, cents: int, count: int, expires: int | None = None) -> dict:
        """Buy `count` contracts of `outcome` ('yes' / 'no') at `cents` of that outcome's price, post-only, resting.
        V2 single book: bid = yes, ask = no, and the price is always the YES price (decisions.md 694)."""
        side = "bid" if outcome == "yes" else "ask"; yes_price = cents if outcome == "yes" else 100 - cents
        body = {"ticker": ticker, "client_order_id": str(uuid.uuid4()), "side": side, "count": f"{count:.2f}", "price": f"{yes_price / 100:.4f}",
                "time_in_force": "good_till_canceled", "self_trade_prevention_type": "taker_at_cross", "post_only": True,
                "exchange_index": self.shard(ticker)}
        if expires:
            body["expiration_time"] = int(expires)
        r = self.req("POST", "/portfolio/events/orders", body, auth=True)
        r.setdefault("client_order_id", body["client_order_id"])
        return r

    def cancel(self, order_id: str, ticker: str) -> dict:
        return self.req("DELETE", f"/portfolio/events/orders/{order_id}?market_ticker={urllib.parse.quote(ticker)}", auth=True)
