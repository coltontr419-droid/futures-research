"""A86: Kalshi series in data-publication categories ranked by settled volume since the history cutoff (screen for leading signals).

    python -m futuresres.kalshi.a86_rank
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "4")
from kalshi_api import Client  # noqa: E402

CATS = {"Entertainment", "Science and Technology", "Companies", "Social", "Health", "Transportation", "Exotics", "Culture", "Business"}
OUT = ROOT / "reports" / "a86_rank.json"


def main() -> int:
    c = Client(); ss, cur = [], None
    for _ in range(40):
        d = c.req("GET", "/series?limit=1000" + (f"&cursor={cur}" if cur else ""))
        ss += [x for x in d.get("series", []) if x.get("category") in CATS]; cur = d.get("cursor")
        if not cur:
            break
    rows = json.loads(OUT.read_text()) if OUT.exists() else {}
    for i, x in enumerate(ss):
        if x["ticker"] in rows:
            continue
        vol, n, ev, cur = 0.0, 0, set(), None
        for _ in range(20):
            d = c.req("GET", f"/markets?series_ticker={x['ticker']}&status=settled&limit=1000" + (f"&cursor={cur}" if cur else ""))
            ms = d.get("markets", []); n += len(ms); vol += sum(float(m.get("volume_fp") or 0) for m in ms); ev |= {m["event_ticker"] for m in ms}
            cur = d.get("cursor")
            if not cur or not ms:
                break
        rows[x["ticker"]] = {"title": x.get("title"), "category": x.get("category"), "events": len(ev), "markets": n, "volume": vol}
        if i % 200 == 0:
            OUT.write_text(json.dumps(rows)); print(i, "/", len(ss), flush=True)
    OUT.write_text(json.dumps(rows))
    for t, r in sorted(rows.items(), key=lambda kv: -kv[1]["volume"])[:50]:
        print(f"{t:26} {r['category'][:12]:12} events {r['events']:4} vol {r['volume']:12,.0f} | {r['title'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
