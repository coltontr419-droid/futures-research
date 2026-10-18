"""Kalshi liquidity-incentive bot (decisions.md 692-694): completes thin order books in short incentive programmes.

Every LOOP_SEC: list active liquidity programmes lasting <= MAX_DAYS; read their books; a side whose OTHER traders' resting size is below the
programme's target gets our target-size bid at PRICE_CENTS (1c) on that side (post-only, expiring at the programme's end), the best
MAX_MARKETS by estimated reward per $ of collateral, within MAX_COLLATERAL. Orders on sides that no longer need us are cancelled. Each
loop accrues an ESTIMATE of earnings from the published scoring; a Discord summary posts daily (and at start).

    MODE=dry  python lip_bot.py     (no key needed: plans and estimates only)
    MODE=live python lip_bot.py     (needs KALSHI_KEY_ID and KALSHI_KEY_PATH)
Kill switch: create the file STOP beside this script - every order is cancelled and the bot exits.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import traceback
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent


def _load_env(p: Path) -> None:
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


_load_env(HERE / ".env")
from kalshi_api import Client  # noqa: E402  (after the environment is loaded)

ET = ZoneInfo("America/New_York")
MODE = os.environ.get("MODE", "dry")
MAX_MARKETS = int(os.environ.get("MAX_MARKETS", "10"))
MAX_COLLATERAL = float(os.environ.get("MAX_COLLATERAL", "150"))
MAX_DAYS = float(os.environ.get("MAX_DAYS", "2"))
PRICE_CENTS = int(os.environ.get("PRICE_CENTS", "1"))
LOOP_SEC = int(os.environ.get("LOOP_SEC", "300"))
MIN_LEFT_MIN = 20                                   # don't enter a programme ending within this many minutes
STATE = HERE / os.environ.get("STATE_FILE", "state.json"); LOG = HERE / "lip_log.jsonl"; STOP = HERE / "STOP"
DISCORD_ENV = Path(os.environ.get("DISCORD_ENV", "/opt/futures-bot/.env"))


def ts(x: str) -> dt.datetime:
    return dt.datetime.fromisoformat(x.replace("Z", "+00:00"))


def levels(ob: dict, key: str) -> list[tuple[int, float]]:
    out = []
    for it in ob.get(key + "_dollars") or ob.get(key) or []:
        p = float(it[0]); p = p * 100 if p <= 1.0 else p
        out.append((int(round(p)), float(it[1])))
    return sorted(out, key=lambda t: -t[0])


def side_share(others: list, target: float, disc: float, add: float, price: int) -> tuple[float, bool]:
    """Our share of a side's score with `add` contracts at `price` added to `others`, and whether the side reaches the target."""
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
    # every order at a qualifying price level counts in full (the filing adds "the size available at the current bid price")
    mine = add * w(price) if add and any(p == price for p, _ in q) else 0.0
    return (mine / tot if tot > 0 else 0.0), True


def discord(text: str) -> None:
    env = {}
    if DISCORD_ENV.exists():
        for line in DISCORD_ENV.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1); env[k.strip()] = v.strip()
    if not env.get("DISCORD_TOKEN") or not env.get("DISCORD_CHANNEL_ID"):
        print("[discord skipped]", text[:200], flush=True); return
    try:
        req = urllib.request.Request(f"https://discord.com/api/v10/channels/{env['DISCORD_CHANNEL_ID']}/messages", method="POST",
                                     data=json.dumps({"content": text[:1990]}).encode(),
                                     headers={"Authorization": f"Bot {env['DISCORD_TOKEN']}", "Content-Type": "application/json", "User-Agent": "lip-bot"})
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:
        print("discord error", e, flush=True)


def load_state() -> dict:
    s = json.loads(STATE.read_text()) if STATE.exists() else {}
    s.setdefault("orders", {}); s.setdefault("est_by_day", {}); s.setdefault("est_total", 0.0); s.setdefault("last_summary", "")
    s.setdefault("started", dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")); s.setdefault("verified", False)
    return s


def save_state(s: dict) -> None:
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(s, indent=1)); tmp.replace(STATE)


def log(**kw) -> None:
    with LOG.open("a") as f:
        f.write(json.dumps({"t": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **kw}) + "\n")


