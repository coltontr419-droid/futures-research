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


_load_env(Path(os.environ.get("ENV_FILE", str(HERE / ".env"))))
from kalshi_api import Client  # noqa: E402  (after the environment is loaded)

ET = ZoneInfo("America/New_York")
MODE = os.environ.get("MODE", "dry")
MAX_MARKETS = int(os.environ.get("MAX_MARKETS", "10"))
MAX_COLLATERAL = float(os.environ.get("MAX_COLLATERAL", "150"))
MAX_DAYS = float(os.environ.get("MAX_DAYS", "2"))
MIN_DAYS = float(os.environ.get("MIN_DAYS", "0"))            # A81 (decisions.md 698): long programmes only when set (e.g. 6)
MIN_LEFT_HOURS = float(os.environ.get("MIN_LEFT_HOURS", "0"))
MAX_FILL_COST = float(os.environ.get("MAX_FILL_COST", "20"))  # hard stop: total $ paid for filled contracts since start
MIN_MARKET_DAYS = float(os.environ.get("MIN_MARKET_DAYS", "0"))  # the MARKET must close this far ahead (a long programme can sit on a market settling tomorrow)
PRICE_CENTS = int(os.environ.get("PRICE_CENTS", "1"))
LOOP_SEC = int(os.environ.get("LOOP_SEC", "300"))
MIN_LEFT_MIN = 20                                   # don't enter a programme ending within this many minutes
SHARDS = {int(x) for x in os.environ.get("SHARDS", "0").split(",")}   # trade only markets on shards that hold our funds
# live sports / matches: whoever sells a long shot in-play knows the score (a 300-contract fill on a LigaPro match, decisions.md 695)
EXCLUDE = [x for x in os.environ.get("EXCLUDE", "MATCH,GAME,KXLIGAPRO,KXTT,KXATP,KXWTA,KXMLB,KXNBA,KXNFL,KXNHL,KXNCAA,KXUFC,KXMVE").split(",") if x]
STATE = HERE / os.environ.get("STATE_FILE", "state.json"); LOG = HERE / os.environ.get("LOG_FILE", "lip_log.jsonl")
STOP = HERE / os.environ.get("STOP_FILE", "STOP")
NAME = os.environ.get("BOT_NAME", "Kalshi rewards bot")
ALERT_FILL_USD = float(os.environ.get("ALERT_FILL_USD", "5"))   # only fills costing at least this get their own message (decisions.md 701)
# canary (the user's idea, decisions.md 700): a new side gets 1 contract, then 100, then the full size, one loop apart; a fill at any step ends it
CANARY = [int(x) for x in os.environ.get("CANARY_STEPS", "").split(",") if x]
DISCORD_ENV = Path(os.environ.get("DISCORD_ENV", "/opt/futures-bot/.env"))


def steps(full: int) -> list[int]:
    """Order sizes in sequence: the canary steps (below the full size), then the full size; just the full size without a canary."""
    return [n for n in CANARY if n < full] + [full]


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


BLUE, GREEN, ORANGE, RED = 0x3498DB, 0x2ECC71, 0xE67E22, 0xE74C3C


def _post(payload: dict) -> None:
    env = {}
    if DISCORD_ENV.exists():
        for line in DISCORD_ENV.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1); env[k.strip()] = v.strip()
    if not env.get("DISCORD_TOKEN") or not env.get("DISCORD_CHANNEL_ID"):
        print("[discord skipped]", json.dumps(payload)[:300], flush=True); return
    try:
        req = urllib.request.Request(f"https://discord.com/api/v10/channels/{env['DISCORD_CHANNEL_ID']}/messages", method="POST",
                                     data=json.dumps(payload).encode(),
                                     headers={"Authorization": f"Bot {env['DISCORD_TOKEN']}", "Content-Type": "application/json", "User-Agent": "lip-bot"})
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:
        print("discord error", e, flush=True)


