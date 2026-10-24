"""C-family 5 (decisions.md 935): after a >= 2% BTC hour, buy the 5 alts that lagged most; hold 1 / 4 hours.

    python -m futuresres.xarb.c5_leadlag [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
C1 = ROOT / "data" / "xarb" / "c1"
COST, PRIOR_SD, SEAL = 0.008, 0.02, "2025-07-01"


def load() -> dict:
    P = {}
    for pid in json.loads((C1 / "universe.json").read_text()):
        f = C1 / f"{pid}.json"
        if f.exists():
            P[pid] = {int(c[0]): (c[3], c[4]) for c in json.loads(f.read_text())}
    return P


def main(validate: bool) -> None:
    P = load(); btc = P["BTC-USD"]; res = {(2, 1): [], (2, 4): [], (3, 1): [], (3, 4): []}
    for t in sorted(btc):
        p = btc.get(t - 3600)
        if not p:
            continue
        rb = btc[t][1] / p[1] - 1
        if rb < 0.02 or (dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat() >= SEAL) != validate:
            continue
        rel = []
        for pid, b in P.items():
            if pid in ("BTC-USD", "ETH-USD"):
                continue
            a, z = b.get(t - 3600), b.get(t)
            if a and z and a[1] > 0:
                rel.append((z[1] / a[1] - 1 - rb, pid))
        if len(rel) < 30:
            continue
        rel.sort(); lag = [pid for _, pid in rel[:5]]
        for th in (2, 3):
            if rb < th / 100:
                continue
            for h in (1, 4):
                rr = []
                for pid in lag:
                    e, x = P[pid].get(t + 3600), P[pid].get(t + 3600 * h)
                    if e and x and e[0] > 0:
                        rr.append(x[1] / e[0] - 1)
                if rr:
                    res[(th, h)].append(float(np.mean(rr)) - COST)
    for (th, h), v in res.items():
        x = np.array(v)
        if len(x) < 3:
            continue
        m, tt = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
        line = f"C5 {'sealed' if validate else 'discovery'} BTC ≥{th}%, hold {h}h: n {len(x)}, mean {m*100:+.2f}%, median {np.median(x)*100:+.2f}%, t {tt:+.2f}"
        if (th, h) == (2, 1):
            if validate:
                rng = np.random.default_rng(935); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
                post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
                line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if tt > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
            else:
                line += "  CARRIED" if m > 0 and tt > 1.96 else "  not carried"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
