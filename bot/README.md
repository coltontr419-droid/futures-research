# Futures demo bot (Discord)

One alert a day at **17:30 New York time** with the next tickets and how the finished ones played out; the account
bookkeeping; the demo and shadow logs. Runs beside other bots on a small DigitalOcean droplet: plain Python +
`discord.py`, ~50–70 MB of memory, near-zero CPU, capped at 200 MB by systemd. `decisions.md` §123, §125.

**The 17:30 alert (Sun–Thu)**, after the 17:00 close:

| ticket | window (New York time) | you place it |
|---|---|---|
| crude, 10 MCL | 18:00 tonight → 16:55 tomorrow | at 18:00, after the alert |
| gold, 8 MGC | 03:00 → 11:30 tomorrow | at 03:00 (or skip) |
| Nasdaq, 4 MNQ | 09:30 → 16:00 tomorrow | at 09:30 (or skip) |

On Fridays the alert carries results only. **Send the day's closing balances (`!eod`) between 17:00 and 17:30** so the
tickets use them; a balance sent after the alert reissues that ticket.

**Every ticket is tracked whether or not you trade it**: after its window closes the bot pulls free 1-minute prices
(Yahoo: NQ=F, GC=F, CL=F — the same prices as the micros), applies the backtests' rules (entry at the open of the entry
minute, take / stop at their prices, a minute touching both counts as the stop, else out at the exit time, commissions
charged) and logs the outcome to `shadow_log.csv`; results appear in the next alert and on `!results`. Checked against the
programme's Databento data for 6–9 October 2026: all 8 outcomes identical. Mark what you did with `!took` / `!skipped`.

## 1. Create the Discord bot (one time, ~5 minutes)

1. Go to <https://discord.com/developers/applications> → **New Application** → name it (e.g. "Futures Demo").
2. **Bot** tab → **Reset Token** → copy the token (this is `DISCORD_TOKEN`; keep it secret).
3. Same tab → turn on **Message Content Intent** → Save.
4. **OAuth2 → URL Generator**: scope **bot**; permissions **Send Messages**, **Read Message History**, **View Channels**.
   Open the generated URL and add the bot to your server.
5. In Discord: **User Settings → Advanced → Developer Mode** on. Right-click the channel the bot should use →
   **Copy Channel ID** (`DISCORD_CHANNEL_ID`). Right-click your own name → **Copy User ID** (`DISCORD_USER_ID`, so only you
   can send commands).

## 2. Put it on the droplet

From the laptop (this repo), copy the bot folder up — replace `DROPLET_IP`:

```bash
scp -r ~/futures-research/bot root@DROPLET_IP:/opt/futures-bot
```

Then on the droplet (`ssh root@DROPLET_IP`):

```bash
cd /opt/futures-bot
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env          # paste the token, channel id, user id
venv/bin/python futures_bot.py             # test run: should print "logged in as ..."; Ctrl+C to stop
cp futures-bot.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now futures-bot
systemctl status futures-bot               # should say active (running)
```

Logs: `journalctl -u futures-bot -f`. Restart after an update: `systemctl restart futures-bot`.
Check the droplet clock is right: `timedatectl` (the bot converts to New York time itself).

## 3. Use it

Type the commands as messages in the bot's channel, starting with `!` or by mentioning the bot (`@Futures Demo eod MNQ 50850`).
**The closing balance is the account balance after the 17:00 ET close**, with every position flat — every ticket is
already out by then (gold 11:30, Nasdaq 16:00, crude 16:55); it is the figure Tradeify's end-of-day floor uses.
In the channel: `!status`; after each close (17:00–17:30): `!eod MNQ 50850`, `!eod MGC ...`, `!eod MCL ...`.
`!ticket` repeats the open tickets; `!results` lists every finished ticket and its outcome.
When a payout is approved: `!payout MNQ 1250`. When an evaluation fails and you buy another: `!new MGC`.
To fix a mistake: `!set MNQ eval 50850 51200 400 0` (phase, balance, peak, best day, payouts). `!help` lists all.

Account events go to `demo_log.csv` and ticket outcomes to `shadow_log.csv` in the bot folder — send them to me to compare
the demo against the backtest: `scp root@DROPLET_IP:/opt/futures-bot/*_log.csv .`

## Updating the policy

If the plan changes, regenerate `policy.json` here (`python -m futuresres.reporting.a06_playbook export`), copy it up,
and restart the service. `tests/test_bot_ticket.py` checks the bot's tickets equal the playbook's.
