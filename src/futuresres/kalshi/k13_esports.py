"""K-family 13 (decisions.md 774): favourite / underdog mispricing in Kalshi esports match winners, before the scheduled start.

    python -m futuresres.kalshi.k13_esports                    # discovery: matches starting before 2026-08-20
    python -m futuresres.kalshi.k13_esports validate TEST      # sealed 2026-08-20 -> 2026-10-19, once (TEST = the carried one)
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.download import OUT
from futuresres.kalshi.k1_longshot import PRIOR_SD, _q, fee

ROOT = Path(__file__).resolve().parents[3]
SERIES = ["KXLOLGAME", "KXCS2GAME", "KXDOTA2GAME", "KXVALORANTGAME", "KXR6GAME", "KXRLGAME", "KXOWGAME", "KXCODGAME", "KXMLBBGAME"]
SEAL = dt.datetime(2026, 8, 20, tzinfo=dt.timezone.utc).timestamp()
END = dt.datetime(2026, 10, 20, tzinfo=dt.timezone.utc).timestamp()


def events(validate: bool) -> list[tuple[str, list[dict]]]:
    out = []
    for s in SERIES:
        f = OUT / "lean_start" / f"{s}.jsonl"
        if not f.exists():
            continue
        ev = collections.defaultdict(list)
        for l in open(f):
            r = json.loads(l)
            if r["start"] and dt.datetime.fromisoformat(r["close"].replace("Z", "+00:00")).timestamp() < r["start"] + 1200:
                continue                                   # closed before its listed start: a schedule error (decisions.md 775)
            if r["start"] and ((SEAL <= r["start"] < END) if validate else r["start"] < SEAL):
                ev[r["event"]].append(r)
        out += [(s, v) for v in ev.values()]
    return out


def run(validate: bool, only: str | None = None) -> dict:
    tests = {"favourite_YES": [], "underdog_YES": []}; by = {k: collections.defaultdict(list) for k in tests}; cap = collections.Counter()
    for s, ms in events(validate):
        q = []
        for r in ms:
            c = r["candle"]
            if not c:
                continue
            yb, ya = _q(c, "yes_bid"), _q(c, "yes_ask")
            if yb is None or ya is None or not (0 < yb < ya < 1) or ya - yb > 0.05:
                continue
            q.append(((yb + ya) / 2, ya, r["result"] == "yes", float(c.get("volume_fp") or c.get("volume") or 0), r["volume"]))
        if len(q) != 2:
            continue
        q.sort(key=lambda x: -x[0]); fav, dog = q
        if fav[0] >= 0.70:
            p = (1.0 if fav[2] else 0.0) - fav[1] - fee(fav[1]); tests["favourite_YES"].append(p); by["favourite_YES"][s].append(p)
            cap["favourite_YES"] += fav[4]
        if dog[0] <= 0.30:
            p = (1.0 if dog[2] else 0.0) - dog[1] - fee(dog[1]); tests["underdog_YES"].append(p); by["underdog_YES"][s].append(p)
            cap["underdog_YES"] += dog[4]
    res = {}
    for k, v in tests.items():
        if only and k != only:
            continue
        x = np.array(v); n = len(x); m = float(x.mean()) if n else float("nan")
        t = float(m / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
        r = {"events": n, "mean_net": m, "t": t, "market_volume": cap[k], "by_series": {s: {"n": len(y), "mean": float(np.mean(y))} for s, y in by[k].items()}}
        if validate:
            rng = np.random.default_rng(774)
            pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m).mean() * 100)
            post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
            r.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT"))
        else:
            r["carried"] = bool(t > 1.96 and m > 0)
        res[k] = r
        print(f"{k}: events {n}, mean net {m*100:+.2f}c, t {t:+.2f}, volume {cap[k]:,.0f} | "
              + ", ".join(f"{s[2:-4]} {d['n']}:{d['mean']*100:+.1f}c" for s, d in r["by_series"].items())
              + (f" -> {r.get('decision')}" if validate else ("  CARRIED" if r["carried"] else "")), flush=True)
    (ROOT / "reports" / ("k13_validation.json" if validate else "k13_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    v = sys.argv[1:2] == ["validate"]
    run(v, sys.argv[2] if v else None)
