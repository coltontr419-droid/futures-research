"""V-family 2 (decisions.md 956): SVXY held only in VIX contango, vs SPY.

    python -m futuresres.stocks.v2_svxy [validate]
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
PRIOR_SD, SEAL = 0.02, "2020-01-01"


def series(sym: str, adj: bool) -> dict:
    f = ROOT / "data" / "stocks" / f"y_{sym.strip('^')}.json"
    if not f.exists():
        r = urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&period1=1325376000&period2=1792800000",
                                                          headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
        f.write_text(r.decode()); time.sleep(0.5)
    r = json.loads(f.read_text())["chart"]["result"][0]
    v = r["indicators"]["adjclose"][0]["adjclose"] if adj else r["indicators"]["quote"][0]["close"]
    return {dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(): x for t, x in zip(r["timestamp"], v) if x}


def main(validate: bool) -> None:
    vix, v3, sv, spy = series("^VIX", False), series("^VIX3M", False), series("SVXY", True), series("SPY", True)
    d = sorted(set(vix) & set(v3) & set(sv) & set(spy)); ex = []; eq = [1.0]; prev = 0
    for a, b in zip(d[:-1], d[1:]):
        if (b >= SEAL) != validate:
            continue
        pos = 1 if vix[a] < v3[a] else 0
        r = (sv[b] / sv[a] - 1) * pos - (0.0005 if pos != prev else 0.0); prev = pos
        ex.append(r - (spy[b] / spy[a] - 1)); eq.append(eq[-1] * (1 + r))
    x = np.array(ex); m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    e = np.array(eq); dd = float((e / np.maximum.accumulate(e) - 1).min()); yrs = len(x) / 252
    line = (f"V2 {'sealed' if validate else 'discovery'}: days {len(x)}, strategy CAGR {(e[-1] ** (1 / yrs) - 1) * 100:+.1f}%, max DD {dd*100:.0f}%, "
            f"daily excess vs SPY {m*100:+.3f}%, t {t:+.2f}")
    if validate:
        rng = np.random.default_rng(956); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
