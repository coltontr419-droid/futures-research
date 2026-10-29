"""S-family 1 (decisions.md §1113): aggregate short interest (FINRA, 2018-12 →) as a half-monthly long/short sign for MNQ (QQQ proxy).

    python -m futuresres.stocks.s1_shortint fetch        # FINRA settlement-date files into data/stocks/s1/
    python -m futuresres.stocks.s1_shortint [validate]   # discovery (or the one sealed read)
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
from curl_cffi import requests

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "stocks" / "s1"
API = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
HDR = {"Content-Type": "application/json", "Accept": "application/json"}
SEAL, LAG, WARM = "2023-01", 10, 24


def post(body):
    for k in range(5):
        r = requests.post(API, headers=HDR, data=json.dumps(body), timeout=60)
        if r.status_code == 204:
            return []
        if r.status_code == 200:
            return r.json() if r.text.strip() else []
        time.sleep(5 * (k + 1))
    raise RuntimeError(r.status_code)


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    syms = set(np.load(ROOT / "data" / "stocks" / "long" / "pack.npz")["syms"].tolist())
    dates = set()
    for y in range(2018, dt.date.today().year + 1):
        for m in range(1, 13):
            a = dt.date(y, m, 1); b = (a + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
            rows = post({"limit": 5000, "fields": ["settlementDate"], "compareFilters": [{"compareType": "EQUAL", "fieldName": "symbolCode", "fieldValue": "AAPL"}],
                         "dateRangeFilters": [{"fieldName": "settlementDate", "startDate": str(a), "endDate": str(b)}]})
            dates |= {r["settlementDate"] for r in rows}
    print(len(dates), "settlement dates", flush=True)
    for d in sorted(dates):
        f = OUT / f"{d}.json"
        if f.exists():
            continue
        got, off = [], 0
        while True:
            rows = post({"limit": 5000, "offset": off, "fields": ["symbolCode", "currentShortPositionQuantity", "averageDailyVolumeQuantity", "daysToCoverQuantity"],
                         "compareFilters": [{"compareType": "EQUAL", "fieldName": "settlementDate", "fieldValue": d}]})
            got += [r for r in rows if r["symbolCode"] in syms]
            if len(rows) < 5000:
                break
            off += 5000; time.sleep(0.5)
        f.write_text(json.dumps(got)); print(d, len(got), flush=True)


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = [str(c) for c in z["cal"]]
    q = json.loads((ROOT / "data" / "stocks" / "y_QQQ.json").read_text())["chart"]["result"][0]
    qd = {dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"): c for t, c in zip(q["timestamp"], q["indicators"]["adjclose"][0]["adjclose"]) if c}
    S, U = [], []
    for f in sorted(OUT.glob("*.json")):
        rows = [r for r in json.loads(f.read_text()) if (r.get("averageDailyVolumeQuantity") or 0) > 0]
        if len(rows) < 500:
            continue
        S.append(float(np.log(np.mean([r["currentShortPositionQuantity"] / r["averageDailyVolumeQuantity"] for r in rows]))))
        i = next((k for k, c in enumerate(cal) if c > f.stem), None)
        U.append(cal[i + LAG - 1] if i is not None and i + LAG - 1 < len(cal) else None)
    x, r, sd = [], [], []
    for k in range(WARM, len(S) - 1):
        a, b = U[k], U[k + 1]
        if a is None or b is None or a not in qd or b not in qd or (a[:7] >= SEAL) != validate:
            continue
        s = S[k] - np.mean(S[k - WARM:k]); ret = qd[b] / qd[a] - 1
        side = -1.0 if s > 0 else 1.0; x.append((side - 1.0) * ret); r.append(ret); sd.append(side)
    x = np.array(x); m, t = x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    line = f"S1 {'sealed' if validate else 'discovery'}: periods {len(x)}, short share {np.mean(np.array(sd) < 0):.0%}, mean x {m*100:+.3f}%/period, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(1113); sig = np.array(sd) < 0; sh = []
        for _ in range(2000):
            s2 = np.roll(sig, rng.integers(1, len(x))); sh.append((np.where(s2, -2.0, 0.0) * np.array(r)).mean())
        pct = float((np.array(sh) < m).mean() * 100)
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    print(line)


if __name__ == "__main__":
    if sys.argv[1:] == ["fetch"]:
        fetch()
    else:
        main(sys.argv[1:] == ["validate"])
