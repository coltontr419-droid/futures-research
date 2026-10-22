"""A-LIP2 (decisions.md 878): shadow competitive quoting on event-settled Kalshi rewards markets — public data only, no orders.

    python -m futuresres.kalshi.alip2_shadow record HOURS
    python -m futuresres.kalshi.alip2_shadow              # readout (settles fills with market results where available)
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
from kalshi_api import Client  # noqa: E402

import os
OUT = ROOT / "data" / "kalshi" / os.environ.get("ALIP_OUT", "alip2")                         # A-LIP3 (decisions.md 883): ALIP_OUT=alip3
INCLUDE = tuple(os.environ.get("ALIP_INCLUDE", "KXTRUTHSOCIAL,KXRT,KXRAIN,MENTION").split(","))
N_MARKETS, SIZE, CYCLE = int(os.environ.get("ALIP_N", "40")), 100.0, int(os.environ.get("ALIP_CYCLE", "60"))


def ts(x: str) -> dt.datetime:
    return dt.datetime.fromisoformat(x.replace("Z", "+00:00"))


def levels(ob: dict, key: str) -> list[tuple[int, float]]:
    out = []
    for it in ob.get(key + "_dollars") or ob.get(key) or []:
        p = float(it[0]); p = p * 100 if p <= 1.0 else p
        out.append((int(round(p)), float(it[1])))
    return sorted(out, key=lambda t: -t[0])


def side_share(others: list, target: float, disc: float, add: float, price: int) -> tuple[float, bool]:
    """Copy of kalshi_lip.lip_bot.side_share (decisions.md 694): our share of a side's score with `add` at `price`, and target reached."""
    L = sorted(others + ([(price, add)] if add else []), key=lambda t: -t[0])
    cum = 0.0; ref = None; q = []
    for p, s in L:
        cum += s; q.append((p, s))
        if ref is None and cum >= target / 5:
            ref = p
        if cum >= target:
            break
    if cum < target or ref is None:
        return 0.0, False
    w = lambda p: 1.0 if p >= ref else disc ** (ref - p)
    tot = sum(s * w(p) for p, s in q)
    mine = add * w(price) if add and any(p == price for p, _ in q) else 0.0
    return (mine / tot if tot > 0 else 0.0), True


def allowed(tk: str) -> bool:
    s = tk.split("-")[0]
    return any(s.startswith(x) or x in s for x in INCLUDE)


def record(hours: float) -> None:
    OUT.mkdir(parents=True, exist_ok=True); c = Client(); end = time.time() + hours * 3600
    progs: list = []; ranked_at = 0.0; last_trade: dict[str, str] = {}; quotes: dict[str, dict] = {}
    while time.time() < end:
        t0 = time.time(); now = dt.datetime.now(dt.timezone.utc)
        try:
            if time.time() - ranked_at > 3600:
                P = [p for p in c.programmes() if allowed(p["market_ticker"]) and ts(p["start_date"]) <= now < ts(p["end_date"])]
                per_day = lambda p: p["period_reward"] / 1e4 / max((ts(p["end_date"]) - ts(p["start_date"])).total_seconds() / 86400, 1e-6)
                progs = sorted(P, key=per_day, reverse=True)[:N_MARKETS]; ranked_at = time.time()
            live = [p for p in progs if ts(p["end_date"]) > now]
            books = c.orderbooks(sorted({p["market_ticker"] for p in live}))
            rows = []
            for p in live:
                tk = p["market_ticker"]; ob = books.get(tk)
                if ob is None:
                    continue
                tgt = float(p.get("target_size_fp") or 0); disc = (p.get("discount_factor_bps") or 5000) / 1e4
                dur = (ts(p["end_date"]) - ts(p["start_date"])).total_seconds(); rate_side = p["period_reward"] / 1e4 / dur / 2
                lv = {o: levels(ob, o) for o in ("yes", "no")}
                best = {o: (lv[o][0][0] if lv[o] else 0) for o in ("yes", "no")}
                q = {}
                for o in ("yes", "no"):
                    px = best[o] if best[o] >= 1 and best[o] + best["no" if o == "yes" else "yes"] < 100 else 0
                    ahead = sum(s for pp, s in lv[o] if pp == px)
                    sh, ok = side_share(lv[o], tgt, disc, SIZE, px) if px else (0.0, False)
                    q[o] = {"px": px, "ahead": ahead, "share": sh, "ok": ok}
                both = q["yes"]["ok"] and q["no"]["ok"]
                reward = (q["yes"]["share"] + q["no"]["share"]) * rate_side * CYCLE if both else 0.0
                # fills since last cycle against the quotes we held over that interval (conservative: we sit last in the queue)
                fills = []; prev = quotes.get(tk)
                try:
                    tr = c.req("GET", f"/markets/trades?ticker={tk}&limit=200").get("trades", [])
                except Exception:
                    tr = []
                new = [x for x in tr if x["created_time"] > last_trade.get(tk, now.isoformat() if tk not in last_trade else "")]
                if tr:
                    last_trade[tk] = max(x["created_time"] for x in tr)
                if prev:
                    for o, hit_by in (("yes", "no"), ("no", "yes")):
                        qp = prev[o]
                        if not qp["px"]:
                            continue
                        px_of = lambda x: round(float(x["yes_price_dollars"]) * 100) if o == "yes" else round(float(x["no_price_dollars"]) * 100)
                        hits = [x for x in new if x["taker_side"] == hit_by and px_of(x) <= qp["px"]]
                        through = sum(float(x["count_fp"]) for x in hits if px_of(x) < qp["px"])
                        at = sum(float(x["count_fp"]) for x in hits if px_of(x) == qp["px"])
                        n = min(SIZE, through + max(0.0, at - qp["ahead"]))
                        if n > 0:
                            fills.append({"side": o, "px": qp["px"], "n": n})
                quotes[tk] = q
                rows.append({"tk": tk, "reward": reward, "q": {o: {k: q[o][k] for k in ("px", "share", "ok")} for o in q}, "fills": fills,
                             "mid": (best["yes"] + (100 - best["no"])) / 2 if best["yes"] and best["no"] else None})
            with open(OUT / "shadow.jsonl", "a") as f:
                f.write(json.dumps({"t": now.isoformat(), "rows": rows}) + "\n")
        except Exception as e:
            print("cycle error", repr(e)[:200], flush=True)
        time.sleep(max(5, CYCLE - (time.time() - t0)))


