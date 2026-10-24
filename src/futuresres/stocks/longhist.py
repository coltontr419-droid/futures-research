"""Long daily history (2015-2026, adjusted) for the most liquid US stocks — infrastructure for stock families (decisions.md 942).

    python -m futuresres.stocks.longhist
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
H2 = ROOT / "data" / "stocks" / "h2" / "daily.jsonl"
OUT = ROOT / "data" / "stocks" / "long" / "daily.jsonl"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    liq = []
    for l in open(H2):
        x = json.loads(l)
        if x.get("err") or not x.get("c"):
            continue
        dv = [c * v for c, v in zip(x["c"][-60:], x["v"][-60:]) if c and v]
        if dv and float(np.median(dv)) >= 20e6:
            liq.append(x["sym"])
    done = {json.loads(l)["sym"] for l in open(OUT)} if OUT.exists() else set()
    print("liquid symbols", len(liq), "to fetch", len([s for s in liq if s not in done]), flush=True)
    with open(OUT, "a") as f:
        for i, s in enumerate(liq):
            if s in done:
                continue
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval=1d&period1=1420070400&period2=1792800000&events=div,split"
            for k in range(4):
                try:
                    r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())["chart"]["result"][0]
                    q = r["indicators"]["quote"][0]; adj = r["indicators"]["adjclose"][0]["adjclose"]
                    f.write(json.dumps({"sym": s, "t": r["timestamp"], "o": q["open"], "c": q["close"], "a": adj, "v": q["volume"]}) + "\n"); break
                except Exception:
                    time.sleep(2 ** k)
            time.sleep(0.3)
            if i % 100 == 0:
                f.flush(); print(f"  {i}/{len(liq)}", flush=True)


if __name__ == "__main__":
    main()
