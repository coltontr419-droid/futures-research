"""L-family 8 (decisions.md 945): sector ETF 12-1 momentum, top 3 of the SPDR sectors vs equal weight.

    python -m futuresres.stocks.l8_sectors [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
ETF = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC")
COST, PRIOR_SD, SEAL = 0.0005, 0.02, "2016-01"


def series() -> dict:
    f = ROOT / "data" / "stocks" / "sectors.json"
    if f.exists():
        return json.loads(f.read_text())
    out = {}
    for s in ETF:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval=1d&period1=1104537600&period2=1792800000", headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())["chart"]["result"][0]
        out[s] = {dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(): a for t, a in zip(r["timestamp"], r["indicators"]["adjclose"][0]["adjclose"]) if a}
        time.sleep(0.5)
    f.write_text(json.dumps(out)); return out


def main(validate: bool) -> None:
    S = series(); cal = sorted(set().union(*[set(v) for v in S.values()]))
    me = [i for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7]]; ex = []
    for i0, i1 in zip(me[:-1], me[1:]):
        if i0 < 260 or (cal[i1][:7] >= SEAL) != validate:
            continue
        d0, d1, dA, dB = cal[i0], cal[i1], cal[i0 - 252], cal[i0 - 21]
        rows = [(v[dB] / v[dA] - 1, v[d1] / v[d0] - 1) for v in S.values() if all(k in v for k in (d0, d1, dA, dB))]
        if len(rows) < 6:
            continue
        rows.sort(reverse=True)
        ex.append(float(np.mean([r[1] for r in rows[:3]])) - COST - float(np.mean([r[1] for r in rows])))
    x = np.array(ex); m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    line = f"L8 {'sealed' if validate else 'discovery'}: months {len(x)}, excess {m*100:+.2f}%/month, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(945); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
