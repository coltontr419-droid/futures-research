"""K-family 17 (decisions.md 797): political favourites a week before the price resolves — underconfidence in Kalshi politics.

    python -m futuresres.kalshi.k17_politics download    # race/nomination series -> settled markets -> daily candles (resumable)
    python -m futuresres.kalshi.k17_politics             # discovery (resolved before 2026-01-01)
    python -m futuresres.kalshi.k17_politics validate    # sealed 2026-01-01 -> 2026-10-20, once
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.download import get
from futuresres.kalshi.k1_longshot import PRIOR_SD, _q, fee

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "kalshi" / "k17"
RX = re.compile(r"^(KX)?(SENATE|HOUSE|GOV|PRES|MAYOR|ECVOTE|POPVOTE|SENATEPARTY|GOVPARTY|PRESPARTY)|NOM")
SEAL, END = "2026-01-01", "2026-10-21"


def T(s: str) -> int:
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def download() -> None:
    DIR.mkdir(parents=True, exist_ok=True); lf = DIR / "markets.json"
    if lf.exists():
        ms = json.loads(lf.read_text())
    else:
        series = sorted({s["ticker"] for c in ("Elections", "Politics") for s in get(f"/series?category={c}&limit=5000")["series"] if RX.search(s["ticker"])})
        ms = []
        for i, s in enumerate(series):
            for base in ("/historical/markets", "/markets"):
                d = get(f"{base}?series_ticker={s}&limit=1000" + ("&status=settled" if base == "/markets" else ""))
                ms += [{"ticker": m["ticker"], "event": m.get("event_ticker"), "series": s, "open": m.get("open_time"), "close": m["close_time"],
                        "result": m["result"], "volume": float(m.get("volume_fp") or 0)}
                       for m in d.get("markets", []) if m.get("result") in ("yes", "no") and float(m.get("volume_fp") or 0) >= 5000]
            if i % 100 == 0:
                print(f"  series {i}/{len(series)} markets {len(ms)}", flush=True)
        ms = list({m["ticker"]: m for m in ms}.values()); lf.write_text(json.dumps(ms))
    cf = DIR / "candles.jsonl"; done = {json.loads(l)["ticker"] for l in open(cf)} if cf.exists() else set()
    todo = [m for m in ms if m["ticker"] not in done]; print("markets", len(ms), "to fetch", len(todo), flush=True)
    with open(cf, "a") as out:
        for i, m in enumerate(todo):
            hi = T(m["close"]); lo = T(m["open"]) if m.get("open") else hi - 400 * 86400; cs = []
            for u in (f"/historical/markets/{m['ticker']}/candlesticks", f"/series/{m['series']}/markets/{m['ticker']}/candlesticks"):
                try:
                    cs = get(f"{u}?start_ts={max(lo, hi - 1000 * 86400)}&end_ts={hi}&period_interval=1440").get("candlesticks", []); break
                except Exception:
                    continue
            keep = [{"ts": int(c["end_period_ts"]), "b": _q(c, "yes_bid"), "a": _q(c, "yes_ask")} for c in cs]
            out.write(json.dumps({**m, "daily": keep}) + "\n")
            if i % 200 == 0:
                out.flush(); print(f"  {i}/{len(todo)}", flush=True)


def anchor(daily: list) -> int | None:
    """First day whose mid is >= 0.97 or <= 0.03 and stays beyond it to the end."""
    mids = [((d["b"] + d["a"]) / 2 if d["b"] is not None and d["a"] is not None else None, d["ts"]) for d in sorted(daily, key=lambda d: d["ts"])]
    r = None
    for mid, ts in reversed(mids):
        if mid is None:
            continue
        if mid >= 0.97 or mid <= 0.03:
            r = ts
        else:
            break
    return r


def run(validate: bool) -> dict:
    weeks = collections.defaultdict(list); n = 0; vol = 0.0
    for l in open(DIR / "candles.jsonl"):
        m = json.loads(l); R = anchor(m["daily"])
        if R is None:
            continue
        day = dt.datetime.fromtimestamp(R, dt.timezone.utc).strftime("%Y-%m-%d")
        if (validate and not SEAL <= day < END) or (not validate and day >= SEAL):
            continue
        e = [d for d in m["daily"] if R - 8 * 86400 < d["ts"] <= R - 7 * 86400]
        if not e or e[0]["b"] is None or e[0]["a"] is None or not 0 < e[0]["b"] < e[0]["a"] < 1 or e[0]["a"] - e[0]["b"] > 0.05:
            continue
        mid = (e[0]["b"] + e[0]["a"]) / 2
        if not 0.60 <= mid <= 0.95:
            continue
        q = e[0]["a"]; pnl = (1.0 if m["result"] == "yes" else 0.0) - q - fee(q)
        wk = dt.datetime.fromtimestamp(R, dt.timezone.utc).strftime("%G-W%V"); weeks[wk].append(pnl); n += 1; vol += m["volume"]
    x = np.array([np.mean(v) for v in weeks.values()]); k = len(x)
    mm = float(x.mean()) if k else float("nan"); t = float(mm / (x.std(ddof=1) / np.sqrt(k))) if k > 2 else float("nan")
    allm = float(np.mean([p for v in weeks.values() for p in v])) if n else float("nan")
    res = {"markets": n, "weeks": k, "mean_week": mm, "mean_market": allm, "t_weeks": t, "volume": vol,
           "weeks_detail": {w: {"n": len(v), "mean": float(np.mean(v))} for w, v in sorted(weeks.items())}}
    if validate:
        rng = np.random.default_rng(797)
        pct = float((np.array([(x * rng.choice((-1.0, 1.0), k)).mean() for _ in range(2000)]) < mm).mean() * 100)
        post0 = mm * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / k)
        res.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t > 1.645 and pct >= 95 and mm > 0 and post0 > 0) else ("WATCHLIST" if mm > 0 else "REJECT"))
    else:
        res["carried"] = bool(t > 1.96 and mm > 0)
    print(f"political favourites 7 d before resolution: markets {n}, weeks {k}, mean/market {allm*100:+.2f}c, mean/week {mm*100:+.2f}c, "
          f"t(weeks) {t:+.2f}" + (f" -> {res.get('decision')}" if validate else ("  CARRIED" if res["carried"] else "  not carried")), flush=True)
    (ROOT / "reports" / ("k17_validation.json" if validate else "k17_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    a = sys.argv[1:2]
    download() if a == ["download"] else run(a == ["validate"])