def plan(c: Client, st: dict, now: dt.datetime) -> tuple[list[dict], dict]:
    P = [p for p in c.programmes() if ts(p["start_date"]) <= now < ts(p["end_date"]) - dt.timedelta(minutes=MIN_LEFT_MIN)
         and (ts(p["end_date"]) - ts(p["start_date"])).total_seconds() <= MAX_DAYS * 86400]
    books = c.orderbooks(sorted({p["market_ticker"] for p in P}))
    mine = {}                                                    # (ticker, outcome) -> (price, size) of our resting orders
    for t, o in st["orders"].items():
        mine[(o["ticker"], o["outcome"])] = (o["cents"], o["count"])
    cands = []
    for p in P:
        tk = p["market_ticker"]; ob = books.get(tk)
        if ob is None:
            continue
        tgt = float(p.get("target_size_fp") or 0); disc = (p.get("discount_factor_bps") or 5000) / 1e4
        if tgt <= 0:
            continue
        sides = {}
        for outcome, key in (("yes", "yes"), ("no", "no")):
            lv = levels(ob, key)
            if (tk, outcome) in mine:                            # remove our own size from the book before judging thinness
                mp, ms = mine[(tk, outcome)]
                lv = [(pp, s - ms if pp == mp else s) for pp, s in lv]; lv = [(pp, s) for pp, s in lv if s > 1e-9]
            sides[outcome] = lv
        need = {o: sum(s for _, s in sides[o]) < tgt for o in ("yes", "no")}
        if not any(need.values()):
            continue
        add = {o: (tgt if need[o] else 0.0) for o in ("yes", "no")}
        sy, qy = side_share(sides["yes"], tgt, disc, add["yes"], PRICE_CENTS); sn, qn = side_share(sides["no"], tgt, disc, add["no"], PRICE_CENTS)
        if not (qy and qn):
            continue
        dur = (ts(p["end_date"]) - ts(p["start_date"])).total_seconds(); reward = p["period_reward"] / 1e4
        rate = (sy + sn) / 2 * reward / dur                      # $ a second while it holds
        coll = sum(add.values()) * PRICE_CENTS / 100
        cands.append({"ticker": tk, "pid": p["id"], "end": p["end_date"], "need": [o for o in ("yes", "no") if need[o]], "count": int(tgt),
                      "rate": rate, "collateral": coll, "share": (sy + sn) / 2, "reward": reward, "dur_h": dur / 3600})
    cands.sort(key=lambda x: -x["rate"] / max(x["collateral"], 0.01))
    chosen, used = [], 0.0
    held = {o["ticker"] for o in st["orders"].values()}
    for x in sorted(cands, key=lambda x: (x["ticker"] not in held, -x["rate"] / max(x["collateral"], 0.01))):   # keep what we hold first
        if len(chosen) < MAX_MARKETS and used + x["collateral"] <= MAX_COLLATERAL:
            chosen.append(x); used += x["collateral"]
    return chosen, {"programmes": len(P), "candidates": len(cands)}


def verify(c: Client, oid: str, outcome: str) -> bool:
    """After the first live order: it must rest on the intended outcome at PRICE_CENTS of that outcome."""
    for o in c.resting():
        if o.get("order_id") == oid:
            raw = json.dumps(o)
            side = o.get("side") or o.get("book_side") or o.get("outcome_side")
            yes_p = o.get("yes_price_dollars") or o.get("price") or o.get("yes_price")
            yp = float(yes_p) * (100 if float(yes_p) <= 1 else 1)
            want = PRICE_CENTS if outcome == "yes" else 100 - PRICE_CENTS
            ok = (side in (("yes", "bid") if outcome == "yes" else ("no", "ask"))) and abs(yp - want) < 0.5
            log(event="verify", ok=ok, order=raw[:600]); return ok
    log(event="verify", ok=False, note="order not found among resting"); return False


