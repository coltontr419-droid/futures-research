"""Kalshi index markets - settled history from the public API (no key): every event of a series, its markets (strikes, result,
volume) and each traded market's hourly candlesticks (yes bid / ask / trade price). decisions.md 664. One JSON per event under
data/kalshi/<series>/; an existing file is skipped, so the download resumes.

    python -m futuresres.kalshi.download KXINX KXINXU KXNASDAQ100 [--close-only]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "kalshi"
B = "https://api.elections.kalshi.com/trade-api/v2"
RATE = 10.0                                              # requests a second overall, across the worker threads
_LOCK = threading.Lock(); _NEXT = [0.0]


def _pace() -> None:
    with _LOCK:
        now = time.monotonic(); t = max(now, _NEXT[0]); _NEXT[0] = t + 1.0 / RATE
    time.sleep(max(0.0, t - now))


def get(u: str, tries: int = 5) -> dict:
    for k in range(tries):
        try:
            _pace()
            return json.loads(urllib.request.urlopen(urllib.request.Request(B + u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            time.sleep(2 ** k)
        except Exception:
            time.sleep(2 ** k)
    raise RuntimeError(u)


def events(series: str) -> list[str]:
    out, cur = [], None
    while True:
        e = get(f"/events?series_ticker={series}&limit=200&status=settled" + (f"&cursor={cur}" if cur else ""))
        out += [x["event_ticker"] for x in e.get("events", [])]; cur = e.get("cursor")
        if not cur or not e.get("events"):
            return out


def markets(ev: str) -> list[dict]:
    for base in ("/historical/markets", "/markets"):
        m = get(f"{base}?event_ticker={ev}&limit=200").get("markets", [])
        if m:
            return m
    return []


def candles(series: str, mk: dict) -> list:
    end = int(dt.datetime.fromisoformat(mk["close_time"].replace("Z", "+00:00")).timestamp())
    op = mk.get("open_time"); st = int(dt.datetime.fromisoformat(op.replace("Z", "+00:00")).timestamp()) if op else end - 86400 * 3
    st = max(st, end - 86400 * 7)
    for u in (f"/historical/markets/{mk['ticker']}/candlesticks", f"/series/{series}/markets/{mk['ticker']}/candlesticks"):
        try:
            return get(f"{u}?start_ts={st}&end_ts={end}&period_interval=60").get("candlesticks", [])
        except urllib.error.HTTPError:
            continue
    return []


KEEP = ("ticker", "title", "yes_sub_title", "strike_type", "floor_strike", "cap_strike", "result", "close_time", "open_time",
        "expiration_value", "volume_fp", "volume", "open_interest_fp")


def run(series: str, close_only: bool) -> None:
    d = OUT / series; d.mkdir(parents=True, exist_ok=True)
    evs = events(series)
    if close_only:
        evs = [e for e in evs if e.endswith("H1600") or "H" not in e.split("-")[1]]
    todo = [e for e in evs if not (d / f"{e}.json").exists()]
    print(series, len(evs), "settled events,", len(todo), "to fetch", flush=True)

    def one(ev):
        f = d / f"{ev}.json"; ms = []
        try:
            for mk in markets(ev):
                rec = {k: mk.get(k) for k in KEEP}
                vol = float(mk.get("volume_fp") or mk.get("volume") or 0)
                rec["candles"] = candles(series, mk) if vol > 0 else []
                ms.append(rec)
        except Exception as e:                       # left for the next run
            print("  failed", ev, e, flush=True); return
        tmp = f.with_suffix(f".{threading.get_ident()}.tmp"); tmp.write_text(json.dumps({"event": ev, "markets": ms})); tmp.replace(f)

    with ThreadPoolExecutor(8) as ex:
        for i, _ in enumerate(ex.map(one, todo)):
            if i % 50 == 0:
                print(f"  {series} {i}/{len(todo)}", flush=True)


if __name__ == "__main__":
    for s in [a for a in sys.argv[1:] if not a.startswith("--")]:
        run(s, "--close-only" in sys.argv)
