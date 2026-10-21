"""K-family 16 (decisions.md 796): sell long shots as a maker in Kalshi's non-sports markets — markout of taker-YES fills at <= 20c.

    python -m futuresres.kalshi.k16_makerls download     # public trades of the K15 sample (resumable)
    python -m futuresres.kalshi.k16_makerls              # discovery (closes before 2026-09-21; decisions.md 799)
    python -m futuresres.kalshi.k16_makerls validate     # sealed 2026-09-21 -> 2026-10-20, once
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.k1_longshot import PRIOR_SD
from futuresres.kalshi.k14_valmom import trades
from futuresres.kalshi.k15_nonsports import DIR as K15, SEAL, END

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "kalshi" / "k16"


def T(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def sample() -> list[dict]:
    """The K15 sample: the markets K15 fetched candles for (discovery pick + sealed)."""
    return [json.loads(l) for l in open(K15 / "candles.jsonl")]


def download() -> None:
    DIR.mkdir(parents=True, exist_ok=True); n = 0
    for i, m in enumerate(sample()):
        f = DIR / f"{m['ticker']}.json"
        if f.exists():
            continue
        tr = [{"t": x["created_time"], "p": float(x["yes_price_dollars"]), "q": float(x["count_fp"]), "s": x["taker_side"]} for x in trades(m["ticker"])]
        f.write_text(json.dumps({**{k: m[k] for k in ("ticker", "event", "cat", "close", "result")}, "trades": tr})); n += 1
        if i % 200 == 0:
            print(f"  {i} fetched {n}", flush=True)


def run(validate: bool) -> dict:
    per = collections.defaultdict(lambda: [0.0, 0.0]); cat = collections.defaultdict(lambda: [0.0, 0.0])
    band = collections.defaultdict(lambda: [0.0, 0.0]); ttc = collections.defaultdict(lambda: [0.0, 0.0]); pool = collections.Counter()
    hold = collections.defaultdict(list)                         # hours from fill to close (capital turnover; descriptive)
    for f in DIR.glob("*.json"):
        d = json.loads(f.read_text())
        if (validate and not SEAL <= d["close"] < END) or (not validate and d["close"] >= SEAL):
            continue
        y = 1.0 if d["result"] == "yes" else 0.0; close = T(d["close"])
        for x in d["trades"]:
            if x["s"] != "yes" or x["p"] > 0.35:
                continue
            pnl = x["p"] - y; h = (close - T(x["t"])).total_seconds() / 3600
            b = "<=20c" if x["p"] <= 0.20 else "20-35c"; band[b][0] += pnl * x["q"]; band[b][1] += x["q"]
            if x["p"] > 0.20:
                continue
            k = ">7d" if h > 168 else ("1-7d" if h > 24 else ("6-24h" if h > 6 else "<6h"))
            ttc[k][0] += pnl * x["q"]; ttc[k][1] += x["q"]
            per[d["event"]][0] += pnl * x["q"]; per[d["event"]][1] += x["q"]
            cat[d["cat"]][0] += pnl * x["q"]; cat[d["cat"]][1] += x["q"]; pool[d["cat"]] += x["q"]; hold[d["cat"]].append(h)
    x = np.array([s / q for s, q in per.values() if q > 0]); n = len(x)
    m = float(x.mean()) if n else float("nan"); t = float(m / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
    res = {"events": n, "mean_per_contract": m, "t": t,
           "by_cat": {c: {"contracts": q, "mean": s / q} for c, (s, q) in cat.items() if q},
           "by_band": {b: s / q for b, (s, q) in band.items() if q}, "by_time_to_close": {k: s / q for k, (s, q) in ttc.items() if q},
           "pool_contracts": dict(pool), "median_hours_to_close": {c: float(np.median(v)) for c, v in hold.items()}}
    if validate:
        rng = np.random.default_rng(796)
        pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m).mean() * 100)
        post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
        res.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        res["carried"] = bool(t > 1.96 and m > 0 and sum(v["mean"] > 0 for v in res["by_cat"].values()) >= 2)
    print(f"maker long-shot sale (<= 20c): events {n}, mean {m*100:+.2f}c/contract (event-weighted), t {t:+.2f} | "
          + ", ".join(f"{c[:12]} {v['contracts']:,.0f}:{v['mean']*100:+.1f}c" for c, v in res["by_cat"].items()), flush=True)
    print("  median hours fill -> close", {c[:12]: round(v, 1) for c, v in res["median_hours_to_close"].items()})
    print("  by band", {k: round(v * 100, 2) for k, v in res["by_band"].items()}, "| by time to close", {k: round(v * 100, 2) for k, v in res["by_time_to_close"].items()},
          ("-> " + res["decision"]) if validate else ("CARRIED" if res["carried"] else "not carried"))
    (ROOT / "reports" / ("k16_validation.json" if validate else "k16_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    a = sys.argv[1:2]
    download() if a == ["download"] else run(a == ["validate"])