def step(c: Client, st: dict) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    chosen, info = plan(c, st, now)
    want = {(x["ticker"], o): x for x in chosen for o in x["need"]}
    live = MODE == "live"
    # cancel orders no longer wanted (side filled up by others, programme ended, or dropped from the chosen set)
    for key, o in list(st["orders"].items()):
        if (o["ticker"], o["outcome"]) not in want or ts(o["end"]) <= now:
            if live:
                try:
                    c.cancel(o["order_id"], o["ticker"])
                except Exception as e:
                    log(event="cancel_error", key=key, err=str(e)[:300])
            log(event="cancel", key=key); st["orders"].pop(key)
    # place what is missing
    for (tk, outcome), x in want.items():
        key = f"{tk}|{outcome}"
        if key in st["orders"]:
            continue
        oid = f"dry-{key}"
        if live:
            r = c.place(tk, outcome, PRICE_CENTS, x["count"], expires=int(ts(x["end"]).timestamp()))
            oid = (r.get("order") or r).get("order_id") or r.get("order_id")
            if not st["verified"]:
                if not verify(c, oid, outcome):
                    discord("**Kalshi LIP bot: first order did not verify — cancelling everything and stopping.** See lip_log.jsonl.")
                    shutdown(c, st); sys.exit(2)
                st["verified"] = True
        st["orders"][key] = {"ticker": tk, "outcome": outcome, "cents": PRICE_CENTS, "count": x["count"], "order_id": oid, "end": x["end"],
                             "pid": x["pid"], "placed": now.isoformat(timespec="seconds")}
        log(event="place", key=key, count=x["count"], cents=PRICE_CENTS, mode=MODE)
    # accrue the estimate for this loop (our share now x the programme's reward rate x the loop length)
    acc = sum(x["rate"] * LOOP_SEC for x in chosen if any(f"{x['ticker']}|{o}" in st["orders"] for o in x["need"]))
    day = now.astimezone(ET).date().isoformat()
    st["est_by_day"][day] = st["est_by_day"].get(day, 0.0) + acc; st["est_total"] += acc
    coll = sum(o["count"] * o["cents"] / 100 for o in st["orders"].values())
    log(event="loop", programmes=info["programmes"], candidates=info["candidates"], orders=len(st["orders"]), collateral=coll,
        est_loop=acc, est_rate_day=sum(x["rate"] for x in chosen) * 86400)
    print(f"{now:%H:%MZ} [{MODE}] {info['programmes']} short programmes, {info['candidates']} thin; holding {len(st['orders'])} orders "
          f"(${coll:,.0f} collateral); est. ${sum(x['rate'] for x in chosen) * 86400:,.0f}/day now, today ${st['est_by_day'][day]:,.2f}", flush=True)


def summary(c: Client, st: dict, force: bool = False) -> None:
    now = dt.datetime.now(ET); key = now.date().isoformat()
    if not force and (st["last_summary"] == key or now.hour < 7):
        return
    y = (now.date() - dt.timedelta(days=1)).isoformat()
    lines = [f"**Kalshi LIP bot ({MODE})** — estimated earnings yesterday ${st['est_by_day'].get(y, 0):,.2f}, today so far "
             f"${st['est_by_day'].get(key, 0):,.2f}, since start ${st['est_total']:,.2f} (estimates from the published scoring; paid credits are final)."]
    lines.append(f"Holding {len(st['orders'])} orders, ${sum(o['count'] * o['cents'] / 100 for o in st['orders'].values()):,.0f} collateral.")
    if MODE == "live" and c.authed:
        try:
            b = c.balance(); pos = [p for p in c.positions() if float(p.get("position_fp") or p.get("position") or 0) != 0]
            lines.append(f"Balance ${float(b.get('balance', 0)) / 100:,.2f}; open positions (fills) {len(pos)}.")
        except Exception as e:
            lines.append(f"(balance unavailable: {str(e)[:80]})")
    discord("\n".join(lines)); st["last_summary"] = key; save_state(st)


def shutdown(c: Client, st: dict) -> None:
    for key, o in list(st["orders"].items()):
        if MODE == "live":
            try:
                c.cancel(o["order_id"], o["ticker"])
            except Exception as e:
                log(event="cancel_error", key=key, err=str(e)[:300])
        st["orders"].pop(key)
    save_state(st); log(event="shutdown")


def main() -> int:
    c = Client()
    if MODE == "live" and not c.authed:
        print("MODE=live needs KALSHI_KEY_ID and KALSHI_KEY_PATH", flush=True); return 1
    st = load_state()
    discord(f"**Kalshi LIP bot started ({MODE})** — up to {MAX_MARKETS} markets, ${MAX_COLLATERAL:,.0f} collateral, programmes <= {MAX_DAYS:g} days, "
            f"bids at {PRICE_CENTS}c. Kill switch: STOP file.")
    once = "--once" in sys.argv
    while True:
        if STOP.exists():
            shutdown(c, st); discord("**Kalshi LIP bot stopped** (STOP file): all orders cancelled."); return 0
        try:
            step(c, st); save_state(st); summary(c, st)
        except SystemExit:
            raise
        except Exception as e:
            log(event="error", err=str(e)[:500], tb=traceback.format_exc()[-1500:]); print("error:", e, flush=True)
        if once:
            return 0
        time.sleep(LOOP_SEC)


if __name__ == "__main__":
    sys.exit(main())
