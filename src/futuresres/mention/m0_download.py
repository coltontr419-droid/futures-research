"""M0: every public trade in KXTRUMPMENTION markets that resolved Yes (the word was said), for the live-mention latency screen.
Resumable: one JSON per event under data/kalshi/mention_trades/.

    python -m futuresres.mention.m0_download [n_latest_events]
"""

from __future__ import annotations

import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "10")
from kalshi_api import Client  # noqa: E402

SRC = ROOT / "data" / "kalshi" / "KXTRUMPMENTION"
OUT = ROOT / "data" / "kalshi" / "mention_trades"


def trades(c: Client, ticker: str, base: str = "/markets/trades") -> list:
    """Live endpoint first; trades before Kalshi's historical cutoff (2026-08-19) are only under /historical/trades."""
    out, cur = [], None
    for _ in range(200):
        d = c.req("GET", f"{base}?ticker={ticker}&limit=1000" + (f"&cursor={cur}" if cur else ""))
        for t in d.get("trades", []):
            out.append({k: t.get(k) for k in ("created_time", "yes_price_dollars", "no_price_dollars", "count_fp", "taker_side")})
        cur = d.get("cursor")
        if not cur or not d.get("trades"):
            break
    if not out and base == "/markets/trades":
        return trades(c, ticker, "/historical/trades")
    return out


def one(c: Client, f: str, result: str = "yes") -> str:
    """Trades of the event's markets that resolved `result` ("yes": the word was said; "no": never said - saved as <event>.no.json)."""
    ev = Path(f).stem; dest = OUT / (f"{ev}.json" if result == "yes" else f"{ev}.no.json")
    if dest.exists() and any(m["trades"] for m in json.load(open(dest))["markets"]):
        return ev + " cached"
    d = json.load(open(f)); rows = []
    for m in d["markets"]:
        if m.get("result") == result:
            rows.append({"ticker": m["ticker"], "word": m.get("yes_sub_title"), "open": m.get("open_time"), "close": m.get("close_time"),
                         "volume": m.get("volume_fp"), "trades": trades(c, m["ticker"])})
    dest.write_text(json.dumps({"event": ev, "title": d["markets"][0].get("title") if d["markets"] else None, "markets": rows}))
    return f"{ev} {len(rows)} yes-markets {sum(len(r['trades']) for r in rows)} trades"


def main(argv) -> int:
    OUT.mkdir(parents=True, exist_ok=True); c = Client()
    result = "no" if "--no" in argv else "yes"; argv = [a for a in argv if a != "--no"]
    fs = sorted(glob.glob(str(SRC / "*.json")), key=lambda f: json.load(open(f))["markets"][0].get("close_time") or "")
    fs = fs[-int(argv[0]):] if argv else fs
    with ThreadPoolExecutor(4) as ex:
        for msg in ex.map(lambda f: one(c, f, result), fs):
            print(msg, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