def embed(title: str, color: int, fields: list[tuple[str, str]] | None = None, description: str = "", footer: str = "") -> None:
    """A clean Discord embed: title, colour, optional description, inline fields (name, value), footer."""
    e = {"title": title[:256], "color": color, "timestamp": dt.datetime.now(dt.timezone.utc).isoformat()}
    if description:
        e["description"] = description[:4000]
    if fields:
        e["fields"] = [{"name": n[:256], "value": (v or "—")[:1024], "inline": inline} for n, v, inline in
                       [(f[0], f[1], f[2] if len(f) > 2 else True) for f in fields]][:25]
    e["footer"] = {"text": ((footer + " · " if footer else "") + NAME)[:2048]}
    _post({"embeds": [e]})


def discord(text: str) -> None:
    """Plain-text fallback, kept for anything unexpected."""
    _post({"content": text[:1990]})


def name(c, ticker: str) -> str:
    """A market's plain-English name (cached lookups), e.g. 'Will gas go below $4.30 by Oct 31? — No'."""
    try:
        m = c.market(ticker); t = (m.get("title") or ticker).strip()
        sub = (m.get("yes_sub_title") or "").strip()
        return f"{t} ({sub})" if sub and sub not in t else t
    except Exception:
        return ticker


def usd(x: float) -> str:
    return f"${x:,.2f}"


def bump(st: dict, what: str, n: float = 1) -> None:
    """Per-day counters for the daily results (canaries tried / swept / passed, periods completed, large fills)."""
    d = dt.datetime.now(ET).date().isoformat(); day = st.setdefault("days", {}).setdefault(d, {})
    day[what] = day.get(what, 0) + n


def load_state() -> dict:
    s = json.loads(STATE.read_text()) if STATE.exists() else {"fresh": True}
    s.setdefault("orders", {}); s.setdefault("est_by_day", {}); s.setdefault("est_total", 0.0); s.setdefault("last_summary", "")
    s.setdefault("started", dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")); s.setdefault("verified", False)
    return s


def save_state(s: dict) -> None:
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(s, indent=1)); tmp.replace(STATE)


def log(**kw) -> None:
    with LOG.open("a") as f:
        f.write(json.dumps({"t": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **kw}) + "\n")


# decisions.md 702 (the user: apply all improvements to both bots)
STAY_MIN_USD = float(os.environ.get("STAY_MIN_USD", "1"))          # keep a held order while its projected reward to the period end is >= this
MIN_PROJECTED_USD = float(os.environ.get("MIN_PROJECTED_USD", "3"))  # enter only if the projected reward to the period end is >= this
MAX_PRICE_CENTS = int(os.environ.get("MAX_PRICE_CENTS", "3"))      # a side may be bid at 1..this cents (whichever pays best)
SWEEP_LIMIT = int(os.environ.get("SWEEP_LIMIT", "2"))              # a series whose canaries are swept this often today is skipped today
STEP_SEC = int(os.environ.get("STEP_SEC", "300"))                  # a canary step must rest this long (wall clock) before the next
# orders the user wants kept to the period end whatever the projection (e.g. to watch one) - "TICKER|side,..." (decisions.md 704)
PINNED = {x.strip() for x in os.environ.get("PIN_KEYS", "").split(",") if x.strip()}


