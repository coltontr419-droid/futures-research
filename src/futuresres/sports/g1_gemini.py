"""G1 (decisions.md 888): shadow quoting on Gemini Predictions NFL liquidity-reward markets — public data only, no orders.

    python -m futuresres.sports.g1_gemini record HOURS
    python -m futuresres.sports.g1_gemini              # readout (settles fills from contract results where available)
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "gemini" / "g1"
API = "https://api.gemini.com"
N, SIZE, HALF, CYCLE = 60, 100.0, 0.02, 120


def get(path: str):
    for k in range(3):
        try:
            time.sleep(0.35)
            return json.loads(urllib.request.urlopen(urllib.request.Request(API + path, headers={"User-Agent": "research"}), timeout=30).read())
        except Exception:
            time.sleep(2 ** k)
    return None


def ts(x: str) -> dt.datetime:
    return dt.datetime.fromisoformat(x.replace("Z", "+00:00"))


def universe(now: dt.datetime) -> list[dict]:
    ev = []
    for off in range(0, 2000, 50):
        d = get(f"/v1/prediction-markets/liquidity-rewards/events?limit=50&offset={off}")
        if not d:
            break
        ev += d["events"]
        if off + 50 >= d["pagination"]["total"]:
            break
    nfl = sorted((e for e in ev if e["category"] == "Pro Football"), key=lambda e: e["event_ticker"])
    out = []
    for e in nfl:
        try:
            start = dt.datetime.strptime(e["event_ticker"].split("-")[1], "%y%m%d%H%M").replace(tzinfo=dt.timezone.utc)   # game time in the ticker (UTC)
        except (IndexError, ValueError):
            continue
        if now < start <= now + dt.timedelta(days=5):
            out.append({"ticker": e["event_ticker"], "pool": float(e["daily_pool_usd"]), "start": start.isoformat()})
    random.Random(888 + now.toordinal()).shuffle(out)
    keep = []
    for u in out:
        if len(keep) >= N:
            break
        x = get(f"/v1/prediction-markets/events/{u['ticker']}")
        if x and x.get("contracts"):
            c = x["contracts"][0]; keep.append(u | {"symbol": c["instrumentSymbol"].lower(), "label": c.get("label")})
    return keep


def fair_mid(bk: dict, sym_info: dict) -> float | None:
    bids = [float(b["price"]) for b in bk.get("bids", [])]; asks = [float(a["price"]) for a in bk.get("asks", [])]
    if bids and asks:
        return (max(bids) + min(asks)) / 2
    return None


def record(hours: float) -> None:
    OUT.mkdir(parents=True, exist_ok=True); end = time.time() + hours * 3600
    U: list = []; drawn = None; last_tid: dict = {}; quotes: dict = {}
    while time.time() < end:
        t0 = time.time(); now = dt.datetime.now(dt.timezone.utc)
        try:
            if drawn != now.date():
                U = universe(now); drawn = now.date(); print(now.isoformat(), "universe", len(U), flush=True)
            rows = []
            for u in U:
                if now >= ts(u["start"]):
                    continue
                bk = get(f"/v1/book/{u['symbol']}?limit_bids=30&limit_asks=30") or {}
                mid = fair_mid(bk, u)
                if mid is None:
                    ev = get(f"/v1/prediction-markets/events/{u['ticker']}") or {}
                    try:
                        mid = float(ev["contracts"][0]["prices"].get("lastTradePrice") or 0) or None
                    except Exception:
                        mid = None
                bids = [(float(b["price"]), float(b["amount"])) for b in bk.get("bids", [])]
                asks = [(float(a["price"]), float(a["amount"])) for a in bk.get("asks", [])]
                q = None
                if mid is not None and 0.03 <= mid <= 0.97:
                    bp, ap = round(mid - HALF, 2), round(mid + HALF, 2)
                    if asks and bp >= min(p for p, _ in asks):
                        bp = round(min(p for p, _ in asks) - 0.01, 2)
                    if bids and ap <= max(p for p, _ in bids):
                        ap = round(max(p for p, _ in bids) + 0.01, 2)
                    if 0.01 <= bp < ap <= 0.99 and ap - bp <= 0.10:
                        q = {"bp": bp, "ap": ap, "mid": mid}
                reward = 0.0
                if q:
                    mine = SIZE / max(q["ap"] - q["bp"], 0.001) ** 2 * 2
                    others = sum(s / max(2 * abs(p - mid), 0.01) ** 2 for p, s in bids + asks if abs(p - mid) <= 0.05)
                    reward = u["pool"] / 1440 * (CYCLE / 60) * mine / (mine + others)
                # fills against the quote we held over the last interval
                fills = []; prev = quotes.get(u["symbol"])
                tr = get(f"/v1/trades/{u['symbol']}?limit_trades=100") or []
                new = [x for x in tr if x["tid"] > last_tid.get(u["symbol"], -1)] if u["symbol"] in last_tid else []
                if tr:                                         # monotonic: a stale page must not move the marker back (old trades re-counted)
                    last_tid[u["symbol"]] = max(last_tid.get(u["symbol"], -1), max(x["tid"] for x in tr))
                if prev:
                    ahead_b = sum(s for p, s in prev["bids"] if p > prev["bp"]); ahead_a = sum(s for p, s in prev["asks"] if p < prev["ap"])
                    for x in new:
                        p, a = float(x["price"]), float(x["amount"])
                        if x["type"] == "sell" and p <= prev["bp"]:
                            fills.append({"side": "buy_yes", "px": prev["bp"], "n": min(SIZE, a), "tid": x["tid"]})       # taker sold into our bid
                        if x["type"] == "buy" and p >= prev["ap"]:
                            fills.append({"side": "sell_yes", "px": prev["ap"], "n": min(SIZE, a), "tid": x["tid"]})      # taker bought our offer
                quotes[u["symbol"]] = (q | {"bids": bids, "asks": asks}) if q else None
                rows.append({"ticker": u["ticker"], "symbol": u["symbol"], "q": q, "reward": reward, "fills": fills,
                             "top": [bids[0] if bids else None, asks[0] if asks else None]})
            with open(OUT / "shadow.jsonl", "a") as f:
                f.write(json.dumps({"t": now.isoformat(), "rows": rows}) + "\n")
        except Exception as e:
            print("cycle error", repr(e)[:200], flush=True)
        time.sleep(max(5, CYCLE - (time.time() - t0)))


def readout() -> None:
    rew = collections.defaultdict(float); F = collections.defaultdict(list); quoted = collections.Counter(); t_first = t_last = None; tk_of = {}
    seen_fill: set = set()
    for l in open(OUT / "shadow.jsonl"):
        s = json.loads(l)
        # a cycle's quote stands until the next cycle: credit the real elapsed time (cap 15 min), not the nominal CYCLE seconds
        el = min((ts(s["t"]) - ts(t_last)).total_seconds(), 900) if t_last else CYCLE
        t_first = t_first or s["t"]; t_last = s["t"]
        for r in s["rows"]:
            rew[r["symbol"]] += r["reward"] * el / CYCLE; quoted[r["symbol"]] += bool(r["q"]); tk_of[r["symbol"]] = r["ticker"]
            left = {"buy_yes": SIZE, "sell_yes": SIZE}                  # our quote is SIZE per side between re-quotes: cap the cycle's fills
            for f in r["fills"]:
                key = (r["symbol"], f.get("tid")) if f.get("tid") else (r["symbol"], f["side"], f["px"], f["n"])
                if key in seen_fill:                                     # re-counted trades (stale pages before the fix) dropped
                    continue
                seen_fill.add(key)
                n = min(f["n"], left[f["side"]])
                if n > 0:
                    left[f["side"]] -= n; F[r["symbol"]].append(f | {"n": n})
    days = max((ts(t_last) - ts(t_first)).total_seconds() / 86400, 1e-6)
    kind = lambda tk: tk.split("-")[-1][:2] if tk.split("-")[-1][:1].isdigit() else "game"
    by = collections.defaultdict(lambda: [0.0, 0.0, 0, 0])            # reward, fill pnl (settled), fills, unsettled fills
    for sym in rew:
        k = kind(tk_of[sym]); by[k][0] += rew[sym]
        if not F[sym]:
            continue
        ev = get(f"/v1/prediction-markets/events/{tk_of[sym]}") or {}
        c = next((c for c in ev.get("contracts", []) if c.get("instrumentSymbol", "").lower() == sym), {})
        res = c.get("resolutionSide") or c.get("settlementValue") or c.get("result")      # Gemini: resolutionSide "yes" / "no"
        for f in F[sym]:
            by[k][2] += 1
            if res is None:
                by[k][3] += 1; continue
            v = 1.0 if str(res).lower() in ("1", "1.0", "yes", "true") else 0.0
            by[k][1] += f["n"] * ((v - f["px"]) if f["side"] == "buy_yes" else (f["px"] - v))
    tot_r = sum(v[0] for v in by.values()); tot_p = sum(v[1] for v in by.values())
    print(f"G1 Gemini shadow over {days:.2f} days, {len(rew)} markets: rewards ${tot_r:,.2f} (${tot_r / days:,.0f}/day), settled fill P&L ${tot_p:,.2f}, "
          f"unsettled fills {sum(v[3] for v in by.values())}")
    for k, v in sorted(by.items(), key=lambda x: -x[1][0]):
        print(f"  {k:5} rewards ${v[0]:9.2f}  fill P&L ${v[1]:8.2f}  fills {v[2]} (unsettled {v[3]})")


if __name__ == "__main__":
    record(float(sys.argv[2])) if sys.argv[1:2] == ["record"] else readout()
