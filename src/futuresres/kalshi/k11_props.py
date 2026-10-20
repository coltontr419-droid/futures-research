"""K-family 11 (decisions.md 760): single player props on Kalshi (KXNFLTD, KXNFLRSHYDS, KXNHLGOAL) — buy NO on cheap props, YES on
expensive ones, at the hourly candle 6 h before the close.

    python -m futuresres.kalshi.k11_props            # discovery: games closing before 2026-03-01
    python -m futuresres.kalshi.k11_props validate   # sealed 2026-03-01 -> 2026-10-19, once
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
SERIES = ["KXNFLTD", "KXNFLRSHYDS", "KXNHLGOAL"]
SEAL = dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 10, 19, 23, 59, tzinfo=dt.timezone.utc)


def T(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


REVERSE = False


def run(validate: bool) -> dict:
    per = {("cheap_YES" if REVERSE else "cheap_NO"): collections.defaultdict(list), "dear_YES": collections.defaultdict(list)}
    ser = {k: collections.defaultdict(list) for k in per}; cap = collections.Counter()
    for s in SERIES:
        for f in sorted((DATA / s).glob("*.json")):
            ev = json.loads(f.read_text())
            for m in ev.get("markets", []):
                if m.get("result") not in ("yes", "no") or not m.get("close_time"):
                    continue
                close = T(m["close_time"])
                if (validate and not SEAL <= close <= END) or (not validate and close >= SEAL):
                    continue
                t = close.timestamp() - 6 * 3600
                c = [x for x in sorted(m.get("candles") or [], key=lambda x: int(x["end_period_ts"])) if t - 3 * 3600 <= int(x["end_period_ts"]) <= t]
                if not c:
                    continue
                c = c[-1]; yb, ya = _q(c, "yes_bid"), _q(c, "yes_ask")
                if yb is None or ya is None or not (0 < yb < ya < 1) or ya - yb > 0.05:
                    continue
                mid = (yb + ya) / 2; yes = m["result"] == "yes"
                if mid <= 0.35 and REVERSE:                      # K-family 11b (decisions.md 771): buy YES on cheap props
                    q = ya; pnl = (1.0 if yes else 0.0) - q - fee(q); k = "cheap_YES"
                elif mid <= 0.35:
                    q = 1 - yb; pnl = (0.0 if yes else 1.0) - q - fee(q); k = "cheap_NO"
                elif mid >= 0.65:
                    q = ya; pnl = (1.0 if yes else 0.0) - q - fee(q); k = "dear_YES"
                else:
                    continue
                per[k][ev["event"]].append(pnl); ser[k][s].append(pnl); cap[k] += float(c.get("volume_fp") or c.get("volume") or 0)
    res = {}
    for k in per:
        x = np.array([np.mean(v) for v in per[k].values()]); n = len(x)
        m_ = float(x.mean()) if n else float("nan"); t_ = float(m_ / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
        r = {"games": n, "markets": int(sum(len(v) for v in per[k].values())), "mean_net": m_, "t": t_, "candle_volume": cap[k],
             "by_series": {s: {"n": len(v), "mean": float(np.mean(v))} for s, v in ser[k].items()}}
        if validate:
            rng = np.random.default_rng(760)
            pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m_).mean() * 100)
            post0 = m_ * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
            r.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t_ > 1.645 and pct >= 95 and m_ > 0 and post0 > 0) else ("WATCHLIST" if m_ > 0 else "REJECT"))
        else:
            r["carried"] = bool(t_ > 1.96 and m_ > 0)
        res[k] = r
        print(f"{k}: games {n}, markets {r['markets']}, mean net {m_*100:+.2f}c, t {t_:+.2f} | "
              + ", ".join(f"{s} {d['n']}:{d['mean']*100:+.1f}c" for s, d in r["by_series"].items())
              + (f" -> {r.get('decision')}" if validate else ("  CARRIED" if r["carried"] else "")), flush=True)
    (ROOT / "reports" / (("k11b" if REVERSE else "k11") + ("_validation.json" if validate else "_discovery.json"))).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    REVERSE = "--reverse" in sys.argv
    run("validate" in sys.argv)
