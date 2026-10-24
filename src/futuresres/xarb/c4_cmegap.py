"""C-family 4 (decisions.md 933): BTC CME-gap long — buy the Sunday reopen when spot is >= 2% below Friday's CME close.

    python -m futuresres.xarb.c4_cmegap [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
CT = ZoneInfo("America/Chicago")
COST, PRIOR_SD, SEAL = 0.008, 0.02, "2025-07-01"


def main(validate: bool) -> None:
    C = {int(c[0]): c for c in json.loads((ROOT / "data" / "xarb" / "c1" / "BTC-USD.json").read_text())}
    res = {0.02: [], 0.03: []}
    d = dt.date(2024, 1, 5)
    while d < dt.date(2026, 10, 16):
        fri_close_hour = dt.datetime(d.year, d.month, d.day, 15, tzinfo=CT)            # hour 15:00-16:00 CT -> its close is 16:00
        sun = d + dt.timedelta(days=2); reopen = dt.datetime(sun.year, sun.month, sun.day, 17, tzinfo=CT)
        f = C.get(int(fri_close_hour.timestamp())); r = C.get(int(reopen.timestamp()))
        if f and r and (reopen.date().isoformat() >= SEAL) == validate:
            ref, entry = f[4], r[3]
            for th in res:
                if entry <= (1 - th) * ref:
                    out = None
                    for h in range(0, 72):
                        c = C.get(int(reopen.timestamp()) + 3600 * h)
                        if c and c[4] >= ref:
                            out = c[4]; break
                    if out is None:
                        c = C.get(int(reopen.timestamp()) + 3600 * 71); out = c[4] if c else None
                    if out:
                        res[th].append(out / entry - 1 - COST)
        d += dt.timedelta(days=7)
    for th, v in res.items():
        x = np.array(v)
        if len(x) < 3:
            print(f"C4 gap ≥{th:.0%}: n {len(x)}"); continue
        m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
        line = f"C4 {'sealed' if validate else 'discovery'} gap ≥{th:.0%}: n {len(x)}, mean {m*100:+.2f}%, median {np.median(x)*100:+.2f}%, t {t:+.2f}"
        if th == 0.02:
            if validate:
                rng = np.random.default_rng(933); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
                post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
                line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
            else:
                line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
