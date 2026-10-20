"""Lean prop download: for each settled market only the last hourly candle 9 h -> 6 h before the close (the one K11 trades on).

Markets closing after Kalshi's historical cutoff come 100 at a time from /markets/candlesticks; older ones one by one, sampled by
event (--sample N keeps N random events a series). Output: data/kalshi/lean/<SERIES>.jsonl, one row a market, resumable.

    python -m futuresres.kalshi.lean KXNBAPTS KXMLBHR ... [--sample 150] [--since 2026-08-20] [--before 2026-08-20] [--start] [--rate 5]

--start (esports, decisions.md 774-775): the window is instead 4 h -> 1 h before the match's scheduled start, read from the event ticker
(e.g. KXLOLGAME-26OCT181400MVKKC = 2026-10-18 14:00 ET), and rows go to data/kalshi/lean_start/.
"""

from __future__ import annotations

import datetime as dt
import json
import random
import sys
import re
import urllib.error
from zoneinfo import ZoneInfo

from futuresres.kalshi import download
from futuresres.kalshi.download import OUT, get

LEAN = OUT / "lean"
START = False


def T(s: str) -> int:
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def listing(series: str) -> list[dict]:
    out = []
    for base in ("/historical/markets", "/markets"):
        cur = None
        while True:
            d = get(f"{base}?series_ticker={series}&limit=1000" + ("&status=settled" if base == "/markets" else "") + (f"&cursor={cur}" if cur else ""))
            out += [m for m in d.get("markets", []) if m.get("result") in ("yes", "no") and m.get("close_time")]
            cur = d.get("cursor")
            if not cur or not d.get("markets"):
                break
    seen = set(); uniq = []
    for m in out:
        if m["ticker"] not in seen:
            seen.add(m["ticker"]); uniq.append(m)
    return uniq


def start(m: dict) -> int | None:
    g = re.match(r"(\d{2}[A-Z]{3}\d{2})(\d{4})", m["event_ticker"].split("-")[1])
    if not g:
        return None
    d = dt.datetime.strptime(g.group(1) + g.group(2), "%y%b%d%H%M").replace(tzinfo=ZoneInfo("America/New_York"))
    return int(d.timestamp())


def window(m: dict) -> tuple[int, int] | None:
    if START:
        s = start(m)
        return (s - 4 * 3600, s - 3600) if s else None
    cl = T(m["close_time"])
    return cl - 9 * 3600, cl - 6 * 3600


def pick(cs: list, w: tuple[int, int]) -> dict | None:
    cs = [c for c in cs if w[0] <= int(c["end_period_ts"]) <= w[1]]
    return max(cs, key=lambda c: int(c["end_period_ts"])) if cs else None


def row(m: dict, c: dict | None) -> dict:
    return {"ticker": m["ticker"], "event": m.get("event_ticker"), "close": m["close_time"], "result": m["result"], "start": start(m) if START else None,
            "volume": float(m.get("volume_fp") or m.get("volume") or 0), "candle": c}


def run(series: str, sample: int | None, since: str | None, before: str | None = None) -> None:
    d_ = OUT / "lean_start" if START else LEAN; d_.mkdir(parents=True, exist_ok=True); f = d_ / f"{series}.jsonl"
    done = {json.loads(l)["ticker"] for l in open(f)} if f.exists() else set()
    ms = [m for m in listing(series) if m["ticker"] not in done and float(m.get("volume_fp") or m.get("volume") or 0) > 0 and window(m)]
    if since:
        ms = [m for m in ms if m["close_time"] >= since]
    if before:
        ms = [m for m in ms if m["close_time"] < before]
    if sample:
        evs = sorted({m["event_ticker"] for m in ms}); random.Random(series).shuffle(evs); keep = set(evs[:sample])
        ms = [m for m in ms if m["event_ticker"] in keep]
    print(series, len(ms), "markets to fetch", flush=True)
    hist = []; out = open(f, "a"); n = 0
    pending = sorted(ms, key=lambda m: window(m)[1])
    for i in range(0, len(pending), 100):                      # batch first; what it does not return is historical
        chunk = pending[i:i + 100]; lo = min(window(m)[0] for m in chunk); hi = max(window(m)[1] for m in chunk)
        try:
            d = get(f"/markets/candlesticks?market_tickers={','.join(m['ticker'] for m in chunk)}&start_ts={lo}&end_ts={hi}&period_interval=60")
        except Exception:
            d = {}
        got = {x.get("market_ticker") or x.get("ticker"): x.get("candlesticks", []) for x in d.get("markets", [])}
        for m in chunk:
            if m["ticker"] in got and got[m["ticker"]]:
                out.write(json.dumps(row(m, pick(got[m["ticker"]], window(m)))) + "\n"); n += 1
            else:
                hist.append(m)
    out.flush()
    print(f"  batch {n}, one-by-one {len(hist)}", flush=True)
    for j, m in enumerate(hist):
        w = window(m); c = None
        for u in (f"/historical/markets/{m['ticker']}/candlesticks", f"/series/{series}/markets/{m['ticker']}/candlesticks"):
            try:
                c = pick(get(f"{u}?start_ts={w[0]}&end_ts={w[1]}&period_interval=60").get("candlesticks", []), w); break
            except (urllib.error.HTTPError, RuntimeError):
                continue
        out.write(json.dumps(row(m, c)) + "\n")
        if j % 200 == 0:
            out.flush(); print(f"  {series} {j}/{len(hist)}", flush=True)
    out.close()


if __name__ == "__main__":
    a = sys.argv[1:]; sample = since = None
    if "--sample" in a:
        i = a.index("--sample"); sample = int(a[i + 1]); del a[i:i + 2]
    if "--since" in a:
        i = a.index("--since"); since = a[i + 1]; del a[i:i + 2]
    before = None
    if "--start" in a:
        a.remove("--start"); START = True
    if "--rate" in a:
        i = a.index("--rate"); download.RATE = float(a[i + 1]); del a[i:i + 2]
    if "--before" in a:
        i = a.index("--before"); before = a[i + 1]; del a[i:i + 2]
    for s in a:
        run(s, sample, since, before)
