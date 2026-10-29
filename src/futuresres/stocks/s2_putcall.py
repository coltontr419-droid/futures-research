"""S-family 2 (decisions.md §1114): CBOE equity put/call ratio (5d / 60d) as a contrarian next-session long/short sign for MNQ (QQQ proxy).

    python -m futuresres.stocks.s2_putcall fetch
    python -m futuresres.stocks.s2_putcall [validate]
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
from curl_cffi import requests

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "stocks" / "s2"
HIST = "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv"
DAY = "https://cdn.cboe.com/data/us/options/market_statistics/daily/{}_daily_options"
SEAL, COST = "2023-01", 0.25 / 20000 * 2


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pc = json.loads((OUT / "pc.json").read_text()) if (OUT / "pc.json").exists() else {}
    if not pc:
        for row in csv.reader(io.StringIO(requests.get(HIST, timeout=60).text)):
            try:
                pc[dt.datetime.strptime(row[0].strip(), "%m/%d/%Y").strftime("%Y-%m-%d")] = float(row[4])
            except (ValueError, IndexError):
                pass
    d = dt.date(2019, 10, 5)
    while d < dt.date.today():
        k = str(d)
        if d.weekday() < 5 and k not in pc:
            r = requests.get(DAY.format(k), timeout=30)
            if r.status_code == 200:
                v = next((x["value"] for x in r.json().get("ratios", []) if x["name"] == "EQUITY PUT/CALL RATIO"), None)
                if v and float(v) > 0:
                    pc[k] = float(v)
            time.sleep(0.25)
        d += dt.timedelta(days=1)
    (OUT / "pc.json").write_text(json.dumps(dict(sorted(pc.items()))))
    print(len(pc), min(pc), max(pc))


def main(validate: bool) -> None:
    pc = json.loads((OUT / "pc.json").read_text())
    q = json.loads((ROOT / "data" / "stocks" / "y_QQQ.json").read_text())["chart"]["result"][0]
    qd = {dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"): c for t, c in zip(q["timestamp"], q["indicators"]["adjclose"][0]["adjclose"]) if c}
    days = [k for k in sorted(qd) if k in pc]
    v = np.array([pc[k] for k in days])
    x, r, sd, prev = [], [], [], None
    for i in range(60, len(days) - 1):
        d0, d1 = days[i], days[i + 1]
        if (d0[:7] >= SEAL) != validate or (not validate and d0 < "2007-03"):
            continue
        p = v[i - 4:i + 1].mean() / v[i - 59:i + 1].mean() - 1
        side = 1.0 if p > 0 else -1.0; ret = qd[d1] / qd[d0] - 1
        x.append((side - 1.0) * ret - (COST if prev is not None and side != prev else 0.0)); r.append(ret); sd.append(side); prev = side
    x = np.array(x); m, t = x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    line = f"S2 {'sealed' if validate else 'discovery'}: sessions {len(x)}, mean x {m*1e4:+.2f} bp/session, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(1114); sig = np.array(sd) < 0; R = np.array(r); sh = []
        for _ in range(2000):
            s2 = np.roll(sig, rng.integers(1, len(x))); sh.append((np.where(s2, -2.0, 0.0) * R).mean())
        pct = float((np.array(sh) < m).mean() * 100)
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    print(line)


if __name__ == "__main__":
    if sys.argv[1:] == ["fetch"]:
        fetch()
    else:
        main(sys.argv[1:] == ["validate"])
