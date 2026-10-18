"""A83 (decisions.md 710): strike type, strike and settled value for every state daily gas market in the A82 download."""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "4")
from kalshi_api import Client  # noqa: E402

IN = ROOT / "data" / "kalshi" / "taker"
OUT = ROOT / "data" / "kalshi" / "gas_meta.json"


def main() -> int:
    c = Client(); meta = json.loads(OUT.read_text()) if OUT.exists() else {}
    evs = [f.stem for d in IN.iterdir() if d.name.startswith("KXAAAGASD") for f in d.glob("*.json") if f.stem not in meta]
    print(len(evs), "events to fetch", flush=True)

    def one(ev):
        for base in ("/markets", "/historical/markets"):
            try:
                ms = c.req("GET", f"{base}?event_ticker={ev}&limit=200").get("markets", [])
            except Exception:
                ms = []
            if ms:
                return ev, {m["ticker"]: {"type": m.get("strike_type"), "floor": m.get("floor_strike"), "cap": m.get("cap_strike"),
                                          "value": m.get("expiration_value"), "result": m.get("result")} for m in ms}
        return ev, None

    with ThreadPoolExecutor(4) as ex:
        for i, (ev, d) in enumerate(ex.map(one, evs)):
            if d:
                meta[ev] = d
            if i % 300 == 0:
                OUT.write_text(json.dumps(meta)); print(f"  {i}/{len(evs)}", flush=True)
    OUT.write_text(json.dumps(meta)); print("done", len(meta), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
