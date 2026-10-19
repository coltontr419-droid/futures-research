"""R-family 1 (decisions.md 736): buy NO on KXRT strikes priced 30-70c at 72 h / 48 h before the close.

    python -m futuresres.rt.r1_drift            # discovery only
    python -m futuresres.rt.r1_drift validate   # the sealed window, once
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "4")
from kalshi_api import Client  # noqa: E402

from futuresres.kalshi.k1_longshot import PRIOR_SD  # noqa: E402

OUT = ROOT / "data" / "kalshi" / "rt"
SEAL = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 10, 19, 23, tzinfo=dt.timezone.utc)
HORIZONS = (72, 48)


def markets(c: Client) -> list[dict]:
    out = []
    for base in ("/markets", "/historical/markets"):
        cur = None
        for _ in range(20):
            d = c.req("GET", f"{base}?series_ticker=KXRT&limit=1000" + ("&status=settled" if base == "/markets" else "") + (f"&cursor={cur}" if cur else ""))
            for m in d.get("markets", []):
                m["_hist"] = base != "/markets"; out.append(m)
            cur = d.get("cursor")
            if not cur or not d.get("markets"):
                break
    return out


def candles(c: Client, m: dict) -> list:
    f = OUT / f"{m['ticker']}.json"
    if f.exists():
        return json.loads(f.read_text())
    close = int(dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp())
    path = (f"/historical/markets/{m['ticker']}/candlesticks" if m["_hist"] else f"/series/KXRT/markets/{m['ticker']}/candlesticks")
    try:
        d = c.req("GET", f"{path}?start_ts={close - 5 * 86400}&end_ts={close}&period_interval=60")
    except Exception as e:
        print("candles fail", m["ticker"], str(e)[:80]); return []
    cs = d.get("candlesticks", []); f.write_text(json.dumps(cs))
    return cs


def fee(q: float) -> float:
    return math.ceil(7 * q * (1 - q)) / 100


def run(validate: bool) -> dict:
    c = Client(); OUT.mkdir(parents=True, exist_ok=True); ms = markets(c)
    ev = collections.defaultdict(lambda: collections.defaultdict(list)); impl = collections.defaultdict(list)
    # final score per event from the strike results (older markets store a label, not the score): between the highest YES strike and
    # the lowest NO strike
    br = collections.defaultdict(lambda: [-1e9, 1e9])
    for m in ms:
        if m.get("result") in ("yes", "no") and m.get("floor_strike") is not None:
            k = float(m["floor_strike"]); b = br[m["event_ticker"]]
            if m["result"] == "yes":
                b[0] = max(b[0], k)
            else:
                b[1] = min(b[1], k)
    FINAL = {e: (b[0] + b[1]) / 2 for e, b in br.items() if -1e9 < b[0] and b[1] < 1e9}
    for m in ms:
        if m.get("result") not in ("yes", "no") or m.get("floor_strike") is None:
            continue
        close = dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
        if (validate and not SEAL <= close <= END) or (not validate and close >= SEAL):
            continue
        cs = candles(c, m)
        for h in HORIZONS:
            target = int((close - dt.timedelta(hours=h)).timestamp())
            # candles exist only for hours with activity: take the last one at or before the horizon (within 6 h) - an empty hour means
            # an unchanged quote
            prior = [x for x in cs if target - 6 * 3600 <= x["end_period_ts"] <= target]
            if not prior:
                continue
            cd = prior[-1]
            px = lambda side: cd.get(side, {}).get("close_dollars", cd.get(side, {}).get("close"))  # live vs /historical field names
            yb, ya = px("yes_bid"), px("yes_ask")
            if yb is None or ya is None:
                continue
            yb, ya = float(yb), float(ya); mid = (yb + ya) / 2
            impl[(m["event_ticker"], h)].append((float(m["floor_strike"]), mid, FINAL.get(m["event_ticker"], float("nan"))))
            if not (0 < yb and ya < 1 and ya - yb <= 0.10 and 0.30 <= mid <= 0.70):
                continue
            q = 1 - yb; pnl = (1.0 if m["result"] == "no" else 0.0) - q - fee(q)
            ev[h][m["event_ticker"]].append(pnl)
    res = {}
    for h in HORIZONS:
        x = np.array([np.mean(v) for v in ev[h].values()]); n = len(x)
        m_ = float(x.mean()) if n else float("nan"); t = float(m_ / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
        gaps = []
        for (e, hh), pts in impl.items():
            if hh != h:
                continue
            pts.sort(); F = pts[0][2]
            for (k1, p1, _), (k2, p2, _) in zip(pts, pts[1:]):
                if p1 >= 0.5 > p2:
                    gaps.append(k1 + (p1 - 0.5) / (p1 - p2) * (k2 - k1) - F); break
        r = {"events": n, "strikes": int(sum(len(v) for v in ev[h].values())), "mean_net": m_, "t": t,
             "implied_median_minus_final": {"mean": float(np.mean(gaps)) if gaps else None, "n": len(gaps),
                                            "t": float(np.mean(gaps) / (np.std(gaps, ddof=1) / np.sqrt(len(gaps)))) if len(gaps) > 2 else None}}
        if validate:
            rng = np.random.default_rng(736)
            pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m_).mean() * 100)
            post0 = m_ * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
            r.update(placebo_pct=pct, posterior_zero_prior=post0,
                     decision="CONFIRM" if (t > 1.645 and pct >= 95 and m_ > 0 and post0 > 0) else ("WATCHLIST" if m_ > 0 else "REJECT"))
        else:
            r["carried"] = bool(t > 1.96 and m_ > 0)
        res[f"{h}h"] = r
        print(f"{h}h: events {n}, strikes {r['strikes']}, mean net {m_*100:+.2f}c/contract, t {t:+.2f} | implied median - final: "
              f"{r['implied_median_minus_final']['mean']} (n {len(gaps)}, t {r['implied_median_minus_final']['t']})" + (f" -> {r.get('decision')}" if validate else (" CARRIED" if r["carried"] else "")), flush=True)
    (ROOT / "reports" / ("r1_validation.json" if validate else "r1_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    run(sys.argv[1:2] == ["validate"])
