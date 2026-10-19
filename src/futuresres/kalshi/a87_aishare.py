"""A87: Kalshi's OpenRouter market-share markets (settled on OpenRouter's public author-market-share, metric=requests, modality=text,
which updates within the week). How uncertain are the strikes late in the week? Hourly candles, settled events since the cutoff.

    python -m futuresres.kalshi.a87_aishare
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "4")
from kalshi_api import Client  # noqa: E402

SERIES = ["KXOPENSHARE", "KXANTHSHARE", "KXDEEPSHARE", "KXGOOGSHARE", "KXTENCENTSHARE", "KXXIAOMISHARE", "KXOPENSOURCESHARE", "KXTOKENUSE"]
OUT = ROOT / "data" / "kalshi" / "aishare"


def main() -> int:
    c = Client(); OUT.mkdir(parents=True, exist_ok=True); rows = []
    for s in SERIES:
        ms = c.req("GET", f"/markets?series_ticker={s}&status=settled&limit=1000").get("markets", [])
        for m in ms:
            f = OUT / f"{m['ticker']}.json"
            if not f.exists():
                close = int(dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp())
                d = c.req("GET", f"/series/{s}/markets/{m['ticker']}/candlesticks?start_ts={close - 8 * 86400}&end_ts={close}&period_interval=60")
                f.write_text(json.dumps({"market": {k: m.get(k) for k in ("ticker", "event_ticker", "result", "close_time", "volume_fp", "yes_sub_title", "floor_strike", "cap_strike")},
                                         "candles": d.get("candlesticks", [])}))
            rows.append(json.loads(f.read_text()))
    # hours before close -> price of the side that won, at that hour (yes ask / no ask from the candle close)
    B = [(96, 72), (72, 48), (48, 24), (24, 0)]
    agg = collections.defaultdict(lambda: [0, 0, 0.0, 0.0])        # bucket: [candles, uncertain (winner ask 10-90c), volume in uncertain candles, $ edge]
    for r in rows:
        m = r["market"]; won = m["result"]; close = dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
        for cd in r["candles"]:
            t = dt.datetime.fromtimestamp(cd["end_period_ts"], dt.timezone.utc); h = (close - t).total_seconds() / 3600
            ya = cd.get("yes_ask", {}).get("close_dollars"); yb = cd.get("yes_bid", {}).get("close_dollars")
            if ya is None or yb is None:
                continue
            ya, yb = float(ya), float(yb)
            ask_win = ya if won == "yes" else 1 - yb
            if not 0 < ask_win < 1:
                continue
            for lo, hi in B:
                if hi <= h < lo:
                    a = agg[(lo, hi)]; a[0] += 1
                    if 0.10 <= ask_win <= 0.90:
                        a[1] += 1; v = float(cd.get("volume_fp") or cd.get("volume") or 0); a[2] += v; a[3] += v * (1 - ask_win)
    print(f"settled markets {len(rows)} in {len({r['market']['event_ticker'] for r in rows})} events")
    for (lo, hi), a in sorted(agg.items(), reverse=True):
        print(f"  {lo:3}-{hi:2}h before close: hourly candles {a[0]:5} | winner's ask 10-90c in {a[1]:4} ({a[1]/max(a[0],1):.0%}) | volume there {a[2]:9,.0f} | "
              f"buying the winner at the ask on that volume: ${a[3]:8,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
