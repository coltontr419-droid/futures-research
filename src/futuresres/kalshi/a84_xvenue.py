"""A84 (decisions.md 714): Kalshi x Polymarket US prices on the same games, sampled every 3 minutes. No orders.

    python -m futuresres.kalshi.a84_xvenue [sweeps]
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
from kalshi_api import Client  # noqa: E402

OUT = ROOT / "reports" / "a84_xvenue.jsonl"
PM = "https://gateway.polymarket.us"
LEAGUES = {"nfl": "KXNFLGAME", "mlb": "KXMLBGAME", "nhl": "KXNHLGAME"}


def pm(path):
    return json.loads(urllib.request.urlopen(urllib.request.Request(PM + path, headers={"User-Agent": "research"}), timeout=30).read())


def fee(p, theta):
    return theta * p * (1 - p)


def kalshi_games(c: Client, series: str) -> dict:
    """(date YYMONDD, frozenset of team codes) -> {code: (bid, ask, bid size, ask size)} from the order books."""
    out = {}
    for e in c.req("GET", f"/events?series_ticker={series}&status=open&limit=200").get("events", []):
        et = e["event_ticker"]; m = re.match(r"[A-Z]+-(\d{2}[A-Z]{3}\d{2})", et)
        if not m:
            continue
        ms = c.req("GET", f"/markets?event_ticker={et}&limit=10").get("markets", [])
        if len(ms) != 2:
            continue
        books = c.orderbooks([x["ticker"] for x in ms]); teams = {}
        for x in ms:
            code = x["ticker"].split("-")[-1]; ob = books.get(x["ticker"], {})
            yes = sorted(((float(p), float(q)) for p, q in ob.get("yes_dollars", [])), reverse=True)
            no = sorted(((float(p), float(q)) for p, q in ob.get("no_dollars", [])), reverse=True)
            bid, bq = (yes[0] if yes else (0.0, 0.0)); ask = (1 - no[0][0]) if no else 1.0; aq = no[0][1] if no else 0.0
            teams[code] = (bid, ask, bq, aq)
        out[(m.group(1), frozenset(teams))] = {"event": et, "teams": teams}
    return out


def sweep(c: Client) -> list[dict]:
    rows = []; now = dt.datetime.now(dt.timezone.utc)
    for league, series in LEAGUES.items():
        try:
            K = kalshi_games(c, series)
            evs = pm(f"/v2/leagues/{league}/events?limit=100").get("events", [])
        except Exception as e:
            print("fetch error", league, str(e)[:100], flush=True); continue
        for ev in evs:
            if ev.get("closed") or ev.get("ended"):
                continue
            st = dt.datetime.fromisoformat(ev["startTime"].replace("Z", "+00:00"))
            if st - now > dt.timedelta(hours=24):
                continue
            codes = re.findall(r"\b([A-Z]{2,4})\b", ev.get("title", ""))[:2]
            mk = next((m for m in ev.get("markets", []) if m.get("marketType") == "moneyline"), None)
            if len(codes) != 2 or not mk:
                continue
            day = st.astimezone(dt.timezone(dt.timedelta(hours=-4))).strftime("%y%b%d").upper()
            kg = next((v for (d, t), v in K.items() if t == frozenset(codes)), None)
            if not kg:
                continue
            try:
                md = pm(f"/v1/markets/{mk['slug']}/book").get("marketData", {})
            except Exception:
                continue
            bids = md.get("bids") or []; offers = md.get("offers") or []
            if not bids or not offers:
                continue
            pb, pbq = float(bids[0]["px"]["value"]), float(bids[0]["qty"]); pa, paq = float(offers[0]["px"]["value"]), float(offers[0]["qty"])
            long_code = codes[0]; short_code = codes[1]                 # Polymarket's long side is the first team in the title
            kL, kS = kg["teams"].get(long_code), kg["teams"].get(short_code)
            if not kL or not kS:
                continue
            # A: buy the long team on Polymarket (ask) + the other team on Kalshi (its ask)
            costA = pa + kS[1]; netA = 1 - costA - fee(pa, 0.0695) - fee(kS[1], 0.07); sizeA = min(paq, kS[3])
            # B: buy the long team on Kalshi (ask) + the other team on Polymarket (1 - Polymarket bid)
            costB = kL[1] + (1 - pb); netB = 1 - costB - fee(kL[1], 0.07) - fee(1 - pb, 0.0695); sizeB = min(pbq, kL[3])
            rows.append({"league": league, "game": ev["title"], "live": bool(ev.get("live")), "pm": [pb, pa], "kalshi_long": kL[:2], "kalshi_short": kS[:2],
                         "netA": netA, "sizeA": sizeA, "netB": netB, "sizeB": sizeB})
    return rows


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60; c = Client()
    for i in range(n):
        t0 = time.time(); now = dt.datetime.now(dt.timezone.utc)
        rows = sweep(c)
        best = max(rows, key=lambda r: max(r["netA"], r["netB"]), default=None)
        with OUT.open("a") as f:
            f.write(json.dumps({"time": now.isoformat(timespec="seconds"), "rows": rows}) + "\n")
        pos = [r for r in rows if max(r["netA"], r["netB"]) > 0]
        print(f"{now:%H:%MZ} matched {len(rows)} games; positive nets {len(pos)}; best "
              + (f"{max(best['netA'], best['netB'])*100:+.2f}c ({best['game'][:30]}, live={best['live']})" if best else "-"), flush=True)
        if i + 1 < n:
            time.sleep(max(0, 180 - (time.time() - t0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
