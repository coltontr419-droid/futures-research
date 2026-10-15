"""Discord bot for the demo forward test: one alert a day at 17:30 New York time with the next tickets and how the
finished ones played out; account bookkeeping; the demo and shadow logs. decisions.md 123, 125.

    python futures_bot.py            (on the droplet, as a systemd service; see bot/README.md)

The 17:30 alert (Sun-Thu): results of finished tickets, then crude (MCL) 18:00 tonight -> 16:55 tomorrow, gold (MGC)
03:00 -> 11:30 tomorrow, Nasdaq (MNQ) 09:30 -> 16:00 tomorrow. Friday: results only. Every ticket is shadow-tracked on
free 1-minute prices after its window closes, traded or not.

Commands (in the configured channel; start with ! or mention the bot, e.g. "@Bot eod MNQ 50850"):
  !eod <PRODUCT> <balance>       the account balance once that product's ticket has closed (any time - filed under the
                                 ticket's trading day); a ticket already issued is reissued. Checked first against a 1-minute
                                 replay from the exact entry: if it hit the other bracket, nothing is booked until you resend
                                 with `confirm` at the end (!eod MNQ 49000 confirm) or send the matching balance
  !took <PRODUCT> / !skipped <PRODUCT>   mark whether you placed the latest ticket
  !results [n]                   finished tickets and how they played out (all, or the last n)
  !ticket                        the tickets issued at the last alert
  !board                         re-post the latest alert's board (red until every traded ticket has its !eod)
  !payout <PRODUCT> <amount>     a payout received (the amount withdrawn, before the 90% split)
  !new <PRODUCT>                 a new $50k evaluation bought
  !set <PRODUCT> <eval|funded> <balance> <peak> [best_day] [payouts]   correct the state by hand
  !status                        all accounts
  !help                          this list

Settings (environment or bot/.env): DISCORD_TOKEN, DISCORD_CHANNEL_ID, optional DISCORD_USER_ID (only that user's
commands are accepted), optional BOT_DATA_DIR (state.json, tickets.json, demo_log.csv, shadow_log.csv; default: here).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
from pathlib import Path

import discord
from discord.ext import commands, tasks

from accounts import PRODUCTS, Book
import daxdollar
import json

from schedule import ALERT, CT, ET, ORDER, Tickets, alert_parts, clock, eod_check, eod_day, last_trading_day, needs_eod, ticket_post

HERE = Path(__file__).resolve().parent


def _load_env(path: Path) -> None:
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env(HERE / ".env")
TOKEN = os.environ.get("DISCORD_TOKEN", "")
CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", "0") or 0)
USER_ID = int(os.environ.get("DISCORD_USER_ID", "0") or 0)
DATA = Path(os.environ.get("BOT_DATA_DIR", str(HERE)))
book = Book(DATA / "state.json", DATA / "demo_log.csv")
tix = Tickets(DATA / "tickets.json", DATA / "shadow_log.csv")

intents = discord.Intents.default()
intents.message_content = True
# commands work as "!eod MNQ 50850" or by mentioning the bot: "@Bot eod MNQ 50850" (or "@Bot !eod ...")
bot = commands.Bot(command_prefix=lambda b, m: commands.when_mentioned_or("!")(b, m) + [f"<@{b.user.id}> !", f"<@!{b.user.id}> !"],
                   intents=intents, help_command=None)
LAST_ALERT = DATA / "last_alert.txt"          # survives restarts, so an alert is never posted twice
BOARDS = DATA / "boards.json"                 # alert date -> {message_id, info, keys}: the posted boards, edited on !eod
FOOTER = "Red = at least one traded ticket still needs !eod.  Green = every ticket recorded."


def _boards() -> dict:
    return json.loads(BOARDS.read_text()) if BOARDS.exists() else {}


def _save_boards(b: dict) -> None:
    keep = dict(sorted(b.items())[-14:])
    tmp = BOARDS.with_suffix(".tmp"); tmp.write_text(json.dumps(keep, indent=1)); tmp.replace(BOARDS)


def _field_name(r: dict) -> str:
    e = dt.datetime.fromisoformat(r["entry"]).astimezone(ET); x = dt.datetime.fromisoformat(r["exit"]).astimezone(ET)
    tk = r["ticket"]
    side = ("LONG" if tk.get("side") == "long" else "SHORT") if tk.get("trade") else ("FAILED" if r["phase"] == "dead" else "NO TRADE")
    mark = ("⏳" if needs_eod(r) else "✅") if tk.get("trade") and r["phase"] != "dead" else "▫️"
    return f"{mark} {r['product']} · {side} · {clock(e)} → {clock(x)} CT"


def _field_value(r: dict) -> str:
    body = ticket_post(r).split("\n", 1)[-1]            # drop the plain-text header; the field name carries it
    from schedule import recorded_outcome
    if r.get("user_pnl") is not None:
        out = recorded_outcome(r["user_pnl"], r["ticket"].get("take_net", 0), r["ticket"].get("stop_net", 0))
        tail = f"\n**!eod recorded: {out} ${r['user_pnl']:+,.0f}**"
    else:
        tail = None
    tail = tail or ("\n**!eod recorded**" if r.get("eod") else ("\n*waiting for `!eod " + r["product"] + " <balance>`*" if needs_eod(r) else ""))
    v = f"[{r['phase']}, balance ${r['balance']:,.2f}]\n" + body + tail
    return v if len(v) <= 1024 else v[:1020] + "…"


def board_embeds(info: str, recs: list, when: str) -> list:
    embeds = []
    if info:
        embeds.append(discord.Embed(title=f"{when} — results & notes", description=info[:4000], color=discord.Color.blurple()))
    if recs:
        recs = sorted(recs, key=lambda r: ORDER.index(r["product"]) if r["product"] in ORDER else 99)
        open_ = sum(needs_eod(r) for r in recs)
        e = discord.Embed(title=f"{when} — tickets", color=discord.Color.red() if open_ else discord.Color.green(),
                          description=(f"**{open_} ticket{'s' if open_ != 1 else ''} still need `!eod`.**" if open_ else "**All tickets recorded.**"))
        for r in recs:
            e.add_field(name=_field_name(r), value=_field_value(r), inline=False)
        e.set_footer(text=FOOTER)
        embeds.append(e)
    return embeds


async def post_board(ch, info: str, recs: list, key: str, when: str) -> None:
    msg = await ch.send(embeds=board_embeds(info, recs, when))
    if recs:
        b = _boards(); b[key] = {"message_id": msg.id, "info": info, "when": when, "keys": [[r["product"], r["entry"]] for r in recs]}
        _save_boards(b)


async def refresh_boards(ch, products: set | None = None) -> None:
    """Re-render every stored board that holds a ticket of `products` (all boards if None)."""
    for key, b in _boards().items():
        recs = tix.batch(b["keys"])
        if products and not any(r["product"] in products for r in recs):
            continue
        try:
            msg = await ch.fetch_message(b["message_id"])
            await msg.edit(embeds=board_embeds(b["info"], recs, b["when"]))
        except discord.HTTPException as e:
            print("board edit failed:", key, e)


async def send(ch, text: str) -> None:
    """Discord caps a message at 2,000 characters: split on blank lines."""
    chunk = ""
    for part in text.split("\n\n"):
        if len(chunk) + len(part) + 2 > 1900:
            await ch.send(chunk); chunk = ""
        chunk = (chunk + "\n\n" + part) if chunk else part
    if chunk:
        await ch.send(chunk)


def _allowed(ctx) -> bool:
    return ctx.channel.id == CHANNEL_ID and (not USER_ID or ctx.author.id == USER_ID)


def _product(p: str) -> str:
    p = p.upper()
    if p not in PRODUCTS:
        raise commands.BadArgument(f"product must be one of {', '.join(PRODUCTS)}")
    return p


@bot.event
async def on_ready():
    print(f"logged in as {bot.user}; channel {CHANNEL_ID}")
    # first start with boards: post one for the latest alert's tickets if none exists yet
    try:
        ch = bot.get_channel(CHANNEL_ID)
        last = LAST_ALERT.read_text().strip() if LAST_ALERT.exists() else ""
        if ch and last and last not in _boards():
            recs = [r for r in tix.t if dt.datetime.fromisoformat(r["issued"]).astimezone(ET).date().isoformat() == last]
            if recs:
                await post_board(ch, "", recs, last, f"{dt.date.fromisoformat(last):%A %d %B} · 4:30 PM CT")
    except Exception as e:
        print("board on start failed:", e)
    if not loop.is_running():
        loop.start()


@tasks.loop(seconds=30)
async def loop():
    now = dt.datetime.now(ET)
    # shadow-track finished windows (network call off the event loop)
    try:
        await asyncio.to_thread(tix.track, now)
    except Exception as e:                                   # never let tracking stop the alert
        print("tracking error:", e)
    ch = bot.get_channel(CHANNEL_ID)
    if ch is None:
        return
    if now.weekday() < 5 and (2, 45) <= (now.hour, now.minute) < (2, 58):
        await fdxm_recheck(ch, now)
    key = now.date().isoformat()
    done = LAST_ALERT.read_text().strip() if LAST_ALERT.exists() else ""
    if now.weekday() != 5 and (now.hour, now.minute) >= ALERT and key != done and (now.hour, now.minute) < (ALERT[0] + 2, 0):
        LAST_ALERT.write_text(key)
        info, recs = alert_parts(book, tix, now)
        await post_board(ch, info, recs, key, f"{now:%A %d %B} · 4:30 PM CT")


async def fdxm_recheck(ch, now: dt.datetime) -> None:
    """02:45-02:58 ET: re-read the dollar for the FDXM ticket entering at 03:00 (decisions.md 490); flip and reissue if it changed."""
    recs = [r for r in tix.t if r["product"] == "FDXM" and r["status"] == "pending" and not r.get("prechecked")
            and dt.datetime.fromisoformat(r["entry"]).astimezone(ET).date() == now.date() and r["ticket"].get("trade")]
    if not recs:
        return
    rec = recs[-1]
    res = await asyncio.to_thread(daxdollar.preopen_side, now)
    old = rec["ticket"]["side"]
    if res is None:                                   # every re-check posts its own message (decisions.md 581)
        rec["prechecked"] = True; tix.save()
        await ch.send(f"FDXM re-check ({clock(now, False)} CT): no EUR/USD data - the 4:30 PM side ({old.upper()}) stands; staged order unchanged.")
        return
    side, why = res
    if side != old:
        alert_day = dt.datetime.fromisoformat(rec["issued"]).date()
        new = tix.issue(book, "FDXM", alert_day, now, side_override=(side, why))
        new["prechecked"] = True; tix.save()
        em = discord.Embed(title=f"FDXM re-check: side changed {old.upper()} → {side.upper()}",
                           description="**Change your staged FDXM order before the 2:00 AM CT entry.**\n\n" + ticket_post(new)[:3800],
                           color=0xE67E22)
        await ch.send(content=f"<@{USER_ID}>" if USER_ID else None, embed=em)
    else:
        rec["prechecked"] = True; rec["ticket"]["note"] = (rec["ticket"].get("note", "") + f" | {why} (unchanged)").strip(" |"); tix.save()
        await ch.send(f"FDXM re-check ({clock(now, False)} CT): side unchanged - {old.upper()}; staged order stands. ({why})")
    await refresh_boards(ch, {"FDXM"})


@bot.command(name="eod")
async def eod_cmd(ctx, product: str, balance: float, confirm: str = ""):
    if not _allowed(ctx):
        return
    p = _product(product)
    now = dt.datetime.now(ET)
    day = eod_day(tix, p, now)                      # the trading day of the ticket that just ended
    pnl = round(balance - book.s[p]["balance"], 2)  # the day's actual P&L, before eod() may reset the account
    if confirm.lower() not in ("confirm", "yes", "force"):    # cross-check against the exact-entry replay first (decisions.md 577)
        warn = await asyncio.to_thread(eod_check, tix, p, pnl, now)
        if warn:
            await send(ctx.channel, warn)
            return
    msgs = book.eod(p, balance, day)
    a = book.s[p]
    out = [f"{p}: closed ${balance:,.2f} ({day}) recorded. Peak ${a['peak']:,.2f}, best day ${a['best']:,.0f}." if a["phase"] != "dead" else ""]
    out += msgs
    # reissue this product's ticket if the alert already went out and its entry is still ahead
    marked = tix.mark_eod(p, now)                   # the board turns this ticket green
    if marked:                                      # the actual result belongs to the latest ticket that started (decisions.md 492)
        max(marked, key=lambda r: r["entry"])["user_pnl"] = pnl; tix.save()
    pend = [r for r in tix.t if r["product"] == p and r["status"] in ("pending", "none") and dt.datetime.fromisoformat(r["entry"]) > now]
    if pend:
        alert_day = dt.datetime.fromisoformat(pend[-1]["issued"]).date()
        tix.issue(book, p, alert_day, now)
        out.append(f"{p}'s next ticket was reissued from the new balance - updated on the board above.")
    await send(ctx.channel, "\n".join(m for m in out if m))
    await refresh_boards(ctx.channel, {p})


@bot.command(name="took")
async def took_cmd(ctx, product: str):
    if _allowed(ctx):
        r = tix.mark(_product(product), True)
        await ctx.send("Marked as traded." if r else "No open ticket to mark.")


@bot.command(name="skipped")
async def skipped_cmd(ctx, product: str):
    if _allowed(ctx):
        r = tix.mark(_product(product), False)
        await ctx.send("Marked as skipped - it is still tracked." if r else "No open ticket to mark.")


@bot.command(name="results")
async def results_cmd(ctx, n: int = 0):
    if _allowed(ctx):
        await send(ctx.channel, tix.summary(n))


@bot.command(name="ticket")
async def ticket_cmd(ctx):
    if not _allowed(ctx):
        return
    now = dt.datetime.now(ET)
    live = [r for r in tix.t if r["status"] in ("pending", "none") and dt.datetime.fromisoformat(r["exit"]) > now]
    await send(ctx.channel, "\n\n".join(ticket_post(r) for r in live) or "No open tickets - the next ones come with the 17:30 alert.")


@bot.command(name="board")
async def board_cmd(ctx):
    """Re-post the latest alert's board (the old one stays as it was)."""
    if not _allowed(ctx):
        return
    b = _boards()
    if not b:
        await ctx.send("No board yet - the next comes with the 17:30 alert.")
        return
    key = sorted(b)[-1]; recs = tix.batch(b[key]["keys"])
    await post_board(ctx.channel, b[key]["info"], recs, key, b[key]["when"])


