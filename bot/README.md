# Futures demo bot (Discord)

Posts each account's order ticket before its entry and keeps the demo log. Runs beside other bots on a small
DigitalOcean droplet: plain Python + `discord.py`, ~50–70 MB of memory, near-zero CPU, capped at 200 MB by systemd.
`decisions.md` §123.

| when (New York time) | what |
|---|---|
| 02:55 Mon–Fri | gold ticket (8 MGC, 03:00 → 11:30) |
| 09:25 Mon–Fri | Nasdaq ticket (4 MNQ, 09:30 → 16:00) |
| 17:05 Mon–Fri | reminder to send end-of-day balances |
| 17:55 Sun–Thu | crude ticket (10 MCL, 18:00 → 16:55 next day) |

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

In the channel: `!status`, then `!ticket` to see today's orders. After each close: `!eod MNQ 50850` (and MGC, MCL).
When a payout is approved: `!payout MNQ 1250`. When an evaluation fails and you buy another: `!new MGC`.
To fix a mistake: `!set MNQ eval 50850 51200 400 0` (phase, balance, peak, best day, payouts). `!help` lists all.

Everything is written to `demo_log.csv` in the bot folder — send it to me to compare the demo against the backtest:
`scp root@DROPLET_IP:/opt/futures-bot/demo_log.csv .`

## Updating the policy

If the plan changes, regenerate `policy.json` here (`python -m futuresres.reporting.a06_playbook export`), copy it up,
and restart the service. `tests/test_bot_ticket.py` checks the bot's tickets equal the playbook's.
