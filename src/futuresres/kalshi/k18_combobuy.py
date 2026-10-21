"""K-family 18 (decisions.md 821): are Kalshi combo buyers at 65-95c under-charged? Trade-level buyer P&L.

    python -m futuresres.kalshi.k18_combobuy download     # list settled combos (newest first) and fetch trades of the samples
    python -m futuresres.kalshi.k18_combobuy              # discovery (closes 2026-10-10 -> 10-19)
    python -m futuresres.kalshi.k18_combobuy validate     # sealed (closes from 2026-10-20), once
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
DIR = ROOT / "data" / "kalshi" / "k18"
SERIES = ["KXMVESPORTSMULTIGAMEEXTENDED", "KXMVECROSSCATEGORY", "KXMVECROSSCATEGORY-SHARD1", "KXMVECROSSCATEGORY0", "KXMVECROSSCATEGORY0-SHARD1"]
D0, SEAL = "2026-10-10", "2026-10-20"


def listing() -> list[dict]:
    f = DIR / "combos.json"
    if f.exists():
        return json.loads(f.read_text())
    out = []
    for s in SERIES:
        cur = None
        while True:
            d = get(f"/markets?series_ticker={s}&status=settled&limit=1000" + (f"&cursor={cur}" if cur else ""))
            ms = d.get("markets", [])
            out += [{"ticker": m["ticker"], "close": m["close_time"], "result": m["result"], "volume": float(m.get("volume_fp") or 0), "series": s}
                    for m in ms if m.get("result") in ("yes", "no") and float(m.get("volume_fp") or 0) > 0 and m.get("close_time", "") >= D0]
            cur = d.get("cursor")
            if not cur or not ms or min(m.get("close_time", "9") for m in ms) < D0:
                break
        print(s, "listed so far", len(out), flush=True)
    f.write_text(json.dumps(out)); return out


def download() -> None:
    DIR.mkdir(parents=True, exist_ok=True); ms = listing()
    disc = [m for m in ms if m["close"] < SEAL]; seal = [m for m in ms if m["close"] >= SEAL]
    random.Random(821).shuffle(disc); random.Random(821).shuffle(seal)
    todo = disc[:6000] + seal[:6000]; out = DIR / "trades.jsonl"
    done = {json.loads(l)["ticker"] for l in open(out)} if out.exists() else set()
    todo = [m for m in todo if m["ticker"] not in done]; print("combos", len(ms), "(disc", len(disc), "sealed", len(seal), ") to fetch", len(todo), flush=True)
    with open(out, "a") as fh:
        for i, m in enumerate(todo):
            tr = get(f"/markets/trades?ticker={m['ticker']}&limit=1000").get("trades", [])
            fh.write(json.dumps({**m, "trades": [{"t": x["created_time"], "p": float(x["yes_price_dollars"]), "q": float(x["count_fp"]), "s": x["taker_side"]} for x in tr]}) + "\n")
            if i % 500 == 0:
                fh.flush(); print(f"  {i}/{len(todo)}", flush=True)


def run(validate: bool) -> dict:
    per, day = {}, collections.defaultdict(list); band = collections.defaultdict(lambda: [0.0, 0.0]); legs_hrs = collections.defaultdict(lambda: [0.0, 0.0])
    for l in open(DIR / "trades.jsonl"):
        m = json.loads(l)
        if (validate and m["close"] < SEAL) or (not validate and not (D0 <= m["close"] < SEAL)):
            continue
        y = 1.0 if m["result"] == "yes" else 0.0; close = dt.datetime.fromisoformat(m["close"].replace("Z", "+00:00")); s = q = 0.0
        for x in m["trades"]:
            if x["s"] != "yes":
                continue
            pnl = y - x["p"] - fee(x["p"])
            b = "2-35c" if x["p"] < 0.35 else ("35-65c" if x["p"] < 0.65 else ("65-95c" if x["p"] <= 0.95 else ">95c"))
            band[b][0] += pnl * x["q"]; band[b][1] += x["q"]
            if b == "65-95c":
                s += pnl * x["q"]; q += x["q"]
                h = (close - dt.datetime.fromisoformat(x["t"].replace("Z", "+00:00"))).total_seconds() / 3600
                k = "<1h" if h < 1 else ("1-6h" if h < 6 else ">6h"); legs_hrs[k][0] += pnl * x["q"]; legs_hrs[k][1] += x["q"]
        if q > 0:
            per[m["ticker"]] = s / q; day[m["close"][:10]].append(s / q)
    x = np.array(list(per.values())); n = len(x); dx = np.array([np.mean(v) for v in day.values()]); nd = len(dx)
    m_ = float(x.mean()) if n else float("nan"); t_c = float(m_ / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
    t_d = float(dx.mean() / (dx.std(ddof=1) / np.sqrt(nd))) if nd > 2 else float("nan")
    res = {"combos": n, "days": nd, "mean_per_contract": m_, "t_combos": t_c, "t_days": t_d,
           "bands": {k: s / q for k, (s, q) in band.items() if q}, "by_hours_to_close": {k: s / q for k, (s, q) in legs_hrs.items() if q}}
    if validate:
        rng = np.random.default_rng(821)
        pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m_).mean() * 100)
        post0 = m_ * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
        res.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t_d > 1.645 and pct >= 95 and m_ > 0 and post0 > 0) else ("WATCHLIST" if m_ > 0 else "REJECT"))
    else:
        res["carried"] = bool(t_d > 1.96 and m_ > 0)
    print(f"combo buyers 65-95c: combos {n}, mean {m_*100:+.2f}c/contract, t(combos) {t_c:+.2f}, t(days, n {nd}) {t_d:+.2f} | bands "
          + ", ".join(f"{k} {v*100:+.2f}c" for k, v in res["bands"].items()) + " | by hours to close "
          + ", ".join(f"{k} {v*100:+.2f}c" for k, v in res["by_hours_to_close"].items())
          + (f" -> {res.get('decision')}" if validate else ("  CARRIED" if res["carried"] else "  not carried")), flush=True)
    (ROOT / "reports" / ("k18_validation.json" if validate else "k18_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    a = sys.argv[1:2]
    download() if a == ["download"] else run(a == ["validate"])
