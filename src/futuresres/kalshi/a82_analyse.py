"""A82 analysis (decisions.md 708): long-shot sales near settlement - how often the favourite won, and the takers' net after fees.

    python -m futuresres.kalshi.a82_analyse
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
IN = ROOT / "data" / "kalshi" / "taker"
OUT = ROOT / "reports" / "a82_taker.json"
DAYS = 45


def group(series: str) -> str:
    if series.startswith("KXAAAGASD"):
        return "state daily gas"
    if series == "KXTEMPMIAH":
        return "Miami hourly temperature"
    if series == "KXEOWEEK":
        return "weekly executive orders"
    return "daily high temperature"


def bucket_time(h: float) -> str:
    return "<= 1 h" if h <= 1 else ("1-6 h" if h <= 6 else ("6-24 h" if h <= 24 else "> 24 h"))


def wilson(k: float, n: float, z: float = 1.96):
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def ts(x):
    return dt.datetime.fromisoformat(x.replace("Z", "+00:00"))


def main() -> int:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=DAYS)
    cells = collections.defaultdict(lambda: {"trades": 0, "wins": 0, "contracts": 0.0, "net": 0.0, "markets": set(), "lost_markets": set(), "worst": []})
    for sd in sorted(IN.iterdir()):
        for f in sd.glob("*.json"):
            ev = json.loads(f.read_text())
            for m in ev.get("markets", []):
                if not m.get("close") or ts(m["close"]) < since:
                    continue
                close = ts(m["close"])
                for t, yp, side, n in m["trades"]:
                    if side == "no" and yp <= 0.0301:
                        fav, price = "no", round(1 - yp, 2)
                    elif side == "yes" and yp >= 0.9699:
                        fav, price = "yes", round(yp, 2)
                    else:
                        continue                                  # the taker bought the long shot: not a long-shot sale
                    hours = (close - ts(t)).total_seconds() / 3600
                    if hours < 0:
                        continue
                    win = m["result"] == fav; fee = 0.07 * price * (1 - price)
                    net = ((1 - price) if win else -price) - fee
                    for key in ((group(sd.name), "all", "all"), (group(sd.name), f"{price*100:.0f}c", "all"), (group(sd.name), "all", bucket_time(hours)), ("ALL", "all", "all")):
                        c = cells[key]
                        c["trades"] += 1; c["wins"] += win; c["contracts"] += n; c["net"] += n * net; c["markets"].add(m["ticker"])
                        if not win:
                            c["lost_markets"].add(m["ticker"])
    rows = []
    for (g, pr, tb), c in sorted(cells.items()):
        lo, hi = wilson(c["wins"], c["trades"]); nm = len(c["markets"]); lm = len(c["lost_markets"])
        mlo, mhi = wilson(nm - lm, nm)
        r = {"group": g, "price": pr, "time_left": tb, "trades": c["trades"], "contracts": c["contracts"], "win_rate_trades": c["wins"] / max(c["trades"], 1),
             "wilson_trades": [lo, hi], "markets": nm, "markets_where_favourite_lost": lm, "market_win_rate": (nm - lm) / max(nm, 1),
             "wilson_markets": [mlo, mhi], "net_total": c["net"], "net_per_contract": c["net"] / max(c["contracts"], 1)}
        rows.append(r)
    OUT.write_text(json.dumps(rows, indent=1) + "\n")
    for r in rows:
        print(f"{r['group']:26} {r['price']:4} {r['time_left']:7} trades {r['trades']:6} contracts {r['contracts']:10,.0f} | favourite won {r['win_rate_trades']:.2%} "
              f"(95% {r['wilson_trades'][0]:.2%}-{r['wilson_trades'][1]:.2%}) | markets {r['markets']:5}, favourite lost in {r['markets_where_favourite_lost']:3} | "
              f"takers net ${r['net_total']:+,.0f} ({r['net_per_contract']*100:+.2f}c/contract)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