def best_option(others: list, target: float, disc: float, can_max: int, rate_side: float, remaining: float, held=None, pinned=False):
    """The side's best (cents, size, share, value): price 1..can_max, size = the shortfall or the full target; value = projected reward
    to the period end - worst-case fill cost (size x price). `held` = our current (cents, size), always an option (no new risk)."""
    tot = sum(s for _, s in others); short = max(0.0, target - tot)
    opts = []
    for cents in range(1, max(1, min(MAX_PRICE_CENTS, can_max)) + 1):
        for size in sorted({int(-(-short // 10) * 10) if short > 0 else 0, int(target)}):
            if size <= 0:
                continue
            sh, q = side_share(others, target, disc, size, cents)
            if q:
                opts.append((sh * rate_side * remaining - size * cents / 100, cents, size, sh))
    if held:
        sh, q = side_share(others, target, disc, held[1], held[0])
        if q:
            # keeping an order keeps its fill risk: judged like a new one (decisions.md 704), except a pinned order, kept as it is
            keep_value = sh * rate_side * remaining - (0.0 if pinned else held[1] * held[0] / 100)
            if pinned:
                return {"cents": held[0], "size": held[1], "share": sh, "value": keep_value}
            opts.append((keep_value, held[0], held[1], sh))
    if not opts:
        return None
    v, cents, size, sh = max(opts)
    return {"cents": cents, "size": size, "share": sh, "value": v}


def plan(c: Client, st: dict, now: dt.datetime) -> tuple[list[dict], dict]:
    P = [p for p in c.programmes() if ts(p["start_date"]) <= now < ts(p["end_date"]) - dt.timedelta(minutes=MIN_LEFT_MIN)
         and MIN_DAYS * 86400 <= (ts(p["end_date"]) - ts(p["start_date"])).total_seconds() <= MAX_DAYS * 86400
         and ts(p["end_date"]) - now >= dt.timedelta(hours=MIN_LEFT_HOURS)]
    books = c.orderbooks(sorted({p["market_ticker"] for p in P}))
    mine = {(o["ticker"], o["outcome"]): (o["cents"], o["count"]) for o in st["orders"].values()}
    skip = set(st.get("skip", [])); filled_keys = set(st.get("filled", {}))
    today = now.astimezone(ET).date().isoformat(); swept = st.get("swept_series", {}).get(today, {})
    cands = []
    for p in P:
        tk = p["market_ticker"]; ob = books.get(tk); series = tk.split("-")[0]
        if ob is None or tk in skip or any(x in tk for x in EXCLUDE) or swept.get(series, 0) >= SWEEP_LIMIT:
            continue
        tgt = float(p.get("target_size_fp") or 0); disc = (p.get("discount_factor_bps") or 5000) / 1e4
        if tgt <= 0:
            continue
        sides = {}
        for outcome in ("yes", "no"):
            lv = levels(ob, outcome)
            if (tk, outcome) in mine:                            # our own size out of the book before judging the side
                mp, ms = mine[(tk, outcome)]
                lv = [(pp, sz - ms if pp == mp else sz) for pp, sz in lv]; lv = [(pp, sz) for pp, sz in lv if sz > 1e-9]
            sides[outcome] = lv
        best = {o: max((pp for pp, _ in sides[o]), default=0) for o in ("yes", "no")}
        can_max = {"yes": 99 - best["no"], "no": 99 - best["yes"]}                 # highest price that still rests (post-only)
        need = {o: sum(sz for _, sz in sides[o]) < tgt for o in ("yes", "no")}
        held = {o: mine.get((tk, o)) for o in ("yes", "no")}
        act = {o: need[o] or held[o] is not None for o in ("yes", "no")}
        if not any(act.values()) or any(f"{tk}|{o}" in filled_keys and need[o] and not held[o] for o in ("yes", "no")):
            continue                                             # nothing to do / a filled side is never re-posted
        if any(need[o] and can_max[o] < 1 for o in ("yes", "no")):
            continue                                             # a side below target that nobody can fill: the snapshot cannot count
        dur = (ts(p["end_date"]) - ts(p["start_date"])).total_seconds(); reward = p["period_reward"] / 1e4
        remaining = (ts(p["end_date"]) - now).total_seconds(); rate_side = reward / dur / 2     # $ a second per unit share of one side
        orders, value, share = {}, 0.0, {}
        ok = True
        for o in ("yes", "no"):
            if act[o]:
                b = best_option(sides[o], tgt, disc, can_max[o], rate_side, remaining, held[o], f"{tk}|{o}" in PINNED)
                if b is None:
                    ok = False; break
                orders[o] = b; value += b["value"]; share[o] = b["share"]
            else:
                sh, q = side_share(sides[o], tgt, disc, 0, 1)
                if not q:
                    ok = False; break
                share[o] = 0.0
        if not ok:
            continue
        rate = sum(rate_side * share[o] for o in ("yes", "no"))
        projected = rate * remaining; is_held = any(held.values())
        value = sum(b["value"] for b in orders.values()); pinned = any(f"{tk}|{o}" in PINNED for o in orders)
        if not pinned and (projected < (STAY_MIN_USD if is_held else MIN_PROJECTED_USD) or value <= 0):
            continue                                             # too little left to clear $1 / the reward left no longer covers the fill risk
        coll = sum(b["size"] * b["cents"] / 100 for b in orders.values())
        cands.append({"ticker": tk, "pid": p["id"], "end": p["end_date"], "need": list(orders), "orders": orders, "rate": rate,
                      "projected": projected, "collateral": coll, "share": sum(share.values()) / 2, "reward": reward, "dur_h": dur / 3600,
                      "held": is_held, "count": max(b["size"] for b in orders.values())})
    cands.sort(key=lambda x: -x["projected"] / max(x["collateral"], 0.01))
    if MODE == "live" or MIN_MARKET_DAYS > 0:                    # shards holding our funds; markets far enough from closing (cached lookups)
        keep = []
        for x in cands:
            if len(keep) >= MAX_MARKETS * 3:
                break
            try:
                m = c.market(x["ticker"]); close = m.get("close_time") or m.get("expiration_time")
                far = (not MIN_MARKET_DAYS) or (close and ts(close) - now >= dt.timedelta(days=MIN_MARKET_DAYS))
                if int(m.get("exchange_index", 0) or 0) in SHARDS and far:
                    keep.append(x)
            except Exception as e:
                log(event="shard_error", ticker=x["ticker"], err=str(e)[:200])
        cands = keep
    chosen, used = [], 0.0
    for x in sorted(cands, key=lambda x: (not x["held"], -x["projected"] / max(x["collateral"], 0.01))):   # keep what we hold first
        if len(chosen) < MAX_MARKETS and used + x["collateral"] <= MAX_COLLATERAL:
            chosen.append(x); used += x["collateral"]
    return chosen, {"programmes": len(P), "candidates": len(cands)}


def verify(c: Client, oid: str, outcome: str, coid: str = "", cents: int | None = None) -> bool:
    """After the first live order: it must be on the intended outcome at PRICE_CENTS of that outcome. Looked up by id, any status - a
    canary can be filled (executed) within seconds, which is a valid order and a detected seller (decisions.md 700)."""
    o = {}
    for attempt in range(6):
        try:
            o = c.req("GET", f"/portfolio/orders/{oid}", auth=True).get("order") or {}
        except Exception:
            o = {}
        if o:
            break
        time.sleep(1.5)
    if not o:
        log(event="verify", ok=False, note="order not found by id"); return False
    side = o.get("outcome_side") or o.get("book_side") or o.get("side")
    if o.get("yes_price_dollars") not in (None, ""):
        yp = float(o["yes_price_dollars"]) * 100
    elif o.get("yes_price") not in (None, ""):
        yp = float(o["yes_price"])
    else:
        yp = float(o.get("price")) * 100
    pc = cents if cents is not None else PRICE_CENTS
    want = pc if outcome == "yes" else 100 - pc
    ok = (side in (("yes", "bid") if outcome == "yes" else ("no", "ask"))) and abs(yp - want) < 0.5
    log(event="verify", ok=ok, status=o.get("status"), order=json.dumps(o)[:600]); return ok


def check_fills(c: Client, st: dict) -> None:
    """Fills since start, rebuilt from Kalshi's records each loop (self-correcting): the side is the fill's outcome_side, the price that
    outcome's price. New fills: logged, alerted, their side dropped and never re-posted. Hard stop past MAX_FILL_COST."""
    if MODE != "live":
        return
    st.setdefault("fill_ids", [])
    since = int(ts(st["started"]).timestamp())
    fills = c.req("GET", f"/portfolio/fills?min_ts={since}&limit=1000", auth=True).get("fills", [])
    mine = {o["order_id"] for o in st["orders"].values()} | set(st.get("order_ids", []))
    filled, cost, new = {}, 0.0, []
    for f in fills:
        if mine and f.get("order_id") not in mine:
            continue                                             # another instance's fill (both bots share the account)
        outcome = f.get("outcome_side") or f.get("side")
        price = float(f.get("yes_price_dollars") if outcome == "yes" else f.get("no_price_dollars") or 0)
        n = float(f.get("count_fp") or 0); key = f"{f.get('ticker')}|{outcome}"
        filled[key] = filled.get(key, 0.0) + n; cost += n * price
        fid = f.get("fill_id") or f.get("trade_id")
        if fid not in st["fill_ids"]:
            st["fill_ids"].append(fid); new.append((key, n, price)); log(event="fill", key=key, count=n, price=price)
    pinned_cost = sum(n * (PRICE_CENTS / 100) for k, n in filled.items() if k in PINNED)
    st["filled"], st["fill_cost"], st["pinned_fill_cost"] = filled, cost - pinned_cost, pinned_cost   # a pinned order (the user's watch) is reported, not counted toward the stop
    for k, n, p in new:
        o = st["orders"].pop(k, None)
        if o:                                                    # cancel what is left of a filled order straight away
            try:
                c.cancel(o["order_id"], o["ticker"])
            except Exception as e:
                log(event="cancel_error", key=k, err=str(e)[:300])
        tk, outcome = k.split("|")
        if o and o.get("step", 0) < len(steps(o.get("full", o["count"]))) - 1:
            bump(st, "canary_swept")                             # a canary (or step) did its job: counted, no message
            d = dt.datetime.now(ET).date().isoformat(); ser = tk.split("-")[0]
            ss = st.setdefault("swept_series", {}).setdefault(d, {}); ss[ser] = ss.get(ser, 0) + 1
        if n * p < ALERT_FILL_USD:
            bump(st, "small_fill_cost", n * p); continue
        bump(st, "large_fills"); bump(st, "large_fill_cost", n * p)
        embed("🟠 Large fill", ORANGE, [
            ("Market", name(c, tk), False),
            ("Side bought", outcome.upper()), ("Contracts", f"{n:,.0f}"), ("Price", f"{p*100:.0f}¢"),
            ("Cost", usd(n * p)), ("Pays if this side wins", usd(n * (1 - p))),
            ("Fill cost so far", f"{usd(st['fill_cost'])} of {usd(MAX_FILL_COST)} limit"),
        ], footer="Filled sides are never re-posted. Most long shots expire worthless, so treat the cost as spent.")
    if st["fill_cost"] > MAX_FILL_COST:
        embed("🔴 Bot stopped — fill limit reached", RED, [("Fill cost", f"{usd(st['fill_cost'])} (limit {usd(MAX_FILL_COST)})"),
              ("Action", "All resting orders cancelled; the bot will not restart on its own.", False)])
        shutdown(c, st); sys.exit(2)


def step(c: Client, st: dict) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    check_fills(c, st)
    chosen, info = plan(c, st, now)
    want = {(x["ticker"], o): x for x in chosen for o in x["need"]}
    live = MODE == "live"
    # cancel orders no longer wanted (side filled up by others, programme ended, or dropped from the chosen set)
    for key, o in list(st["orders"].items()):
        if ts(o["end"]) <= now + dt.timedelta(minutes=MIN_LEFT_MIN) and o.get("count", 0) >= o.get("full", 0) > 0:
            bump(st, "periods_done"); bump(st, "periods_est", o.get("est", 0.0))
            held_h = (now - ts(o["placed"])).total_seconds() / 3600
            embed("🏁 Reward period completed", BLUE, [
                ("Market", name(c, o["ticker"]), False), ("Side", o["outcome"].upper()), ("Size", f"{o['count']:,} at {o['cents']}¢"),
                ("Rested", f"{held_h:,.1f} h, never filled"), ("Est. reward earned", usd(o.get("est", 0.0)))],
                footer="Kalshi pays after the period ends, in a later processing run. Check Rewards → Lifetime.")
        if (o["ticker"], o["outcome"]) not in want or ts(o["end"]) <= now:
            if live:
                try:
                    c.cancel(o["order_id"], o["ticker"])
                except Exception as e:
                    log(event="cancel_error", key=key, err=str(e)[:300])
            log(event="cancel", key=key); st["orders"].pop(key)
    # place, re-price or step up what we want (decisions.md 702)
    today = now.astimezone(ET).date().isoformat(); passed = st.setdefault("passed", {})
    for (tk, outcome), x in want.items():
        key = f"{tk}|{outcome}"; tgt_c = x["orders"][outcome]["cents"]; tgt_n = int(x["orders"][outcome]["size"])
        o = st["orders"].get(key)
        if o:
            seq = steps(tgt_n)
            stepping = CANARY and o.get("step", len(seq) - 1) < len(seq) - 1 and passed.get(key) != today
            if stepping:
                waited = (now - ts(o.get("step_time", o["placed"]))).total_seconds()
                if not live or waited < STEP_SEC:                # a real STEP_SEC unfilled, by the clock (not just the next loop)
                    continue
                nxt, step_no = seq[o["step"] + 1], o["step"] + 1
            elif o["cents"] != tgt_c or (o["count"] >= o.get("full", o["count"]) and abs(o["count"] - tgt_n) > 0.2 * tgt_n):
                nxt, step_no = tgt_n, len(seq) - 1               # a better price or size: re-post at the planned one
            else:
                continue
            if not live:
                o.update(count=nxt, cents=tgt_c, step=step_no, full=tgt_n); continue
            try:
                c.cancel(o["order_id"], o["ticker"])
                r = c.place(tk, outcome, tgt_c, nxt, expires=int(ts(x["end"]).timestamp()))
                o.update(order_id=(r.get("order") or r).get("order_id") or r.get("order_id"), count=nxt, cents=tgt_c, step=step_no, full=tgt_n,
                         step_time=now.isoformat(timespec="seconds"))
                st.setdefault("order_ids", []).append(o["order_id"])
                log(event="step_up" if stepping else "reprice", key=key, count=nxt, cents=tgt_c, step=step_no)
                if stepping and nxt == tgt_n:
                    bump(st, "canary_passed"); passed[key] = today
                    embed("✅ Canary passed — full order resting", GREEN, [
                        ("Market", name(c, tk), False), ("Side", outcome.upper()), ("Size", f"{nxt:,} at {tgt_c}¢"),
                        ("Capital", usd(nxt * tgt_c / 100)), ("Reward pool", f"{usd(x['reward'])} over {x['dur_h']:.0f} h"),
                        ("Est. our share", f"{x['share']:.0%}"), ("Projected to period end", usd(x["projected"])),
                        ("Period ends", f"<t:{int(ts(x['end']).timestamp())}:R>")],
                        footer="No seller appeared at the smaller sizes. Rewards accrue while it rests.")
            except Exception as e:
                log(event="step_error", key=key, err=str(e)[:300])
            continue
        # a new side: canary first, unless this side already passed its canary today (re-entry after stepping aside)
        first = tgt_n if passed.get(key) == today else steps(tgt_n)[0]
        oid = f"dry-{key}"; coid = ""
        if live:
            try:
                r = c.place(tk, outcome, tgt_c, first, expires=int(ts(x["end"]).timestamp()))
            except Exception as e:                               # one rejected market must not stop the loop
                log(event="place_error", key=key, err=str(e)[:300])
                if "market_not_found" in str(e):
                    st.setdefault("skip", []).append(tk)
                continue
            oid = (r.get("order") or r).get("order_id") or r.get("order_id"); coid = r.get("client_order_id", "")
            st.setdefault("order_ids", []).append(oid)
        st["orders"][key] = {"ticker": tk, "outcome": outcome, "cents": tgt_c, "count": first, "order_id": oid, "end": x["end"], "pid": x["pid"],
                             "placed": now.isoformat(timespec="seconds"), "step_time": now.isoformat(timespec="seconds"),
                             "step": len(steps(tgt_n)) - 1 if first == tgt_n else 0, "full": tgt_n, "est": 0.0}
        if CANARY and first < tgt_n:
            bump(st, "canary_tried")
        save_state(st)
        if live and not st["verified"]:
            if not verify(c, oid, outcome, coid, tgt_c):
                embed("🔴 Bot stopped — order check failed", RED, [("What happened", "The first order did not appear on Kalshi as intended.", False),
                      ("Action", "All resting orders cancelled; the bot will not restart on its own. Details in the log.", False)])
                shutdown(c, st); sys.exit(2)
            st["verified"] = True
        log(event="place", key=key, count=first, cents=tgt_c, mode=MODE, reentry=first == tgt_n and bool(CANARY))
    # accrue the estimate for this loop (our share now x the programme's reward rate x the loop length)
    acc = 0.0
    for x in chosen:
        held = [f"{x['ticker']}|{o}" for o in x["need"] if f"{x['ticker']}|{o}" in st["orders"]]
        full = [k for k in held if st["orders"][k].get("count", 0) >= st["orders"][k].get("full", 0)]
        if full and len(full) == len(x["need"]):                 # rewards only once every needed side holds its full size
            a = x["rate"] * LOOP_SEC; acc += a
            for k in full:
                st["orders"][k]["est"] = st["orders"][k].get("est", 0.0) + a / len(full)
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
    coll = sum(o["count"] * o["cents"] / 100 for o in st["orders"].values())
    fields = [("Est. rewards yesterday", usd(st["est_by_day"].get(y, 0))), ("Est. today so far", usd(st["est_by_day"].get(key, 0))),
              ("Est. since start", usd(st["est_total"])),
              ("Orders resting", f"{len(st['orders'])} ({usd(coll)} capital)"),
              ("Fills since start", f"{sum(1 for _ in st.get('fill_ids', []))} ({usd(st.get('fill_cost', 0.0))} cost)")]
    if MODE == "live" and c.authed:
        try:
            fields.append(("Cash balance", usd(float(c.balance().get("balance_dollars") or 0))))
        except Exception:
            fields.append(("Cash balance", "unavailable"))
    dy = st.get("days", {}).get(y, {})
    if CANARY:
        fields.append(("Canaries yesterday", f"{dy.get('canary_tried', 0):.0f} tried · {dy.get('canary_swept', 0):.0f} swept · "
                       f"{dy.get('canary_passed', 0):.0f} passed (cost {usd(dy.get('small_fill_cost', 0))})", False))
    if dy.get("periods_done") or dy.get("large_fills"):
        fields.append(("Yesterday", f"{dy.get('periods_done', 0):.0f} reward periods completed (est. {usd(dy.get('periods_est', 0))}) · "
                       f"{dy.get('large_fills', 0):.0f} large fills ({usd(dy.get('large_fill_cost', 0))})", False))
    if st["orders"]:
        fields.append(("Markets", "\n".join(f"• {name(c, o['ticker'])} — **{o['outcome'].upper()}** "
                                              f"{o['count']:,} at {o['cents']}¢" + (" (canary)" if o.get("count", 0) < o.get("full", 0) else "")
                                              for o in st["orders"].values())[:1024], False))
    embed(f"🟢 {NAME} — daily results, {now:%a %b %d}" + ("" if MODE == "live" else " (dry run)"), GREEN, fields,
          footer="Estimates use Kalshi's published scoring. Only paid credits (Kalshi → Rewards) are final.")
    st["last_summary"] = key; save_state(st)


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
    if st.pop("fresh", False):
      embed("🔵 " + NAME + " started" + ("" if MODE == "live" else " (dry run — no orders)"), BLUE, [
        ("Markets", f"up to {MAX_MARKETS}"), ("Capital limit", usd(MAX_COLLATERAL)), ("Bid price", f"{PRICE_CENTS}¢"),
        ("Programmes", f"{MIN_DAYS:g}–{MAX_DAYS:g} days long" + (f", market closing ≥ {MIN_MARKET_DAYS:g} days out" if MIN_MARKET_DAYS else ""), False),
        ("Safety", f"stops itself after {usd(MAX_FILL_COST)} of fills; filled sides never re-posted", False)],
        footer="It earns Kalshi liquidity rewards by resting bids; fills are the risk.")
    once = "--once" in sys.argv
    while True:
        if STOP.exists():
            shutdown(c, st); embed("🔴 Bot stopped (kill switch)", RED, [("Action", "All resting orders cancelled.", False)])
            return 2                                             # the deliberate-stop code: systemd does not restart it (decisions.md 707)
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
