"""K-family 14 (decisions.md 777): in-play under-reaction in Kalshi Valorant match markets — follow a fast move 5 s late.

    python -m futuresres.kalshi.k14_valmom download     # trades of one market per settled KXVALORANTGAME event
    python -m futuresres.kalshi.k14_valmom              # discovery: matches settled before 2026-10-20 20:00Z
    python -m futuresres.kalshi.k14_valmom forward      # sealed forward test (decisions.md 777), once at >= 60 matches
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.download import get
from futuresres.kalshi.k1_longshot import PRIOR_SD, fee
from futuresres.kalshi.lean import listing

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "kalshi" / "k14"
SERIES = "KXVALORANTGAME"
CUT = "2026-10-20T20:00:00Z"


def T(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def trades(tk: str) -> list:
    out = []
    for base in ("/markets/trades", "/historical/trades"):
        cur = None
        for _ in range(200):
            d = get(f"{base}?ticker={tk}&limit=1000" + (f"&cursor={cur}" if cur else ""))
            out += [{k: x.get(k) for k in ("created_time", "yes_price_dollars", "count_fp", "taker_side")} for x in d.get("trades", [])]
            cur = d.get("cursor")
            if not cur or not d.get("trades"):
                break
        if out:
            return sorted(out, key=lambda x: x["created_time"])
    return out


def download() -> None:
    from futuresres.kalshi import download as dl
    dl.RATE = 3.0                                                  # shares the limit with other downloads
    OUT.mkdir(parents=True, exist_ok=True)
    ms = listing(SERIES); ev = collections.defaultdict(list)
    for m in ms:
        ev[m["event_ticker"]].append(m)
    todo = [e for e in sorted(ev) if not (OUT / f"{e}.json").exists()]
    print(len(ev), "settled events,", len(todo), "to fetch", flush=True)
    for i, e in enumerate(todo):
        m = sorted(ev[e], key=lambda x: x["ticker"])[0]
        (OUT / f"{e}.json").write_text(json.dumps({"event": e, "ticker": m["ticker"], "result": m["result"], "close": m["close_time"],
                                                   "trades": trades(m["ticker"])}))
        if i % 50 == 0:
            print(f"  {i}/{len(todo)}", flush=True)


def signals(tr: list) -> list[float]:
    """P&L a contract of each signal in one market (decisions.md 777)."""
    px = [(T(x["created_time"]), float(x["yes_price_dollars"]), x["taker_side"]) for x in tr]
    out, last = [], None
    for i, (t, p, _) in enumerate(px):
        if last and (t - last).total_seconds() < 120:
            continue
        ref = [q for u, q, _ in px[max(0, i - 2000):i] if t - dt.timedelta(seconds=120) <= u <= t - dt.timedelta(seconds=10)]
        if len(ref) < 3 or abs(p - st.median(ref)) < 0.10:
            continue
        up = p > st.median(ref); last = t
        ent = next((q for u, q, sd in px[i:] if u >= t + dt.timedelta(seconds=5) and (sd == "yes") == up), None)
        ex = [(q, u) for u, q, _ in px[i:] if t + dt.timedelta(seconds=60) <= u <= t + dt.timedelta(seconds=120)]
        if ent is None or not ex or not 0 < ent < 1:
            continue
        vw = sum(q for q, _ in ex) / len(ex)
        cost = ent if up else 1 - ent; val = (vw if up else 1 - vw) - 0.01
        out.append(val - cost - fee(cost) - fee(min(max(val, 0.01), 0.99)))
    return out


def run(forward: bool) -> dict:
    per, blocks = {}, collections.defaultdict(list)
    for f in sorted(OUT.glob("*.json")):
        d = json.loads(f.read_text())
        if not d["trades"] or (forward and d["trades"][0]["created_time"] < CUT) or (not forward and d["close"] >= CUT):
            continue
        s = signals(d["trades"])
        if s:
            per[d["event"]] = s; c = T(d["close"]); blocks[f"{c.year}Q{(c.month - 1) // 3 + 1}"].append(float(np.mean(s)))
    x = np.array([np.mean(v) for v in per.values()]); n = len(x)
    m = float(x.mean()) if n else float("nan"); t = float(m / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
    res = {"matches": n, "signals": int(sum(map(len, per.values()))), "mean_per_contract": m, "t": t,
           "blocks": {k: {"n": len(v), "mean": float(np.mean(v))} for k, v in sorted(blocks.items())}}
    if forward:
        rng = np.random.default_rng(777)
        pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m).mean() * 100)
        post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
        res.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        res["carried"] = bool(t > 1.96 and m > 0 and sum(b["mean"] > 0 for b in res["blocks"].values()) >= 2)
    print(f"K14 {'forward' if forward else 'discovery'}: matches {n}, signals {res['signals']}, mean {m*100:+.2f}c/contract, t {t:+.2f} | "
          + ", ".join(f"{k} {b['n']}:{b['mean']*100:+.1f}c" for k, b in res["blocks"].items())
          + (f" -> {res.get('decision')}" if forward else ("  CARRIED" if res["carried"] else "  not carried")), flush=True)
    (ROOT / "reports" / ("k14_forward.json" if forward else "k14_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    a = sys.argv[1:2]
    if a == ["download"]:
        download()
    else:
        run(a == ["forward"])
