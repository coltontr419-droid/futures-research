"""A93 (decisions.md 773): Kalshi x Polymarket US prices on the same NBA player props, sampled every 5 minutes. No orders.

    python -m futuresres.kalshi.a93_props_xvenue [sweeps]
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a93_props_xvenue.jsonl"
PM = "https://gateway.polymarket.us"
KB = "https://api.elections.kalshi.com/trade-api/v2"
STATS = {"basketball_player_points": "KXNBAPTS", "basketball_player_rebounds": "KXNBAREB",
         "basketball_player_assists": "KXNBAAST", "basketball_player_threes": "KXNBA3PT"}


def get(url: str) -> dict:
    for k in range(5):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research"}), timeout=30).read())
        except Exception:
            time.sleep(2 ** k)
    return {}


def norm(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", re.sub(r"[^a-z ]", "", name)).split())


def kalshi(series: str) -> dict:
    """(sorted team pair, player, threshold) -> (bid, ask)."""
    out, cur = {}, None
    while True:
        d = get(f"{KB}/markets?series_ticker={series}&status=open&limit=1000" + (f"&cursor={cur}" if cur else ""))
        for m in d.get("markets", []):
            g = re.match(r"(.+):\s*(\d+)\+$", m.get("yes_sub_title") or ""); ev = m["event_ticker"].split("-")[1]
            if not g:
                continue
            teams = ev[7:]
            out[(teams, norm(g.group(1)), int(g.group(2)))] = (float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 1), m["ticker"])
        cur = d.get("cursor")
        if not cur or not d.get("markets"):
            return out


def fee(p: float, th: float) -> float:
    return th * p * (1 - p)


def sweep() -> list[dict]:
    now = dt.datetime.now(dt.timezone.utc); rows = []
    K = {s: kalshi(s) for s in STATS.values()}
    for ev in get(f"{PM}/v2/leagues/nba/events?limit=100").get("events", []):
        st = dt.datetime.fromisoformat(ev["startTime"].replace("Z", "+00:00"))
        if ev.get("closed") or not dt.timedelta(0) < st - now < dt.timedelta(hours=12):
            continue
        full = get(f"{PM}/v1/events/slug/{ev['slug']}").get("event", {})
        a, h = (x.upper() for x in ev["slug"].split("-")[1:3])      # Polymarket codes can be shorter (NY / NYK, SA / SAS)
        pairs = {k[0] for ks in K.values() for k in ks}
        pair = next((t for t in pairs if any(t[:i].startswith(a) and t[i:].startswith(h) for i in range(2, len(t) - 1))), None)
        if not pair:
            continue
        for m in full.get("markets", []):
            ser = STATS.get(m.get("sportsMarketType"))
            g = re.match(r"Will (.+?) (?:record|score|make) at least (\d+)", m.get("question", ""))
            if not ser or not g or not m.get("bestBidQuote") or not m.get("bestAskQuote"):
                continue
            k = K[ser].get((pair, norm(g.group(1)), int(g.group(2))))
            if not k:
                continue
            pb, pa = float(m["bestBidQuote"]["value"]), float(m["bestAskQuote"]["value"]); kb, ka, tk = k
            th = float(m.get("feeCoefficient") or 0.0695)
            netA = 1 - pa - (1 - kb) - fee(pa, th) - fee(1 - kb, 0.07)        # YES on Polymarket, NO on Kalshi
            netB = 1 - ka - (1 - pb) - fee(ka, 0.07) - fee(1 - pb, th)        # YES on Kalshi, NO on Polymarket
            rows.append({"game": ev["slug"], "kalshi": tk, "pm": m["slug"], "pm_q": [pb, pa], "k_q": [kb, ka], "netA": netA, "netB": netB,
                         "mins_to_start": round((st - now).total_seconds() / 60)})
    for r in rows:                                                          # sizes only where it matters
        if max(r["netA"], r["netB"]) > 0:
            md = get(f"{PM}/v1/markets/{r['pm']}/book").get("marketData", {})
            ob = get(f"{KB}/markets/{r['kalshi']}/orderbook").get("orderbook_fp") or {}
            r["pm_book"] = {"bids": (md.get("bids") or [])[:1], "offers": (md.get("offers") or [])[:1]}; r["k_book"] = {k: v[-1:] for k, v in ob.items() if v}
    return rows


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 72
    for i in range(n):
        t0 = time.time(); now = dt.datetime.now(dt.timezone.utc)
        rows = sweep(); pos = [r for r in rows if max(r["netA"], r["netB"]) > 0]
        with OUT.open("a") as f:
            f.write(json.dumps({"time": now.isoformat(timespec="seconds"), "rows": rows}) + "\n")
        best = max(rows, key=lambda r: max(r["netA"], r["netB"]), default=None)
        print(f"{now:%H:%MZ} matched {len(rows)} props; positive nets {len(pos)}; best "
              + (f"{max(best['netA'], best['netB'])*100:+.2f}c {best['kalshi']}" if best else "-"), flush=True)
        if i + 1 < n:
            time.sleep(max(0, 300 - (time.time() - t0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
