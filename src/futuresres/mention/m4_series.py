"""M4: every Kalshi mention-style series ranked by settled volume, then the first-taker prize and jump speed per series.

    python -m futuresres.mention.m4_series rank
    python -m futuresres.mention.m4_series prize N      # top N series by volume (trades of YES-resolved markets)
"""

from __future__ import annotations

import collections
import json
import os
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "4")
from kalshi_api import Client  # noqa: E402

from futuresres.mention.m0_download import trades  # noqa: E402
from futuresres.mention.m1_prize import jump  # noqa: E402

OUT = ROOT / "data" / "kalshi" / "mention_series"


def series(c: Client) -> list[str]:
    out, cur = [], None
    for _ in range(40):
        d = c.req("GET", "/series?limit=1000" + (f"&cursor={cur}" if cur else ""))
        out += [x["ticker"] for x in d.get("series", []) if re.search(r"MENTION|SAY", x["ticker"]) or re.search(r"\bsay\b|mention", x.get("title", ""), re.I)]
        cur = d.get("cursor")
        if not cur:
            return out
    return out


def settled(c: Client, s: str) -> list[dict]:
    out, cur = [], None
    for _ in range(50):
        d = c.req("GET", f"/markets?series_ticker={s}&status=settled&limit=1000" + (f"&cursor={cur}" if cur else ""))
        out += d.get("markets", []); cur = d.get("cursor")
        if not cur or not d.get("markets"):
            return out
    return out


def rank() -> None:
    c = Client(); OUT.mkdir(parents=True, exist_ok=True); rows = {}
    for s in series(c):
        ms = settled(c, s)
        rows[s] = {"markets": len(ms), "events": len({m["event_ticker"] for m in ms}), "volume": sum(float(m.get("volume_fp") or 0) for m in ms),
                   "yes": [m["ticker"] for m in ms if m.get("result") == "yes"], "last": max((m.get("close_time") or "" for m in ms), default="")}
    (OUT / "rank.json").write_text(json.dumps(rows))
    for s, r in sorted(rows.items(), key=lambda kv: -kv[1]["volume"])[:40]:
        print(f"{s:28} events {r['events']:4} markets {r['markets']:5} yes {len(r['yes']):4} volume {r['volume']:12,.0f} last {r['last'][:10]}")


def prize(n: int) -> None:
    c = Client(); rows = json.loads((OUT / "rank.json").read_text())
    for s, r in sorted(rows.items(), key=lambda kv: -kv[1]["volume"])[:n]:
        f = OUT / f"{s}.json"
        if not f.exists():
            f.write_text(json.dumps({t: trades(c, t) for t in r["yes"]}))
        T = json.loads(f.read_text()); js = [j for j in (jump(v) for v in T.values()) if j]
        ev = collections.defaultdict(float)
        for t, v in T.items():
            j = jump(v)
            if j:
                ev[t.rsplit("-", 1)[0]] += j["prize"]
        if not js:
            print(f"{s:28} no jumps"); continue
        print(f"{s:28} events {r['events']:4} jumps {len(js):4} | prize total ${sum(j['prize'] for j in js):9,.0f}, per event ${sum(ev.values())/max(r['events'],1):7,.0f} | "
              f"span median {st.median([j['span_s'] for j in js]):5.2f}s p75 {sorted(j['span_s'] for j in js)[3*len(js)//4]:6.2f}s | first {sum(j['first'] for j in js)/max(sum(j['prize'] for j in js),1):.0%} | "
              f"takers {st.median([j['orders'] for j in js])}", flush=True)


if __name__ == "__main__":
    rank() if sys.argv[1] == "rank" else prize(int(sys.argv[2]))
