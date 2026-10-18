"""A82 (decisions.md 708): settled markets of the last 45 days in the short series, their results, and their public trades at the
extremes (yes price <= 3c or >= 97c). Resumable: one JSON per event under data/kalshi/taker/<series>/.

    python -m futuresres.kalshi.a82_download
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "10")
from kalshi_api import Client  # noqa: E402

OUT = ROOT / "data" / "kalshi" / "taker"
DAYS = 45
HIGHS = ("KXHIGHNY", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHAUS", "KXHIGHLAX", "KXHIGHDEN", "KXHIGHPHIL")


def series_list(c: Client) -> list[str]:
    out, cur = [], None
    for _ in range(40):
        d = c.req("GET", "/series?limit=1000" + (f"&cursor={cur}" if cur else ""))
        out += [x["ticker"] for x in d.get("series", [])]; cur = d.get("cursor") or d.get("next_cursor")
        if not cur or not d.get("series"):
            break
    gas = sorted(x for x in out if x.startswith("KXAAAGASD") and len(x) == 11)
    return gas + ["KXTEMPMIAH", "KXEOWEEK"] + list(HIGHS)


def event_date(ev: str):
    for part in ev.split("-")[1:]:                     # the date is always the first 7 characters (YYMONDD), an hour may follow
        try:
            return dt.datetime.strptime(part[:7], "%y%b%d").date()
        except ValueError:
            continue
    return None


def events(c: Client, series: str, since: dt.datetime) -> list[str]:
    """Settled events newest first, stopping at the cutoff (events are listed newest first)."""
    out, cur = [], None
    for _ in range(50):
        d = c.req("GET", f"/events?series_ticker={series}&status=settled&limit=200" + (f"&cursor={cur}" if cur else ""))
        evs = d.get("events", []); cur = d.get("cursor")
        old = False
        for e in evs:
            d = event_date(e["event_ticker"])
            if d is not None and d < since.date():
                old = True; break
            out.append(e["event_ticker"])
        if old or not cur or not evs:
            break
        if len(out) > 3000:
            break
    return out


def markets(c: Client, ev: str) -> list[dict]:
    for base in ("/markets", "/historical/markets"):
        try:
            m = c.req("GET", f"{base}?event_ticker={ev}&limit=200").get("markets", [])
        except Exception:
            m = []
        if m:
            return m
    return []


def trades(c: Client, ticker: str) -> list:
    out, cur = [], None
    for _ in range(30):
        d = c.req("GET", f"/markets/trades?ticker={ticker}&limit=1000" + (f"&cursor={cur}" if cur else ""))
        for t in d.get("trades", []):
            yp = float(t.get("yes_price_dollars") or 0)
            if yp <= 0.0301 or yp >= 0.9699:
                out.append([t.get("created_time"), yp, t.get("taker_outcome_side") or t.get("taker_side"), float(t.get("count_fp") or 0)])
        cur = d.get("cursor")
        if not cur or not d.get("trades"):
            break
    return out


def main() -> int:
    c = Client(); since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=DAYS)
    todo = []
    for s in series_list(c):
        (OUT / s).mkdir(parents=True, exist_ok=True)
        for ev in events(c, s, since):
            if not (OUT / s / f"{ev}.json").exists():
                todo.append((s, ev))
    print(len(todo), "events to fetch", flush=True)
    done = [0]; lock = threading.Lock()

    def one(item):
        s, ev = item
        try:
            ms = markets(c, ev)
            if not ms:
                return
            close = max((m.get("close_time") or "") for m in ms)
            if close and dt.datetime.fromisoformat(close.replace("Z", "+00:00")) < since:
                (OUT / s / f"{ev}.json").write_text(json.dumps({"event": ev, "old": True})); return
            rows = []
            for m in ms:
                if m.get("result") not in ("yes", "no"):
                    continue
                rows.append({"ticker": m["ticker"], "close": m.get("close_time"), "result": m["result"], "trades": trades(c, m["ticker"])})
            (OUT / s / f"{ev}.json").write_text(json.dumps({"event": ev, "markets": rows}))
        except Exception as e:
            print("failed", ev, str(e)[:120], flush=True)
        with lock:
            done[0] += 1
            if done[0] % 200 == 0:
                print(f"  {done[0]}/{len(todo)}", flush=True)

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(one, todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
