"""Discord bot for the demo forward test: one alert a day at 17:30 New York time with the next tickets and how the
finished ones played out; account bookkeeping; the demo and shadow logs. decisions.md 123, 125.

    python futures_bot.py            (on the droplet, as a systemd service; see bot/README.md)

The 17:30 alert (Sun-Thu): results of finished tickets, then crude (MCL) 18:00 tonight -> 16:55 tomorrow, gold (MGC)
03:00 -> 11:30 tomorrow, Nasdaq (MNQ) 09:30 -> 16:00 tomorrow. Friday: results only. Every ticket is shadow-tracked on
free 1-minute prices after its window closes, traded or not.

Commands (in the configured channel; start with ! or mention the bot, e.g. "@Bot eod MNQ 50850"):
  !eod <PRODUCT> <balance>       the account balance after the 17:00 ET close, all positions flat (send 17:00-17:30;
                                 a ticket already issued is reissued)
  !took <PRODUCT> / !skipped <PRODUCT>   mark whether you placed the latest ticket
  !results [n]                   finished tickets and how they played out (all, or the last n)
  !ticket                        the tickets issued at the last alert
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
from schedule import ALERT, ET, Tickets, alert_text, last_trading_day, ticket_post

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
    key = now.date().isoformat()
    done = LAST_ALERT.read_text().strip() if LAST_ALERT.exists() else ""
    if now.weekday() != 5 and (now.hour, now.minute) >= ALERT and key != done and (now.hour, now.minute) < (ALERT[0] + 2, 0):
        LAST_ALERT.write_text(key)
        await send(ch, f"**{now:%A %d %B} - 17:30 ET**\n\n" + alert_text(book, tix, now))


@bot.command(name="eod")
async def eod_cmd(ctx, product: str, balance: float):
    if not _allowed(ctx):
        return
    p = _product(product)
    now = dt.datetime.now(ET)
    day = last_trading_day(now.date() if now.hour >= 17 else now.date() - dt.timedelta(days=1)).isoformat()
    msgs = book.eod(p, balance, day)
    a = book.s[p]
    out = [f"{p}: closed ${balance:,.2f} ({day}) recorded. Peak ${a['peak']:,.2f}, best day ${a['best']:,.0f}." if a["phase"] != "dead" else ""]
    out += msgs
    # reissue this product's ticket if the alert already went out and its entry is still ahead
    pend = [r for r in tix.t if r["product"] == p and r["status"] in ("pending", "none") and dt.datetime.fromisoformat(r["entry"]) > now]
    if pend:
        alert_day = dt.datetime.fromisoformat(pend[-1]["issued"]).date()
        out.append("Updated ticket:\n" + ticket_post(tix.issue(book, p, alert_day, now)))
    await send(ctx.channel, "\n".join(m for m in out if m))


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
