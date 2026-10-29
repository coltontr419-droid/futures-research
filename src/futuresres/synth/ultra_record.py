"""Record Binance spot best bid/ask (book ticker) and aggregate trades for Synth Ultra model tests (decisions.md §1170). Public market-data mirror.

    python -m futuresres.synth.ultra_record <minutes> <symbols e.g. btcusdt,ethusdt>
"""

from __future__ import annotations

import gzip
import json
import sys
import time
from pathlib import Path

from curl_cffi.requests import Session

OUT = Path(__file__).resolve().parents[3] / "data" / "ultra"


def main(minutes: float, symbols: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    streams = "/".join(f"{s}@bookTicker/{s}@aggTrade" for s in symbols)
    f = gzip.open(OUT / f"rec_{int(time.time())}.jsonl.gz", "wt"); end = time.time() + minutes * 60; last = {}
    while time.time() < end:
        try:
            ws = Session(impersonate="chrome").ws_connect(f"wss://data-stream.binance.vision/stream?streams={streams}", timeout=30)
            while time.time() < end:
                d = json.loads(ws.recv()[0]); now = int(time.time() * 1000); s = d["stream"]; x = d["data"]
                if s.endswith("bookTicker"):
                    key = (x["b"], x["B"], x["a"], x["A"])
                    if last.get(s) == key:
                        continue
                    last[s] = key; f.write(json.dumps({"t": now, "s": x["s"], "k": "b", "b": float(x["b"]), "B": float(x["B"]), "a": float(x["a"]), "A": float(x["A"])}) + "\n")
                else:
                    f.write(json.dumps({"t": now, "T": x["T"], "s": x["s"], "k": "t", "p": float(x["p"]), "q": float(x["q"]), "m": x["m"]}) + "\n")
        except Exception as e:                                   # reconnect on drops
            print("reconnect", repr(e)[:120], flush=True); time.sleep(2)
    f.close()


if __name__ == "__main__":
    main(float(sys.argv[1]), sys.argv[2].split(","))
