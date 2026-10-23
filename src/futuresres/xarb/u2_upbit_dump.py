"""U-family 2 (decisions.md 910): Upbit delisting / warning notices — buy the dump an hour later on Coinbase, hold 24 h / 72 h.

    python -m futuresres.xarb.u2_upbit_dump [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

from futuresres.xarb.x1_snapshot import get
from futuresres.xarb.x3_listings import CB, candles

ROOT = Path(__file__).resolve().parents[3]
BAD = re.compile(r"거래지원 종료 안내|유의 종목 지정 안내|유의 촉구 안내")
COST, PRIOR_SD, SEAL = 0.012, 0.02, "2026-01-01"


def main(validate: bool) -> None:
    N = json.loads((ROOT / "data" / "xarb" / "u1" / "notices.json").read_text())
    cb = {p["base_currency"]: p["id"] for p in get(f"{CB}/products") if p["quote_currency"] == "USD"}
    seen, res = set(), {24: [], 72: []}
    for n in sorted(N, key=lambda x: x["listed_at"]):
        if not BAD.search(n["title"]) or "연장" in n["title"] or n["listed_at"] < "2025-01-01" or (n["listed_at"] >= SEAL) != validate:
            continue
        m = re.search(r"\(([A-Z0-9]{2,12})\)", n["title"])
        if not m or m.group(1) in seen or m.group(1) not in cb:
            continue
        seen.add(m.group(1))
        t0 = dt.datetime.fromisoformat(n["listed_at"]).astimezone(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
        c = {int(x[0]): x for x in candles(cb[m.group(1)], t0, 3600, 80)}; time.sleep(0.35)
        e = c.get(int((t0 + dt.timedelta(hours=1)).timestamp()))
        if not e:
            continue
        for h in (24, 72):
            x = c.get(int((t0 + dt.timedelta(hours=h)).timestamp()))
            if x:
                res[h].append(x[4] / e[4] - 1 - COST)
    for h, v in res.items():
        x = np.array(v)
        if len(x) < 3:
            print(f"U2 hold {h}h: n {len(x)}"); continue
        mu, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
        line = f"U2 {'sealed' if validate else 'discovery'} hold {h}h: n {len(x)}, mean {mu*100:+.2f}%, median {np.median(x)*100:+.2f}%, t {t:+.2f}"
        if validate:
            rng = np.random.default_rng(910); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < mu).mean() * 100)
            post = mu * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
            line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and mu > 0 and post > 0 else ("WATCHLIST" if mu > 0 else "REJECT"))
        else:
            line += "  CARRIED" if mu > 0 and t > 1.96 else "  not carried"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
