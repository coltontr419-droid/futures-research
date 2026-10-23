"""C-family 3 (decisions.md 923): weekly cross-sectional momentum among 40 liquid Coinbase coins (C1 cache).

    python -m futuresres.xarb.c3_xsmom [validate]
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


def main(validate: bool) -> None:
    U = json.loads((C1 / "universe.json").read_text()); P = {}
    for pid in U:
        f = C1 / f"{pid}.json"
        if f.exists():
            P[pid] = {int(c[0]): (c[3], c[4]) for c in json.loads(f.read_text())}       # hour start -> (open, close)
    btc = P["BTC-USD"]; out = {"top": [], "bottom": []}
    t = int(dt.datetime(2024, 1, 8, tzinfo=dt.timezone.utc).timestamp()); end = int(dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc).timestamp())
    while t < end:
        day = dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat()
        if (day >= SEAL) == validate:
            ranks = []
            for pid, b in P.items():
                a, z, x = b.get(t - 7 * 86400), b.get(t), b.get(t + 167 * 3600)
                if a and z and x and a[1] > 0 and z[0] > 0:
                    ranks.append((z[0] / a[1] - 1, x[1] / z[0] - 1 - COST))
            if len(ranks) >= 20 and btc.get(t) and btc.get(t + 167 * 3600):
                ranks.sort(); bm = btc[t + 167 * 3600][1] / btc[t][0] - 1
                for k, sl in (("top", ranks[-5:]), ("bottom", ranks[:5])):
                    r = float(np.mean([y for _, y in sl])); out[k].append((r, r - bm))
        t += 7 * 86400
    for k, v in out.items():
        a = np.array([x[1] for x in v]); rw = np.array([x[0] for x in v])
        if len(a) < 4:
            continue
        m, tt = float(a.mean()), float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a))))
        line = f"C3 {'sealed' if validate else 'discovery'} {k} 5: weeks {len(a)}, raw {rw.mean()*100:+.2f}%/wk, vs BTC {m*100:+.2f}%/wk, t {tt:+.2f}"
        if k == "top":
            if validate:
                rng = np.random.default_rng(923); pct = float((np.array([(a * rng.choice((-1.0, 1.0), len(a))).mean() for _ in range(4000)]) < m).mean() * 100)
                post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + a.var(ddof=1) / len(a))
                line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if tt > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
            else:
                line += "  CARRIED" if (m > 0 and tt > 1.96 and rw.mean() > 0) else "  not carried"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
