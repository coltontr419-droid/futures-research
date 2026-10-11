"""Discord bot for the demo forward test: posts each account's order ticket before its entry and keeps the demo log.
decisions.md 123.

    python futures_bot.py            (on the droplet, as a systemd service; see bot/README.md)

Schedule (New York time, daylight saving handled): MGC ticket 02:55 Mon-Fri, MNQ 09:25 Mon-Fri, MCL 17:55 Sun-Thu
(crude's session opens at 18:00 for the next day), and an end-of-day reminder at 17:05 Mon-Fri.

Commands (in the configured channel):
  !ticket [MNQ|MGC|MCL]          the order for now (all three if omitted)
  !eod <PRODUCT> <balance>       end-of-day balance -> peak, best day, pass / fail / payout checks
  !payout <PRODUCT> <amount>     a payout received (the amount withdrawn, before the 90% split)
  !new <PRODUCT>                 a new $50k evaluation bought
  !set <PRODUCT> <eval|funded> <balance> <peak> [best_day] [payouts]   correct the state by hand
  !status                        all accounts
  !help                          this list

Settings (environment or bot/.env): DISCORD_TOKEN, DISCORD_CHANNEL_ID, optional DISCORD_USER_ID (only that user's
commands are accepted), optional BOT_DATA_DIR (state.json and demo_log.csv; default: this folder).
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from accounts import PRODUCTS, Book
from ticket import describe, ticket

HERE = Path(__file__).resolve().parent
ET = ZoneInfo("America/New_York")
#: (product, hh, mm, weekdays) - weekday(): Mon=0 .. Sun=6
SCHEDULE = [("MGC", 2, 55, {0, 1, 2, 3, 4}), ("MNQ", 9, 25, {0, 1, 2, 3, 4}), ("MCL", 17, 55, {6, 0, 1, 2, 3})]
EOD_REMINDER = (17, 5, {0, 1, 2, 3, 4})


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

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
_posted: set[tuple[str, str]] = set()


def ticket_text(product: str) -> str:
    a = book.s[product]
    if a["phase"] == "dead":
        return f"**{product}: account failed** - buy a new evaluation and send `!new {product}`."
    t = ticket(a["phase"], a["balance"], a["peak"], a["best"], a["payouts"], product)
    return f"[{a['phase']} - balance ${a['balance']:,.2f}]\n" + describe(t, product)


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
    if not scheduler.is_running():
        scheduler.start()


@tasks.loop(seconds=20)
async def scheduler():
    now = dt.datetime.now(ET)
    ch = bot.get_channel(CHANNEL_ID)
    if ch is None:
        return
    today = now.date().isoformat()
    for product, hh, mm, days in SCHEDULE:
        key = (product, today)
        if now.weekday() in days and (now.hour, now.minute) == (hh, mm) and key not in _posted:
            _posted.add(key)
            await ch.send(ticket_text(product))
    hh, mm, days = EOD_REMINDER
    key = ("EOD", today)
    if now.weekday() in days and (now.hour, now.minute) == (hh, mm) and key not in _posted:
        _posted.add(key)
        await ch.send("End of day: send each account's closing balance - `!eod MNQ <balance>`, `!eod MGC <balance>`, "
                      "`!eod MCL <balance>` (also any payouts: `!payout`).")


@bot.command(name="ticket")
async def ticket_cmd(ctx, product: str = ""):
    if not _allowed(ctx):
        return
    ps = [_product(product)] if product else list(PRODUCTS)
    await ctx.send("\n\n".join(ticket_text(p) for p in ps))


@bot.command(name="eod")
async def eod_cmd(ctx, product: str, balance: float):
    if not _allowed(ctx):
        return
    p = _product(product)
    msgs = book.eod(p, balance)
    a = book.s[p]
    head = f"{p}: closed ${balance:,.2f} recorded. Peak ${a['peak']:,.2f}, best day ${a['best']:,.0f}." if a["phase"] != "dead" else ""
    await ctx.send("\n".join([m for m in [head, *msgs] if m]))


@bot.command(name="payout")
async def payout_cmd(ctx, product: str, amount: float):
    if _allowed(ctx):
        await ctx.send(book.payout(_product(product), amount))


@bot.command(name="new")
async def new_cmd(ctx, product: str):
    if _allowed(ctx):
        p = _product(product)
        await ctx.send(book.new(p) + "\n\n" + ticket_text(p))


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
        await ctx.send("```" + __doc__.split("Commands (in the configured channel):")[1].split("Settings")[0] + "```")


@bot.event
async def on_command_error(ctx, error):
    if _allowed(ctx):
        await ctx.send(f"Couldn't do that: {error}. `!help` lists the commands.")


if __name__ == "__main__":
    if not TOKEN or not CHANNEL_ID:
        raise SystemExit("set DISCORD_TOKEN and DISCORD_CHANNEL_ID (bot/.env)")
    bot.run(TOKEN)
