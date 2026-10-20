"""K-family 11c (decisions.md 772): buy YES on 20-35c player props across every sport, at the candle 9 h -> 6 h before the close.

    python -m futuresres.kalshi.k11c            # discovery: markets closing before 2026-08-20 (lean.py samples)
    python -m futuresres.kalshi.k11c validate   # sealed 2026-08-20 -> 2026-10-19, once
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.k1_longshot import PRIOR_SD, _q, fee
from futuresres.kalshi.lean import LEAN

ROOT = Path(__file__).resolve().parents[3]
SERIES = ["KXNBAPTS", "KXNBAREB", "KXNBAAST", "KXNBA3PT", "KXWNBAPTS", "KXMLBHIT", "KXMLBHR", "KXMLBKS", "KXMLBTB", "KXNHLPTS",
          "KXNHLAST", "KXNHLGOAL", "KXNFLRSHYDS", "KXNFLRECYDS", "KXNFLPASSYDS", "KXNFLTD"]
SEAL, END = "2026-08-20", "2026-10-19T23:59:59Z"


def sport(s: str) -> str:
    return next(x for x in ("WNBA", "NBA", "MLB", "NHL", "NFL") if s.startswith("KX" + x))


def run(validate: bool) -> dict:
    per = collections.defaultdict(list); by = collections.defaultdict(list); cap = 0.0
    for s in SERIES:
        f = LEAN / f"{s}.jsonl"
        if not f.exists():
            continue
        for l in open(f):
            r = json.loads(l); c = r["candle"]
            if c is None or (validate and not SEAL <= r["close"] <= END) or (not validate and r["close"] >= SEAL):
                continue
            yb, ya = _q(c, "yes_bid"), _q(c, "yes_ask")
            if yb is None or ya is None or not (0 < yb < ya < 1) or ya - yb > 0.05 or not 0.20 <= (yb + ya) / 2 <= 0.35:
                continue
            pnl = (1.0 if r["result"] == "yes" else 0.0) - ya - fee(ya)
            per[r["event"]].append(pnl); by[s].append(pnl); cap += r["volume"]
    x = np.array([np.mean(v) for v in per.values()]); n = len(x)
    m = float(x.mean()) if n else float("nan"); t = float(m / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
    sp = collections.defaultdict(list)
    for s, v in by.items():
        sp[sport(s)] += v
    res = {"events": n, "markets": int(sum(len(v) for v in per.values())), "mean_net": m, "t": t, "market_volume": cap,
           "by_series": {s: {"n": len(v), "mean": float(np.mean(v))} for s, v in by.items()},
           "by_sport": {s: {"n": len(v), "mean": float(np.mean(v))} for s, v in sp.items()}}
    if validate:
        rng = np.random.default_rng(772)
        pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m).mean() * 100)
        post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
        res.update(placebo_pct=pct, posterior_zero_prior=post0,
                   decision="CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        res["carried"] = bool(m > 0 and t > 1.645 and sum(d["mean"] > 0 for k, d in res["by_sport"].items() if k != "NFL") >= 2)
    print(f"cheap_YES: events {n}, markets {res['markets']}, mean net {m*100:+.2f}c, t {t:+.2f} | "
          + ", ".join(f"{k} {d['n']}:{d['mean']*100:+.1f}c" for k, d in res["by_sport"].items())
          + (f" -> {res['decision']}" if validate else ("  CARRIED" if res["carried"] else "  not carried")), flush=True)
    print("  " + ", ".join(f"{k} {d['n']}:{d['mean']*100:+.1f}c" for k, d in res["by_series"].items()))
    (ROOT / "reports" / ("k11c_validation.json" if validate else "k11c_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    run(sys.argv[1:2] == ["validate"])
