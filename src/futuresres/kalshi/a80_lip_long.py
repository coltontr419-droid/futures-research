"""A80 (decisions.md 696): longer liquidity programmes - reward share against fills measured from 72 hours of public trades. No orders.

    python -m futuresres.kalshi.a80_lip_long
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
from kalshi_api import Client  # noqa: E402
from lip_bot import levels, side_share  # noqa: E402

OUT = ROOT / "reports" / "a80_lip_long.json"
HOURS = 72


def ts(x):
    return dt.datetime.fromisoformat(x.replace("Z", "+00:00"))


def trades_at_1c(c: Client, ticker: str, since: dt.datetime) -> dict:
    """Contracts traded in the last HOURS against resting 1c bids: on the yes side (taker sold yes at 1c) and on the no side (taker sold no at 1c)."""
    out = {"yes": 0.0, "no": 0.0}; cur = None; mts = int(since.timestamp())
    for _ in range(20):
        d = c.req("GET", f"/markets/trades?ticker={ticker}&min_ts={mts}&limit=1000" + (f"&cursor={cur}" if cur else ""))
        for t in d.get("trades", []):
            yp = float(t.get("yes_price_dollars") or 0); n = float(t.get("count_fp") or 0); side = t.get("taker_outcome_side") or t.get("taker_side")
            if yp <= 0.0101 and side == "no":
                out["yes"] += n                      # a yes bid at 1c was hit
            elif yp >= 0.9899 and side == "yes":
                out["no"] += n                       # a no bid at 1c was hit
        cur = d.get("cursor")
        if not cur or not d.get("trades"):
            break
    return out


def measure(c, P, books, now, label, cap=400):
    since = now - dt.timedelta(hours=HOURS); rows = []
    cands = []
    for p in P:
        tk = p["market_ticker"]; ob = books.get(tk)
        if ob is None:
            continue
        tgt = float(p.get("target_size_fp") or 0); disc = (p.get("discount_factor_bps") or 5000) / 1e4
        if tgt <= 0:
            continue
        sides = {"yes": levels(ob, "yes"), "no": levels(ob, "no")}
        best = {o: max((pp for pp, _ in sides[o]), default=0) for o in sides}
        can = {"yes": best["no"] < 99, "no": best["yes"] < 99}
        need = {o: sum(s for _, s in sides[o]) < tgt for o in sides}
        if not any(need.values()) or any(need[o] and not can[o] for o in sides):
            continue
        add = {o: (tgt if need[o] else 0.0) for o in sides}
        sy, qy = side_share(sides["yes"], tgt, disc, add["yes"], 1); sn, qn = side_share(sides["no"], tgt, disc, add["no"], 1)
        if not (qy and qn):
            continue
        dur = (ts(p["end_date"]) - ts(p["start_date"])).total_seconds(); reward_day = p["period_reward"] / 1e4 / dur * 86400
        ahead = {o: sum(s for pp, s in sides[o] if pp == 1) for o in sides}
        cands.append((p, tgt, [o for o in sides if need[o]], (sy + sn) / 2, reward_day, ahead))
    random.seed(696); random.shuffle(cands)
    for p, tgt, need, share, rday, ahead in cands[:cap]:
        try:
            tr = trades_at_1c(c, p["market_ticker"], since)
        except Exception:
            continue
        fills = sum(max(0.0, tr[o] - ahead[o]) for o in need) / (HOURS / 24)
        fills = min(fills, tgt * len(need) * 24)                 # can't be filled more than the order each hour, refreshed
        reward = share * rday; net = reward - fills * 0.01
        rows.append({"ticker": p["market_ticker"], "series": p["market_ticker"].split("-")[0], "dur_days": (ts(p["end_date"]) - ts(p["start_date"])).days,
                     "need": need, "share": share, "reward_day": reward, "fills_day": fills, "net_day": net, "collateral": tgt * len(need) * 0.01,
                     "traded_1c_72h": tr, "ahead": ahead})
    pos = [r for r in rows if r["net_day"] > 0]
    tot_net = sum(r["net_day"] for r in rows); tot_rew = sum(r["reward_day"] for r in rows); tot_fill = sum(r["fills_day"] * 0.01 for r in rows)
    coll = sum(r["collateral"] for r in rows)
    print(f"== {label}: {len(P)} programmes, {len(cands)} completable thin, measured {len(rows)}", flush=True)
    print(f"   reward ${tot_rew:,.0f}/day, fill cost ${tot_fill:,.0f}/day, net ${tot_net:,.0f}/day on ${coll:,.0f} collateral; net-positive {len(pos)}/{len(rows)}; "
          f"markets with any 1c fills in 72 h: {sum(1 for r in rows if r['fills_day'] > 0)}", flush=True)
    by = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for r in rows:
        b = by[r["series"]]; b[0] += 1; b[1] += r["net_day"]; b[2] += r["fills_day"]
    for k, v in sorted(by.items(), key=lambda kv: -kv[1][1])[:10]:
        print(f"     {k:26} markets {v[0]:3}  net ${v[1]:8,.0f}/day  fills {v[2]:8,.0f} contracts/day", flush=True)
    return {"label": label, "programmes": len(P), "completable": len(cands), "rows": rows, "net_day": tot_net, "reward_day": tot_rew, "fill_cost_day": tot_fill}


def main() -> int:
    c = Client(); now = dt.datetime.now(dt.timezone.utc)
    P = [p for p in c.programmes() if ts(p["start_date"]) <= now < ts(p["end_date"])]
    long_ = [p for p in P if (ts(p["end_date"]) - ts(p["start_date"])).total_seconds() >= 6 * 86400 and ts(p["end_date"]) - now >= dt.timedelta(days=1)]
    short = [p for p in P if (ts(p["end_date"]) - ts(p["start_date"])).total_seconds() <= 2 * 86400 and ts(p["end_date"]) - now >= dt.timedelta(minutes=20)]
    books = c.orderbooks(sorted({p["market_ticker"] for p in long_ + short}))
    out = {"time": now.isoformat(timespec="seconds"), "long": measure(c, long_, books, now, "long (>= 6 days)"),
           "short_control": measure(c, short, books, now, "short control (<= 2 days)", cap=150)}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
