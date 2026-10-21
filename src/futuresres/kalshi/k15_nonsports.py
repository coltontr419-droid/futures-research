"""K-family 15 (decisions.md 795): favourite / long-shot bias in Kalshi's non-sports, non-index markets, 24 h before the close.

    python -m futuresres.kalshi.k15_nonsports list        # settled events since 2026-06-01 (resumable, cached)
    python -m futuresres.kalshi.k15_nonsports candles     # the 27 h -> 24 h candle per sampled market (resumable)
    python -m futuresres.kalshi.k15_nonsports             # discovery (closes before 2026-09-21; decisions.md 799)
    python -m futuresres.kalshi.k15_nonsports validate    # sealed 2026-09-21 -> 2026-10-20, once
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import random
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.download import get
from futuresres.kalshi.k1_longshot import PRIOR_SD, _q, fee

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "kalshi" / "k15"
CATS = {"Politics", "Elections", "Economics", "Climate and Weather", "World", "Entertainment", "Science and Technology", "Companies", "Mentions",
        "Health", "Social", "Culture"}
START, SEAL, END = "2026-06-01", "2026-09-21", "2026-10-21"


def T(s: str) -> int:
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def listing() -> None:
    DIR.mkdir(parents=True, exist_ok=True); f = DIR / "markets.jsonl"; cur_f = DIR / "cursor.txt"
    cur = cur_f.read_text().strip() if cur_f.exists() else None
    ts = T(START + "T00:00:00Z"); n = 0
    with open(f, "a") as out:
        while True:
            d = get(f"/events?status=settled&limit=200&with_nested_markets=true&min_close_ts={ts}" + (f"&cursor={cur}" if cur else ""))
            for e in d.get("events", []):
                if e.get("category") not in CATS:
                    continue
                for m in e.get("markets") or []:
                    if m.get("result") in ("yes", "no") and m.get("close_time") and float(m.get("volume_fp") or 0) >= 1000:
                        out.write(json.dumps({"ticker": m["ticker"], "event": e["event_ticker"], "series": e.get("series_ticker"), "cat": e["category"],
                                              "close": m["close_time"], "result": m["result"], "volume": float(m.get("volume_fp") or 0)}) + "\n"); n += 1
            cur = d.get("cursor"); cur_f.write_text(cur or "")
            if not cur or not d.get("events"):
                break
    print("listed", n, flush=True)


def candles() -> None:
    ms = [json.loads(l) for l in open(DIR / "markets.jsonl")]
    ms = list({m["ticker"]: m for m in ms}.values())
    disc = [m for m in ms if m["close"] < SEAL]; seal = [m for m in ms if SEAL <= m["close"] < END]
    evs = sorted({m["event"] for m in disc}); random.Random(795).shuffle(evs); keep = set(evs)
    pick, k = [], 0
    for e in evs:                                                # whole events until ~4,000 discovery markets
        sub = [m for m in disc if m["event"] == e]
        if k + len(sub) > 4000:
            continue
        pick += sub; k += len(sub)
    todo = pick + seal
    f = DIR / "candles.jsonl"; done = {json.loads(l)["ticker"] for l in open(f)} if f.exists() else set()
    todo = [m for m in todo if m["ticker"] not in done]
    print("to fetch", len(todo), flush=True)
    with open(f, "a") as out:
        for i, m in enumerate(todo):
            hi = T(m["close"]) - 24 * 3600; lo = hi - 3 * 3600; c = None
            us = (f"/historical/markets/{m['ticker']}/candlesticks", f"/series/{m['series']}/markets/{m['ticker']}/candlesticks")
            for u in (us if m["close"] < "2026-08-19" else us[::-1]):      # most settle after the historical cutoff
                try:
                    cs = get(f"{u}?start_ts={lo}&end_ts={hi}&period_interval=60").get("candlesticks", [])
                    c = max(cs, key=lambda x: int(x["end_period_ts"])) if cs else None; break
                except Exception:
                    continue
            out.write(json.dumps({**m, "candle": c}) + "\n")
            if i % 200 == 0:
                out.flush(); print(f"  {i}/{len(todo)}", flush=True)


def run(validate: bool) -> dict:
    rows = [json.loads(l) for l in open(DIR / "candles.jsonl")]
    tests = {"favourite_YES": collections.defaultdict(list), "longshot_NO": collections.defaultdict(list)}
    cat = {k: collections.defaultdict(list) for k in tests}; cap = collections.Counter()
    for r in rows:
        if (validate and not SEAL <= r["close"] < END) or (not validate and r["close"] >= SEAL) or not r["candle"]:
            continue
        yb, ya = _q(r["candle"], "yes_bid"), _q(r["candle"], "yes_ask")
        if yb is None or ya is None or not (0 < yb < ya < 1) or ya - yb > 0.05:
            continue
        mid = (yb + ya) / 2; yes = r["result"] == "yes"
        if mid >= 0.80:
            k = "favourite_YES"; q = ya; pnl = (1.0 if yes else 0.0) - q - fee(q)
        elif mid <= 0.20:
            k = "longshot_NO"; q = 1 - yb; pnl = (0.0 if yes else 1.0) - q - fee(q)
        else:
            continue
        tests[k][r["event"]].append(pnl); cat[k][r["cat"]].append(pnl); cap[k] += r["volume"]
    res = {}
    for k in tests:
        x = np.array([np.mean(v) for v in tests[k].values()]); n = len(x)
        m = float(x.mean()) if n else float("nan"); t = float(m / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
        r = {"events": n, "markets": int(sum(map(len, tests[k].values()))), "mean_net": m, "t": t, "market_volume": cap[k],
             "by_cat": {c: {"n": len(v), "mean": float(np.mean(v))} for c, v in cat[k].items()}}
        if validate:
            rng = np.random.default_rng(795)
            pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m).mean() * 100)
            post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
            r.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT"))
        else:
            r["carried"] = bool(t > 1.96 and m > 0 and sum(d["mean"] > 0 for d in r["by_cat"].values()) >= 2)
        res[k] = r
        print(f"{k}: events {n}, markets {r['markets']}, mean {m*100:+.2f}c, t {t:+.2f} | "
              + ", ".join(f"{c[:12]} {d['n']}:{d['mean']*100:+.1f}c" for c, d in r["by_cat"].items())
              + (f" -> {r.get('decision')}" if validate else ("  CARRIED" if r["carried"] else "  not carried")), flush=True)
    (ROOT / "reports" / ("k15_validation.json" if validate else "k15_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    a = sys.argv[1:2]
    {"list": listing, "candles": candles}.get(a[0] if a else "", lambda: run(a == ["validate"]))()
