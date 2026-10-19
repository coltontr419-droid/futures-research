"""M1: the prize for being first when a mention word is said — what takers earned buying YES at <= 90c in the jump to >= 95c.

    python -m futuresres.mention.m1_prize
"""

from __future__ import annotations

import collections
import datetime as dt
import glob
import json
import math
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "data" / "kalshi" / "mention_trades"


def T(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def fee(p: float) -> float:
    return math.ceil(7 * p * (1 - p)) / 100            # taker fee per contract, rounded up a cent (per 1-lot; conservative)


def jump(tr: list) -> dict | None:
    tr = sorted(tr, key=lambda x: x["created_time"])
    px = [float(x["yes_price_dollars"]) for x in tr]
    idx = max((i for i, p in enumerate(px) if p < 0.90), default=None)
    if idx is None or idx + 1 >= len(tr):
        return None
    t1 = T(tr[idx]["created_time"])
    win = [x for x in tr if t1 - dt.timedelta(seconds=10) <= T(x["created_time"]) <= t1 + dt.timedelta(seconds=2)]
    before = [float(x["yes_price_dollars"]) for x in tr if T(x["created_time"]) < t1 - dt.timedelta(seconds=10)][-20:]
    p0 = st.median(before) if before else None
    buys = [x for x in win if x["taker_side"] == "yes" and float(x["yes_price_dollars"]) <= 0.90]
    if not buys or p0 is None or p0 > 0.85:
        return None
    first_ts = min(x["created_time"] for x in buys)
    prize = sum(float(x["count_fp"]) * (1 - float(x["yes_price_dollars"]) - fee(float(x["yes_price_dollars"]))) for x in buys)
    first = sum(float(x["count_fp"]) * (1 - float(x["yes_price_dollars"]) - fee(float(x["yes_price_dollars"]))) for x in buys if x["created_time"] == first_ts)
    takers_ts = len({x["created_time"] for x in buys})
    secs = (T(max(x["created_time"] for x in buys)) - T(first_ts)).total_seconds()
    return {"p0": p0, "prize": prize, "first": first, "contracts": sum(float(x["count_fp"]) for x in buys), "orders": takers_ts, "span_s": secs, "t": first_ts}


def main() -> int:
    ev = []; allj = []
    for f in sorted(glob.glob(str(SRC / "*.json"))):
        d = json.load(open(f)); js = []
        for m in d["markets"]:
            j = jump(m["trades"])
            if j:
                j["word"] = m["word"]; js.append(j)
        if any(m["trades"] for m in d["markets"]):
            ev.append((d["event"], len(d["markets"]), js)); allj += js
    print(f"events with trades {len(ev)}; said words {sum(e[1] for e in ev)}; words with a jump from <= 85c: {len(allj)}")
    pz = [e and sum(j['prize'] for j in e[2]) for e in ev]
    print(f"prize per event (net of taker fee): mean ${st.mean(pz):,.0f} median ${st.median(pz):,.0f} max ${max(pz):,.0f}; total ${sum(pz):,.0f}")
    print(f"share taken by the FIRST instant (one sweep): {sum(j['first'] for j in allj)/max(sum(j['prize'] for j in allj),1):.0%}")
    print(f"per jump: median prize ${st.median([j['prize'] for j in allj]):,.0f}, median contracts {st.median([j['contracts'] for j in allj]):,.0f}, "
          f"median distinct taker instants {st.median([j['orders'] for j in allj])}, median span {st.median([j['span_s'] for j in allj]):.2f}s")
    for e, n, js in ev[-8:]:
        print(f"  {e}: {len(js)} jumps, prize ${sum(j['prize'] for j in js):,.0f}, first-sweep ${sum(j['first'] for j in js):,.0f}")
    (ROOT / "reports" / "m1_prize.json").write_text(json.dumps({"events": [(e, n, js) for e, n, js in ev]}, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
