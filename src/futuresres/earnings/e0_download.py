"""E-family 1 data (decisions.md 752): every settled Kalshi earnings-mention market (live + /historical) with its public trades.
One JSON per event under data/kalshi/earnings/. Resumable.

    python -m futuresres.earnings.e0_download
"""

from __future__ import annotations

import collections
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "5")
from kalshi_api import Client  # noqa: E402

from futuresres.mention.m0_download import trades  # noqa: E402

OUT = ROOT / "data" / "kalshi" / "earnings"


def retry(f, *a):
    for k in range(8):
        try:
            return f(*a)
        except Exception as e:                                        # noqa: BLE001
            if "429" not in str(e) and "Remote" not in str(e) and "timed out" not in str(e):
                raise
            time.sleep(6 * (k + 1))
    raise RuntimeError("gave up")


def settled(c, s):
    out = []
    for base, extra in (("/markets", "&status=settled"), ("/historical/markets", "")):
        cur = None
        for _ in range(20):
            d = retry(c.req, "GET", f"{base}?series_ticker={s}&limit=1000{extra}" + (f"&cursor={cur}" if cur else ""))
            out += d.get("markets", []); cur = d.get("cursor")
            if not cur or not d.get("markets"):
                break
    return out


def main() -> int:
    c = Client(); OUT.mkdir(parents=True, exist_ok=True)
    series = sorted(s for s in json.loads((ROOT / "data/kalshi/mention_series/rank.json").read_text()) if "EARN" in s)
    print("series", len(series), flush=True)
    for s in series:
        ev = collections.defaultdict(list)
        for m in settled(c, s):
            if m.get("result") in ("yes", "no"):
                ev[m["event_ticker"]].append(m)
        for e, ms in ev.items():
            f = OUT / f"{e}.json"
            if f.exists():
                continue
            f.write_text(json.dumps({"event": e, "series": s, "markets": [
                {"ticker": m["ticker"], "word": m.get("yes_sub_title"), "result": m["result"], "open": m.get("open_time"),
                 "close": m.get("close_time"), "rules": (m.get("rules_primary") or "")[:400], "trades": retry(trades, c, m["ticker"])} for m in ms]}))
        print(s, len(ev), "events", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
