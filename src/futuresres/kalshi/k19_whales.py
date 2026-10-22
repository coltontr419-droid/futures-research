"""K-family 19 (decisions.md 835): follow large takers in Kalshi's non-sports markets — copy the tape's informed flow.

    python -m futuresres.kalshi.k19_whales download     # trades of the sampled markets (resumable)
    python -m futuresres.kalshi.k19_whales              # discovery (closes 2026-08-14 -> 09-20)
    python -m futuresres.kalshi.k19_whales validate     # sealed (closes 09-21 -> 10-20), once
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
from futuresres.kalshi.k1_longshot import PRIOR_SD, fee

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "kalshi" / "k19"
SEAL = "2026-09-21"


def T(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def sample() -> list[dict]:
    ms = [json.loads(l) for l in open(ROOT / "data" / "kalshi" / "k15" / "markets.jsonl")]
    ms = [m for m in ms if m["volume"] >= 5_000 and m.get("result") in ("yes", "no") and not m["series"].startswith("KXRAIN")]   # 835 amendment
    disc = sorted((m for m in ms if m["close"] < SEAL), key=lambda m: m["ticker"]); seal = sorted((m for m in ms if m["close"] >= SEAL), key=lambda m: m["ticker"])
    random.Random(835).shuffle(disc); random.Random(835).shuffle(seal)
    return disc[:3000] + seal[:3000]


def download() -> None:
    DIR.mkdir(parents=True, exist_ok=True); out = DIR / "trades.jsonl"
    done = {json.loads(l)["ticker"] for l in open(out)} if out.exists() else set()
    todo = [m for m in sample() if m["ticker"] not in done]; print("to fetch", len(todo), flush=True)
    with open(out, "a") as fh:
        for i, m in enumerate(todo):
            tr, cur = [], None
            for _ in range(20):
                d = get(f"/markets/trades?ticker={m['ticker']}&limit=1000" + (f"&cursor={cur}" if cur else ""))
                tr += [{"t": x["created_time"], "p": float(x["yes_price_dollars"]), "q": float(x["count_fp"]), "s": x["taker_side"], "b": bool(x.get("is_block_trade"))} for x in d.get("trades", [])]
                cur = d.get("cursor")
                if not cur or not d.get("trades"):
                    break
            fh.write(json.dumps({k: m[k] for k in ("ticker", "series", "cat", "close", "result", "volume")} | {"trades": tr}) + "\n")
            if i % 200 == 0:
                fh.flush(); print(f"  {i}/{len(todo)}", flush=True)


def entry(m: dict, usd: float, lag: int) -> float | None:
    """P&L per contract of copying the first large taker (decisions.md 835), or None."""
    tr = sorted(m["trades"], key=lambda x: x["t"]); close = T(m["close"])
    for k, x in enumerate(tr):
        px = x["p"] if x["s"] == "yes" else 1.0 - x["p"]
        if x.get("b") or x["q"] * px < usd or not 0.10 <= px <= 0.90 or (close - T(x["t"])).total_seconds() <= 600:
            continue
        t0 = T(x["t"]); nxt = next((y for y in tr[k + 1:] if (T(y["t"]) - t0).total_seconds() >= lag), None)
        if nxt is None:
            return None
        p = (nxt["p"] if x["s"] == "yes" else 1.0 - nxt["p"]) + 0.01
        if p >= 1.0:
            return None
        return (1.0 if m["result"] == x["s"] else 0.0) - p - fee(p)
    return None


def run(validate: bool) -> dict:
    CFG = ((250.0, 60), (1_000.0, 60), (250.0, 300)); rows = []     # streamed: the full trade file does not fit in memory
    for l in open(DIR / "trades.jsonl"):
        m = json.loads(l)
        if (m["close"] >= SEAL) == validate:
            rows.append({"close": m["close"], "cat": m["cat"], "v": {c: entry(m, *c) for c in CFG}})

    def stats(usd: float, lag: int, sub=None) -> tuple:
        day = collections.defaultdict(list); xs = []
        for m in rows:
            if sub and m["cat"] != sub:
                continue
            v = m["v"][(usd, lag)]
            if v is not None:
                xs.append(v); day[m["close"][:10]].append(v)
        x = np.array(xs); dx = np.array([np.mean(v) for v in day.values()])
        if len(x) < 3 or len(dx) < 3:
            return np.array([]), float("nan"), float("nan"), len(x)
        return x, float(x.mean()), float(dx.mean() / (dx.std(ddof=1) / np.sqrt(len(dx)))), len(x)

    x, m_, t_d, n = stats(250.0, 60)
    res = {"markets": len(rows), "entries": n, "mean_per_contract": m_, "t_days": t_d,
           "secondary": {f"${u:,.0f} lag {g}s": stats(u, g)[1:] for u, g in ((1_000.0, 60), (250.0, 300))},
           "by_category": {c: stats(250.0, 60, c)[1:] for c in sorted({m["cat"] for m in rows})}}
    if validate:
        rng = np.random.default_rng(835)
        pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m_).mean() * 100)
        post0 = m_ * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
        res.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t_d > 1.645 and pct >= 95 and m_ > 0 and post0 > 0) else ("WATCHLIST" if m_ > 0 else "REJECT"))
    else:
        res["carried"] = bool(t_d > 1.96 and m_ > 0)
    print(f"follow large takers ($250, +60 s): markets {len(rows)}, entries {n}, mean {m_*100:+.2f}c/contract, t(days) {t_d:+.2f}"
          + (f" -> {res['decision']}" if validate else ("  CARRIED" if res["carried"] else "  not carried")), flush=True)
    for k, v in res["secondary"].items():
        print(f"  {k}: mean {v[0]*100:+.2f}c, t {v[1]:+.2f}, n {v[2]}")
    for k, v in res["by_category"].items():
        print(f"  {k}: mean {v[0]*100:+.2f}c, t {v[1]:+.2f}, n {v[2]}")
    (ROOT / "reports" / ("k19_validation.json" if validate else "k19_discovery.json")).write_text(json.dumps(res, indent=1, default=float) + "\n")
    return res


if __name__ == "__main__":
    a = sys.argv[1:2]
    download() if a == ["download"] else run(a == ["validate"])
