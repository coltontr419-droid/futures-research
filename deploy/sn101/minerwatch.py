"""SN101 miner watch for Discord (futures-research decisions.md §1176). Posts through the bot's REST API (no gateway connection).

    python minerwatch.py health   # every 5 min: red embed once per incident (service down / no tasks for 20 min / repeated errors)
    python minerwatch.py report   # every 4 h: green embed, miners ranked, $/month estimate, total earned
    python minerwatch.py test     # one test post

Config: /opt/tag101/discord.env (DISCORD_BOT_TOKEN), CHANNEL below; state in /opt/tag101/watch_state.json.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
import urllib.request

sys.path.insert(0, "/opt/tag101")
from chainrpc import rpc, subnet, tx  # noqa: E402

CHANNEL = "1565694815595925534"
NETUID = 101
WALLET = "/root/.bittensor/wallets/main/hotkeys"


def _pub(name: str) -> bytes:
    p = json.load(open(f"{WALLET}/{name}pub.txt"))["publicKey"]
    return bytes.fromhex(p[2:] if p.startswith("0x") else p)


def _uid(hk: bytes):
    """The hotkey's UID on NETUID (Uids double map: netuid Identity, hotkey Blake2_128Concat), or None if not registered."""
    key = tx(b"SubtensorModule") + tx(b"Uids") + NETUID.to_bytes(2, "little") + hashlib.blake2b(hk, digest_size=16).digest() + hk
    v = rpc("state_getStorage", ["0x" + key.hex()])
    return int.from_bytes(bytes.fromhex(v[2:])[:2], "little") if v else None


def miners() -> dict[str, int]:
    """Every m<N> hotkey in the wallet that holds a UID on NETUID, so new miners show up without editing this file."""
    import glob
    import os
    out = {}
    for f in sorted(glob.glob(f"{WALLET}/m*pub.txt"), key=lambda p: int("".join(c for c in os.path.basename(p) if c.isdigit()) or 0)):
        name = os.path.basename(f)[:-len("pub.txt")]
        uid = _uid(_pub(name))
        if uid is not None:
            out[name] = uid
    return out
STATE = "/opt/tag101/watch_state.json"
RED, GREEN = 0xE53935, 0x43A047
UA = "DiscordBot (https://github.com/coltontr419-droid/futures-research, 1.0)"


def token() -> str:
    for line in open("/opt/tag101/discord.env"):
        if line.startswith("DISCORD_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no DISCORD_BOT_TOKEN")


def post(embed: dict) -> None:
    req = urllib.request.Request(f"https://discord.com/api/v10/channels/{CHANNEL}/messages", json.dumps({"embeds": [embed]}).encode(),
                                 {"Authorization": f"Bot {token()}", "Content-Type": "application/json", "User-Agent": UA})
    urllib.request.urlopen(req, timeout=30).read()


def state() -> dict:
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save(s: dict) -> None:
    json.dump(s, open(STATE, "w"))


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def health() -> None:
    import glob
    import os
    s = state(); problems = {}
    try:
        MINERS = miners()
    except Exception:                                   # chain unreachable: still check every local miner service
        MINERS = {os.path.basename(f)[:-len("pub.txt")]: "?" for f in glob.glob(f"{WALLET}/m*pub.txt")}
    for name in MINERS:
        unit = f"tag101-{name}"
        active = sh(f"systemctl is-active {unit}").strip()
        log = sh(f"journalctl -u {unit} --since '-20 min' --no-pager")
        solved = log.count("MINER_SOLVED_TASK"); errors = sum(log.count(k) for k in ("Traceback", "ERROR", "RateLimit", "insufficient_quota"))
        up_long = sh(f"systemctl show {unit} -p ActiveEnterTimestampMonotonic").strip().split("=")[-1]
        boot = float(open("/proc/uptime").read().split()[0]); started = int(up_long or 0) / 1e6
        recent_start = (boot - started) < 25 * 60 if started else False
        why = []
        if active != "active":
            why.append(f"service is **{active}**")
        elif solved == 0 and not recent_start:
            why.append("answered **no tasks** in the last 20 minutes")
        if errors >= 5:
            why.append(f"**{errors} errors** in the last 20 minutes")
        if why:
            problems[name] = why
    alerted = set(s.get("alerted", []))
    new = {k: v for k, v in problems.items() if k not in alerted}
    if new:
        lines = [f"**{k}** (UID {MINERS[k]}): " + "; ".join(v) for k, v in new.items()]
        post({"title": "⚠️ Miner problem — SN101 (Tag101)", "color": RED, "description": "\n".join(lines),
              "footer": {"text": f"droplet 157.230.91.2 · {now()} · auto-restart is on; Claude checks next session"}})
    s["alerted"] = sorted(problems)                     # cleared once healthy, so a later failure alerts again
    save(s)


def hotkey_alpha(pub_hex: str) -> float:
    hk = bytes.fromhex(pub_hex[2:] if pub_hex.startswith("0x") else pub_hex)
    key = tx(b"SubtensorModule") + tx(b"TotalHotkeyAlpha") + hashlib.blake2b(hk, digest_size=16).digest() + hk + NETUID.to_bytes(2, "little")
    v = rpc("state_getStorage", ["0x" + key.hex()])
    return int.from_bytes(bytes.fromhex(v[2:])[:8], "little") / 1e9 if v else 0.0


def report() -> None:
    em, vp, burn, price, tempo = subnet(NETUID)
    try:
        tao = json.load(urllib.request.urlopen("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", timeout=20))["bittensor"]["usd"]
    except Exception:
        tao = float("nan")
    per_month = lambda e: e * (7200 / (tempo + 1)) * price * tao * 30
    miners = sorted(((e, u) for u, e in enumerate(em) if not (u < len(vp) and vp[u])), reverse=True)
    rank = {u: i + 1 for i, (_, u) in enumerate(miners)}; med = per_month(miners[len(miners) // 2][0])
    lines = []; total_m = total_usd = 0.0
    for name, uid in miners().items():                  # M1, M2, ... in hotkey order; new miners appear automatically
        a = hotkey_alpha(json.load(open(f"{WALLET}/{name}pub.txt"))["publicKey"]); m = per_month(em[uid]); usd = a * price * tao
        total_m += m; total_usd += usd
        lines.append(f"**{name.upper()}** ({rank.get(uid, '?')}/{len(miners)}): **${m:,.0f}/month**  Total Earned: **${usd:,.2f}**")
    lines.append(f"**Combined Totals**: **${total_m:,.0f}/month**  Total Earned: **${total_usd:,.2f}**")
    post({"title": "✅ SN101 (Tag101) — 4-hour earnings", "color": GREEN, "description": "\n".join(lines),
          "footer": {"text": f"median slot ${med:,.0f}/month · TAO ${tao:,.2f} · α ${price * tao:.3f} · {now()}"}})


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "health":
        health()
    elif cmd == "test":
        post({"title": "🔧 Miner watch connected", "color": GREEN, "description": "Health alerts (red) and 4-hour earnings (green) will post here.", "footer": {"text": now()}})
    else:
        report()
