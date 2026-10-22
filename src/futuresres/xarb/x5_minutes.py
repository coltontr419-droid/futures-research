"""X5 (decisions.md 851): minute-level Coinbase vs Bitstamp gaps on random 2026 days — capacity upper bound.

    python -m futuresres.xarb.x5_minutes
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import random
import time
from pathlib import Path

from futuresres.xarb.x1_snapshot import get
from futuresres.xarb.x3_listings import CB, candles

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "xarb" / "x5"


def bitstamp_minutes(pair: str, day: dt.datetime) -> dict:
    out = {}; s = int(day.timestamp())
    for k in range(2):
        time.sleep(0.4)
        try:
            d = get(f"https://www.bitstamp.net/api/v2/ohlc/{pair}/?step=60&limit=1000&start={s + 60000 * k}")["data"]["ohlc"]
        except Exception:
            continue
        for x in d:
            t = int(x["timestamp"])
            if s <= t < s + 86400 and float(x["volume"]) > 0:
                out[t] = (float(x["close"]), float(x["close"]) * float(x["volume"]))
    return out


def main() -> None:
    DIR.mkdir(parents=True, exist_ok=True); f = DIR / "minutes.jsonl"
    done = {(json.loads(l)["pair"], json.loads(l)["day"]) for l in open(f)} if f.exists() else set()
    bs = {x["url_symbol"]: x["name"].split("/")[0] for x in get("https://www.bitstamp.net/api/v2/trading-pairs-info/") if x["name"].endswith("/USD") and x.get("trading") == "Enabled"}
    cb = {p["base_currency"]: p["id"] for p in get(f"{CB}/products") if p["quote_currency"] == "USD" and p["status"] == "online"}
    pairs = sorted((u, b) for u, b in bs.items() if b in cb)
    rng = random.Random(851); d0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    days = sorted(d0 + dt.timedelta(days=x) for x in rng.sample(range(292), 20))
    print("pairs", len(pairs), "days", len(days), flush=True)
    with open(f, "a") as fh:
        for day in days:
            for u, b in pairs:
                if (u, day.date().isoformat()) in done:
                    continue
                B = bitstamp_minutes(u, day); C = {}
                for k in range(5):
                    for x in candles(cb[b], day + dt.timedelta(minutes=300 * k), 60, 300):
                        if x[5] > 0 and day.timestamp() <= x[0] < day.timestamp() + 86400:
                            C[int(x[0])] = (x[4], x[4] * x[5])
                agg = collections.defaultdict(float); n = 0
                for t, (bc, bu) in B.items():
                    c = C.get(t)
                    if not c:
                        continue
                    n += 1; g = abs(c[0] / bc - 1); cap = min(0.1 * c[1], 0.1 * bu)
                    for lab, fee in (("base", 0.016), ("tier", 0.008)):
                        if g > fee:
                            agg[lab] += cap * (g - fee)
                fh.write(json.dumps({"pair": u, "day": day.date().isoformat(), "matched": n, **agg}) + "\n"); fh.flush()
            print(day.date(), "done", flush=True)
    rows = [json.loads(l) for l in open(f)]
    for lab in ("base", "tier"):
        tot = sum(r.get(lab, 0.0) for r in rows); top = sorted(((r.get(lab, 0.0), r["pair"], r["day"]) for r in rows), reverse=True)[:8]
        print(f"{lab}: capturable over {len(days)} days ${tot:,.0f} → ${tot / len(days) * 30.4:,.0f}/month; top {[(round(a), p, d) for a, p, d in top]}")


if __name__ == "__main__":
    main()
