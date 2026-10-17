"""NBM (NBS text) daytime-maximum forecasts from the Iowa Environmental Mesonet archive (free) for the Kalshi weather stations
(decisions.md 672): rows with TXN, every run hour, saved as data/kalshi/nbm/<station>.csv (runtime, ftime, txn, xnd).

    python -m futuresres.kalshi.nbm
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "kalshi" / "nbm"
STATIONS = ("KNYC", "KMDW", "KMIA", "KAUS", "KLAX", "KDEN", "KPHL")
URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/mos.py?station={s}&model=NBS&sts={a}T00:00Z&ets={b}T00:00Z&format=csv"


def fetch(s: str, a: dt.date, b: dt.date) -> list[dict]:
    for k in range(5):
        try:
            txt = urllib.request.urlopen(urllib.request.Request(URL.format(s=s, a=a, b=b), headers={"User-Agent": "futures-research"}), timeout=180).read().decode()
            return [r for r in csv.DictReader(io.StringIO(txt)) if r.get("txn") not in (None, "")]
        except Exception:
            time.sleep(5 * (k + 1))
    raise RuntimeError((s, a, b))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in STATIONS:
        f = OUT / f"{s}.csv"
        if f.exists():
            continue
        rows = []; a = dt.date(2021, 7, 1)
        while a < dt.date(2026, 10, 18):
            b = min(a + dt.timedelta(days=60), dt.date(2026, 10, 18))
            rows += [{k: r[k] for k in ("runtime", "ftime", "txn", "xnd")} for r in fetch(s, a, b)]; a = b; time.sleep(1)
        tmp = f.with_suffix(".tmp")
        with tmp.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["runtime", "ftime", "txn", "xnd"]); w.writeheader(); w.writerows(rows)
        tmp.replace(f); print(s, len(rows), "rows", flush=True)


if __name__ == "__main__":
    main()
