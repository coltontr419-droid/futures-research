"""C-family 2 (decisions.md 908): new Coinbase USD listings — buy at the second hour's open, hold 24 h / 72 h.

    python -m futuresres.xarb.c2_listing_drift [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np

from futuresres.xarb.x3_listings import candles

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL = 0.012, 0.02, "2026-01-01"


def main(validate: bool) -> None:
    L = json.loads((ROOT / "data" / "xarb" / "x3" / "listings.json").read_text()); res = {24: [], 72: []}
    for x in L:
        t0 = dt.datetime.fromtimestamp(x["first_day"], dt.timezone.utc)
        if (t0.isoformat() >= SEAL) != validate:
            continue
        c = sorted(cc for cc in candles(x["id"], t0, 3600, 100) if cc[5] > 0); time.sleep(0.35)
        if len(c) < 3:
            continue
        start = c[0][0]; by = {int(cc[0]): cc for cc in c}
        e = by.get(int(start + 3600))
        if not e:
            continue
        for h in (24, 72):
            k = max((t for t in by if t <= start + h * 3600 - 3600), default=None)
            if k and k > e[0]:
                res[h].append(by[k][4] / e[3] - 1 - COST)
    for h, v in res.items():
        x = np.array(v)
        if len(x) < 3:
            continue
        m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
        line = f"C2 {'sealed' if validate else 'discovery'} hold {h}h: n {len(x)}, mean {m*100:+.2f}%, median {np.median(x)*100:+.2f}%, t {t:+.2f}"
        if validate:
            rng = np.random.default_rng(908); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
            post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
            line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
        else:
            line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