@bot.command(name="payout")
async def payout_cmd(ctx, product: str, amount: float):
    if _allowed(ctx):
        await ctx.send(book.payout(_product(product), amount))


@bot.command(name="new")
async def new_cmd(ctx, product: str):
    if _allowed(ctx):
        await ctx.send(book.new(_product(product)))


@bot.command(name="set")
async def set_cmd(ctx, product: str, phase: str, balance: float, peak: float, best: float = 0.0, payouts: int = 0):
    if _allowed(ctx):
        if phase not in ("eval", "funded"):
            raise commands.BadArgument("phase must be eval or funded")
        await ctx.send(book.set(_product(product), phase, balance, peak, best, payouts))


@bot.command(name="status")
async def status_cmd(ctx):
    if _allowed(ctx):
        await ctx.send(book.status())


@bot.command(name="help")
async def help_cmd(ctx):
    if _allowed(ctx):
        await ctx.send("```" + __doc__.split("e.g. \"@Bot eod MNQ 50850\"):")[1].split("Settings")[0] + "```")


@bot.event
async def on_command_error(ctx, error):
    if _allowed(ctx):
        await ctx.send(f"Couldn't do that: {error}. `!help` lists the commands.")


if __name__ == "__main__":
    if not TOKEN or not CHANNEL_ID:
        raise SystemExit("set DISCORD_TOKEN and DISCORD_CHANNEL_ID (bot/.env)")
    bot.run(TOKEN)
