"""A94 (decisions.md 776): does Riot's public livestats feed show LoL game events before Kalshi's in-play sweep? Records only, no orders.

Riot: every second, the three latest 10 s-aligned windows of feed.lolesports.com/livestats/v1/window/{game} for every live game
(found via esports-api getLive); each frame is logged once with the wall time it was first received.
Kalshi: every second, new trades on one side of each LIVE match's KXLOLGAME event (Riot team codes matched inside the event ticker,
else the open event listed nearest to now), logged with their exchange time and receive time.
NTP offset logged every 5 minutes (true UTC = local clock + offset).

    python -m futuresres.esports.a94_lolrace LABEL HOURS
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path

import ntplib

ROOT = Path(__file__).resolve().parents[3]
KB = "https://api.elections.kalshi.com/trade-api/v2"
RIOT = "https://esports-api.lolesports.com/persisted/gw"
RIOT_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"              # the public key the lolesports.com site itself sends
UTC = dt.timezone.utc


def get(url: str, headers: dict | None = None, timeout: float = 10) -> dict | None:
    try:
        b = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **(headers or {})}), timeout=timeout).read()
        return json.loads(b) if b else None
    except Exception:
        return None


def now() -> dt.datetime:
    return dt.datetime.now(UTC)


class Rec:
    def __init__(self, label: str, hours: float):
        self.dir = ROOT / "data" / "esports" / "a94" / label; self.dir.mkdir(parents=True, exist_ok=True)
        self.end = time.time() + hours * 3600; self.lock = threading.Lock()
        self.games: set[str] = set(); self.tickers: dict[str, str] = {}
        self.f = {k: open(self.dir / f"{k}.jsonl", "a") for k in ("riot", "kalshi", "log")}

    def w(self, k: str, row: dict) -> None:
        with self.lock:
            self.f[k].write(json.dumps(row) + "\n"); self.f[k].flush()

    def discover(self) -> None:
        while time.time() < self.end:
            live = get(f"{RIOT}/getLive?hl=en-US", {"x-api-key": RIOT_KEY}) or {}
            gs = set(); codes = []
            for e in (live.get("data", {}).get("schedule", {}).get("events") or []):
                m_ = e.get("match") or {}
                live_games = [g["id"] for g in m_.get("games", []) or [] if g.get("state") == "inProgress"]
                if live_games:
                    gs |= set(live_games); codes.append([t.get("code", "").upper() for t in m_.get("teams", [])])
            ev = (get(f"{KB}/events?series_ticker=KXLOLGAME&status=open&limit=200") or {}).get("events", [])
            tk = {}
            for cs in codes:
                hit = [e for e in ev if all(c and c in e["event_ticker"].split("-")[1][11:] for c in cs)]
                if not hit:                                # nearest listed start
                    def gap(e):
                        m = re.match(r"(\d{2}[A-Z]{3}\d{2})(\d{4})", e["event_ticker"].split("-")[1])
                        st = dt.datetime.strptime(m.group(1) + m.group(2), "%y%b%d%H%M").replace(tzinfo=dt.timezone(dt.timedelta(hours=-4)))
                        return abs((st - now()).total_seconds())
                    hit = sorted(ev, key=gap)[:1]
                for e in hit[:1]:
                    mks = (get(f"{KB}/markets?event_ticker={e['event_ticker']}") or {}).get("markets", [])
                    if mks:
                        tk[mks[0]["ticker"]] = cs
            if gs:                                          # keep the last live set 15 min past a game's end (the sweep follows it)
                self.games, self.tickers, self.seen_live = gs, tk, time.time()
            elif time.time() - getattr(self, "seen_live", 0) > 900:
                self.games, self.tickers = set(), {}
            try:
                off = ntplib.NTPClient().request("pool.ntp.org", version=3, timeout=5).offset
            except Exception:
                off = None
            self.w("log", {"t": now().isoformat(), "games": sorted(self.games), "tickers": sorted(self.tickers), "ntp_offset": off})
            time.sleep(120 if gs else 60)

    def riot(self) -> None:
        seen: set[tuple[str, str]] = set()
        while time.time() < self.end:
            t0 = time.time(); base = now().replace(microsecond=0)
            for g in list(self.games):
                for back in (10, 20, 30):
                    s = base - dt.timedelta(seconds=back); s = s.replace(second=s.second // 10 * 10)
                    d = get(f"https://feed.lolesports.com/livestats/v1/window/{g}?startingTime={s.strftime('%Y-%m-%dT%H:%M:%SZ')}", timeout=5)
                    rcv = now().isoformat()
                    for fr in (d or {}).get("frames", []):
                        k = (g, fr["rfc460Timestamp"])
                        if k in seen:
                            continue
                        seen.add(k); b, r = fr["blueTeam"], fr["redTeam"]
                        self.w("riot", {"game": g, "ts": fr["rfc460Timestamp"], "rcv": rcv, "state": fr["gameState"],
                                        "k": [b["totalKills"], r["totalKills"]], "tw": [b["towers"], r["towers"]], "inh": [b["inhibitors"], r["inhibitors"]],
                                        "bar": [b["barons"], r["barons"]], "drg": [len(b["dragons"]), len(r["dragons"])], "gold": [b["totalGold"], r["totalGold"]]})
            time.sleep(max(0.0, 1.0 - (time.time() - t0)))

    def kalshi(self) -> None:
        last: dict[str, str] = {}
        while time.time() < self.end:
            t0 = time.time()
            for tk in list(self.tickers):
                d = get(f"{KB}/markets/trades?ticker={tk}&limit=200", timeout=5); rcv = now().isoformat()
                for x in reversed((d or {}).get("trades", [])):
                    if x["created_time"] > last.get(tk, ""):
                        self.w("kalshi", {"ticker": tk, "t": x["created_time"], "rcv": rcv, "p": x["yes_price_dollars"], "q": x["count_fp"], "side": x["taker_side"]})
                        last[tk] = x["created_time"]
            time.sleep(max(0.0, 1.0 - (time.time() - t0)))


def main(argv) -> int:
    r = Rec(argv[0], float(argv[1]))
    ts = [threading.Thread(target=f, daemon=True) for f in (r.discover, r.riot, r.kalshi)]
    for t in ts:
        t.start()
    while time.time() < r.end:
        time.sleep(30)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
