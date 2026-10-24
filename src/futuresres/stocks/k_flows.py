"""K-calendar 3-6 (decisions.md 962): pension rebalancing (SPY), Treasury 30Y auction cycle (TLT), month-end in IEF / LQD, OPEX week (SPY).

    python -m futuresres.stocks.k_flows [validate]
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
COST, PRIOR_SD, SEAL = 0.0002, 0.02, "2016-01"


def ser(sym: str) -> tuple[list[str], list[float]]:
    f = ROOT / "data" / "stocks" / f"y_{sym}.json"
    if not f.exists():
        f.write_text(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&period1=1104537600&period2=1792800000",
                                                                   headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read().decode()); time.sleep(0.5)
    r = json.loads(f.read_text())["chart"]["result"][0]
    p = [(dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(), a) for t, a in zip(r["timestamp"], r["indicators"]["adjclose"][0]["adjclose"]) if a]
    return [x for x, _ in p], [y for _, y in p]


def verdict(name: str, x: list, validate: bool, seed: int) -> None:
    x = np.array(x)
    if len(x) < 6:
        print(f"  {name}: n {len(x)}"); return
    m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    s = f"  {name:16}: n {len(x):3}, excess {m*100:+.3f}%, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(seed); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        s += f", placebo {pct:.0f}th, posterior {post*100:+.3f}% -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        s += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(s)


def main(validate: bool) -> None:
    sel = lambda d: (d[:7] >= SEAL) == validate
    sd, sa = ser("SPY"); td, ta = ser("TLT"); spy = dict(zip(sd, sa)); tlt = dict(zip(td, ta))
    drift = lambda a, k: (a[-1] / a[0]) ** (k / len(a)) - 1
    # K3 pension rebalancing
    k3 = []; me = [i for i in range(len(sd) - 1) if sd[i][:7] != sd[i + 1][:7]]
    for p0, p1 in zip(me[:-1], me[1:]):
        e = p1 - 3; d0, de = sd[p0], sd[e]
        if not sel(sd[p1]) or d0 not in tlt or de not in tlt:
            continue
        if (tlt[de] / tlt[d0]) - (spy[de] / spy[d0]) >= 0.03:
            k3.append(sa[p1] / sa[e] - 1 - COST - drift(sa, 3))
    # K4 auction cycle
    A = json.loads((ROOT / "data" / "stocks" / "auctions30.json").read_text()) if (ROOT / "data" / "stocks" / "auctions30.json").exists() else []
    ti = {d: i for i, d in enumerate(td)}; k4 = []
    for d in sorted({x[:10] for x in A}):
        i = ti.get(d)
        if i is None or i + 5 >= len(td) or not sel(d):
            continue
        k4.append(ta[i + 5] / ta[i] - 1 - COST - drift(ta, 5))
    # K5 month-end extension on IEF and LQD
    k5 = {}
    for s in ("IEF", "LQD"):
        d, a = ser(s); k5[s] = [a[i] / a[i - 4] - 1 - COST - drift(a, 4) for i in range(5, len(d) - 1) if d[i][:7] != d[i + 1][:7] and sel(d[i])]
    # K6 OPEX week
    k6 = []; si = {d: i for i, d in enumerate(sd)}
    for i, d in enumerate(sd):
        x = dt.date.fromisoformat(d)
        if x.weekday() == 4 and 15 <= x.day <= 21 and sel(d):                                     # 3rd Friday
            j = next((k for k in range(i - 1, max(i - 8, 0), -1) if dt.date.fromisoformat(sd[k]).weekday() == 4), None)
            if j is not None:
                k6.append(sa[i] / sa[j] - 1 - COST - drift(sa, i - j))
    print(f"K flows {'sealed' if validate else 'discovery'}")
    verdict("K3 pension", k3, validate, 9623); verdict("K4 auction", k4, validate, 9624)
    verdict("K5 IEF month-end", k5["IEF"], validate, 9625); verdict("K5 LQD month-end", k5["LQD"], validate, 9626); verdict("K6 OPEX week", k6, validate, 9627)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
