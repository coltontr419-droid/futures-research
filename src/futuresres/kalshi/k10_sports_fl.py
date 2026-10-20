"""K-family 10 (decisions.md 756): favourite / long-shot bias in Kalshi game-winner markets.

    python -m futuresres.kalshi.k10_sports_fl            # discovery: games closing before 2025-10-01
    python -m futuresres.kalshi.k10_sports_fl validate   # sealed 2025-10-01 -> 2026-10-19, once
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.k1_longshot import DATA, PRIOR_SD, _q, fee

ROOT = Path(__file__).resolve().parents[3]
SERIES = ["KXNFLGAME", "KXNBAGAME", "KXMLBGAME", "KXNHLGAME", "KXNCAAFGAME"]
SEAL = dt.datetime(2025, 10, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 10, 19, 23, 59, tzinfo=dt.timezone.utc)
LEAD = 6 * 3600


def T(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def rows():
    out = []
    for s in SERIES:
        for f in sorted((DATA / s).glob("*.json")):
            ev = json.loads(f.read_text()); ms = [m for m in ev.get("markets", []) if m.get("result") in ("yes", "no") and m.get("close_time")]
            if not ms:
                continue
            m = ms[0]; close = T(m["close_time"]); t = close.timestamp() - LEAD
            cs = sorted(m.get("candles") or [], key=lambda x: int(x["end_period_ts"]))
            c = [x for x in cs if t - 3 * 3600 <= int(x["end_period_ts"]) <= t]
            if not c:
                continue
            c = c[-1]; yb, ya = _q(c, "yes_bid"), _q(c, "yes_ask")
            if yb is None or ya is None or not (0 < yb < ya < 1) or ya - yb > 0.05:
                continue
            vol = float(c.get("volume_fp") or c.get("volume") or 0)
            out.append((s, close, yb, ya, m["result"] == "yes", vol))
    return out


def run(validate: bool) -> dict:
    rs = [r for r in rows() if (SEAL <= r[1] <= END if validate else r[1] < SEAL)]
    tests = {"longshot_NO": [], "favourite_YES": []}; by_sport = collections.defaultdict(lambda: collections.defaultdict(list))
    cap = collections.Counter(); months = collections.defaultdict(lambda: collections.defaultdict(list))
    for s, close, yb, ya, yes, vol in rs:
        mid = (yb + ya) / 2
        if mid <= 0.25:
            q = 1 - yb; pnl = (0.0 if yes else 1.0) - q - fee(q); k = "longshot_NO"
        elif mid >= 0.75:
            q = ya; pnl = (1.0 if yes else 0.0) - q - fee(q); k = "favourite_YES"
        else:
            continue
        tests[k].append(pnl); by_sport[k][s].append(pnl); cap[k] += vol; months[k][close.strftime("%Y-%m")].append(pnl)
    res = {}
    for k, v in tests.items():
        x = np.array(v); n = len(x); m = float(x.mean()) if n else float("nan")
        t = float(m / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
        r = {"games": n, "mean_net": m, "t": t, "candle_volume": cap[k],
             "by_sport": {s: {"n": len(y), "mean": float(np.mean(y))} for s, y in by_sport[k].items()},
             "months_positive": f"{sum(np.mean(y) > 0 for y in months[k].values())}/{len(months[k])}"}
        if validate:
            rng = np.random.default_rng(756)
            pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m).mean() * 100)
            post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
            r.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT"))
        else:
            r["carried"] = bool(t > 1.96 and m > 0)
        res[k] = r
        print(f"{k}: games {n}, mean net {m*100:+.2f}c/contract, t {t:+.2f}, months + {r['months_positive']}, "
              + ", ".join(f"{s} {d['n']}:{d['mean']*100:+.1f}c" for s, d in r["by_sport"].items())
              + (f" -> {r.get('decision')}" if validate else ("  CARRIED" if r["carried"] else "")), flush=True)
    (ROOT / "reports" / ("k10_validation.json" if validate else "k10_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    run(sys.argv[1:2] == ["validate"])
