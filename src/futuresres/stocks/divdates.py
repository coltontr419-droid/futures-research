"""Ex-dividend dates 2014-2026 for the packed long-history universe (decisions.md 947). Small payloads: interval=3mo, events=div.

    python -m futuresres.stocks.divdates
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "stocks" / "long" / "divs.jsonl"


def main() -> None:
    syms = list(np.load(ROOT / "data" / "stocks" / "long" / "pack.npz")["syms"])
    done = {json.loads(l)["sym"] for l in open(OUT)} if OUT.exists() else set()
    with open(OUT, "a") as f:
        for i, s in enumerate(syms):
            if s in done:
                continue
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval=3mo&period1=1388534400&period2=1792800000&events=div"
            for k in range(4):
                try:
                    r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())["chart"]["result"][0]
                    dv = (r.get("events") or {}).get("dividends") or {}
                    f.write(json.dumps({"sym": s, "ex": sorted(dt.datetime.fromtimestamp(int(v["date"]), dt.timezone.utc).date().isoformat() for v in dv.values())}) + "\n"); break
                except Exception:
                    time.sleep(2 ** k)
            time.sleep(0.25)
            if i % 200 == 0:
                f.flush(); print(f"  {i}/{len(syms)}", flush=True)


if __name__ == "__main__":
    main()
