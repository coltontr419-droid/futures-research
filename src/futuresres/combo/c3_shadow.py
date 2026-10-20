"""C-family 1 shadow analysis (decisions.md 744): sampled live RFQs (droplet logger) joined to their outcome — did the combo trade,
at what price and side, how did it settle — and priced from the leg books at RFQ time.

    python -m futuresres.combo.c3_shadow [n_sample]
"""

from __future__ import annotations

import collections
import json
import math
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "6")
from kalshi_api import Client  # noqa: E402

SH = ROOT / "data" / "kalshi" / "rfq_shadow"


def retry(f, *a):
    for k in range(6):
        try:
            return f(*a)
        except Exception as e:                                       # noqa: BLE001
            if "404" in str(e):
                return None
            time.sleep(4 * (k + 1))
    return None


def load(n: int):
    """Two streaming passes (the laptop has 2 GB): ids with a leg snapshot, then only the sampled records."""
    with_legs = set()
    for f in sorted(SH.glob("rfq_*.jsonl")):
        for l in open(f):
            if '"kind":"legs"' in l[:20]:
                with_legs.add(l.split('"rfq_id":"', 1)[1][:36])
    random.seed(744); keep = set(random.sample(sorted(with_legs), min(n, len(with_legs))))
    rfq, legs = {}, {}
    for f in sorted(SH.glob("rfq_*.jsonl")):
        for l in open(f):
            if '"kind":"rfq"' in l[:20] or '"kind":"legs"' in l[:20]:
                r = json.loads(l)
                if r["kind"] == "rfq" and r["id"] in keep:
                    rfq[r["id"]] = r
                elif r["kind"] == "legs" and r["rfq_id"] in keep:
                    legs[r["rfq_id"]] = r["legs"]
    return rfq, legs


def main(argv) -> int:
    n = int(argv[0]) if argv else 3000
    rfq, legs = load(n); ids = sorted(i for i in rfq if i in legs)
    c = Client(); out = []; cache = SH / "c3_markets.json"; mk = json.loads(cache.read_text()) if cache.exists() else {}
    for k, i in enumerate(ids):
        t = rfq[i]["market_ticker"]
        if t not in mk:
            d = retry(c.req, "GET", f"/markets/{t}"); mk[t] = (d or {}).get("market")
            if k % 200 == 0:
                cache.write_text(json.dumps(mk)); print(k, flush=True)
        m = mk[t]
        if not m:
            continue
        out.append({"id": i, "ticker": t, "volume": float(m.get("volume_fp") or 0), "status": m.get("status"), "result": m.get("result"),
                    "last": float(m.get("last_price_dollars") or 0), "legs": legs[i], "sel": rfq[i].get("mve_selected_legs"),
                    "contracts": rfq[i].get("contracts_fp"), "target": rfq[i].get("target_cost_dollars"), "created": rfq[i].get("created_ts")})
    cache.write_text(json.dumps(mk))
    (SH / "c3_sample.json").write_text(json.dumps(out))
    traded = [o for o in out if o["volume"] > 0]
    print(f"sampled RFQs {len(out)}; the combo traded at all: {len(traded)} ({len(traded)/max(len(out),1):.1%}); settled among traded: "
          f"{sum(1 for o in traded if o['result'] in ('yes','no'))}; total volume of traded {sum(o['volume'] for o in traded):,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