def readout() -> None:
    c = Client(); rew = collections.defaultdict(float); F = collections.defaultdict(list); lastmid = {}; t_first = t_last = None
    pull = os.environ.get("ALIP_PULL") == "1"; blocked: dict[str, dt.datetime] = {}       # §883 variant: skip 6 h after a >= 5c mid move
    for l in open(OUT / "shadow.jsonl"):
        s = json.loads(l); t_first = t_first or s["t"]; t_last = s["t"]; t = ts(s["t"])
        for r in s["rows"]:
            tk = r["tk"]
            if pull and r["mid"] is not None and lastmid.get(tk) is not None and abs(r["mid"] - lastmid[tk]) >= 5:
                blocked[tk] = t + dt.timedelta(hours=6)
            lastmid[tk] = r["mid"] or lastmid.get(tk)
            if pull and blocked.get(tk) and t < blocked[tk]:
                continue
            rew[tk] += r["reward"]; F[tk] += r["fills"]
    days = max((ts(t_last) - ts(t_first)).total_seconds() / 86400, 1e-6)
    by = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0])     # reward, settled pnl, marked pnl, fills
    for tk in set(rew) | set(F):
        ser = tk.split("-")[0]; by[ser][0] += rew[tk]
        if not F[tk]:
            continue
        try:
            m = c.req("GET", f"/markets/{tk}").get("market", {}); res = m.get("result")
        except Exception:
            res = None
        for f in F[tk]:
            cost = f["n"] * f["px"] / 100; by[ser][3] += 1
            if res in ("yes", "no"):
                by[ser][1] += (f["n"] if res == f["side"] else 0.0) - cost
            elif lastmid.get(tk) is not None:
                v = lastmid[tk] / 100 if f["side"] == "yes" else 1 - lastmid[tk] / 100
                by[ser][2] += f["n"] * v - cost
    tot = [sum(v[i] for v in by.values()) for i in range(3)]
    print(f"A-LIP2 shadow over {days:.2f} days: rewards ${tot[0]:,.2f}, settled fill P&L ${tot[1]:,.2f}, unsettled (marked) ${tot[2]:,.2f} → "
          f"net ${sum(tot):,.2f} (${sum(tot) / days:,.2f}/day)")
    for ser, v in sorted(by.items(), key=lambda x: -(x[1][0] + x[1][1] + x[1][2])):
        print(f"  {ser:24} rewards ${v[0]:8.2f}  settled ${v[1]:8.2f}  marked ${v[2]:8.2f}  fills {v[3]}")


if __name__ == "__main__":
    record(float(sys.argv[2])) if sys.argv[1:2] == ["record"] else readout()
