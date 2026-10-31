"""Bittensor miner watch for Discord (futures-research decisions.md §1176, §1187). Posts through the bot's REST API (no gateway connection).

    python minerwatch.py health   # every 5 min: red embed once per incident (service down / no tasks for 20 min / repeated errors)
    python minerwatch.py report   # every 4 h: green embed, one line per miner per subnet, $/month and earned, combined totals
    python minerwatch.py test     # one test post

Miners are discovered from the wallet: every hotkey whose name starts with a subnet's prefix (m = Tag101, r = ReadyAI) and holds a UID there.
Config: /opt/tag101/discord.env (DISCORD_BOT_TOKEN), CHANNEL below; state in /opt/tag101/watch_state.json.
"""

from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, "/opt/tag101")
from chainrpc import rpc, subnet, tx  # noqa: E402

CHANNEL = "1565694815595925534"
WALLET = "/root/.bittensor/wallets/main/hotkeys"
SUBNETS = {   # netuid: hotkey prefix, systemd unit pattern, log text of one answered task, display name, minutes without a task before alerting
    101: {"prefix": "m", "unit": "tag101-{name}", "solved": "MINER_SOLVED_TASK", "name": "Tag101", "quiet_min": 20},
    33: {"prefix": "r", "unit": "readyai-{name}", "solved": "Successfully mined", "name": "ReadyAI", "quiet_min": 90},
}
STATE = "/opt/tag101/watch_state.json"
RED, GREEN = 0xE53935, 0x43A047
UA = "DiscordBot (https://github.com/coltontr419-droid/futures-research, 1.0)"


def _pub(name: str) -> bytes:
    p = json.load(open(f"{WALLET}/{name}pub.txt"))["publicKey"]
    return bytes.fromhex(p[2:] if p.startswith("0x") else p)


def _uid(netuid: int, hk: bytes):
    """The hotkey's UID on netuid (Uids double map: netuid Identity, hotkey Blake2_128Concat), or None if not registered."""
    key = tx(b"SubtensorModule") + tx(b"Uids") + netuid.to_bytes(2, "little") + hashlib.blake2b(hk, digest_size=16).digest() + hk
    v = rpc("state_getStorage", ["0x" + key.hex()])
    return int.from_bytes(bytes.fromhex(v[2:])[:2], "little") if v else None


def _local(prefix: str) -> list[str]:
    names = [os.path.basename(f)[:-len("pub.txt")] for f in glob.glob(f"{WALLET}/{prefix}*pub.txt")]
    names = [n for n in names if n[len(prefix):].isdigit()]
    return sorted(names, key=lambda n: int(n[len(prefix):]))


def miners(netuid: int) -> dict[str, int]:
    """Every <prefix><N> hotkey in the wallet that holds a UID on netuid, so new miners show up without editing this file."""
    out = {}
    for name in _local(SUBNETS[netuid]["prefix"]):
        uid = _uid(netuid, _pub(name))
        if uid is not None:
            out[name] = uid
    return out


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
    s = state(); problems = {}; uids = {}
    registered = s.get("registered", {}); lost = []      # "netuid:name" -> UID, remembered so a pruned miner raises an alert (§1196)
    for netuid, cfg in SUBNETS.items():
        try:
            found = miners(netuid)
        except Exception:                               # chain unreachable: still check every local miner service
            found = {n: "?" for n in _local(cfg["prefix"])}
        else:
            for key in [k for k in registered if k.startswith(f"{netuid}:")]:
                name = key.split(":", 1)[1]
                if found.get(name) != registered[key]:
                    lost.append(f"**{cfg['name']} {name.upper()}** (UID {registered[key]}): **deregistered** (pushed out of the subnet)")
                    del registered[key]
            registered.update({f"{netuid}:{n}": u for n, u in found.items()})
        for name, uid in found.items():
            unit = cfg["unit"].format(name=name); key = f"{netuid}:{name}"; uids[key] = (cfg["name"], name, uid)
            active = sh(f"systemctl is-active {unit}").strip()
            q = cfg["quiet_min"]; log = sh(f"journalctl -u {unit} --since '-{q} min' --no-pager")
            solved = log.count(cfg["solved"]); errors = sum(log.count(k) for k in ("Traceback", "ERROR", "RateLimit", "insufficient_quota"))
            up_long = sh(f"systemctl show {unit} -p ActiveEnterTimestampMonotonic").strip().split("=")[-1]
            boot = float(open("/proc/uptime").read().split()[0]); started = int(up_long or 0) / 1e6
            recent_start = (boot - started) < (q + 5) * 60 if started else False
            why = []
            if active != "active":
                why.append(f"service is **{active}**")
            elif solved == 0 and not recent_start:
                why.append(f"answered **no tasks** in the last {q} minutes")
            if errors >= 5:
                why.append(f"**{errors} errors** in the last {q} minutes")
            if why:
                problems[key] = why
    alerted = set(s.get("alerted", []))
    new = {k: v for k, v in problems.items() if k not in alerted}
    if new or lost:
        lines = lost + [f"**{uids[k][0]} {uids[k][1].upper()}** (UID {uids[k][2]}): " + "; ".join(v) for k, v in new.items()]
        post({"title": "⚠️ Miner problem", "color": RED, "description": "\n".join(lines),
              "footer": {"text": f"droplet 157.230.91.2 · {now()} · auto-restart is on; Claude checks next session"}})
    s["alerted"] = sorted(problems)                     # cleared once healthy, so a later failure alerts again
    s["registered"] = registered
    save(s)


def hotkey_alpha(netuid: int, pub_hex: str) -> float:
    hk = bytes.fromhex(pub_hex[2:] if pub_hex.startswith("0x") else pub_hex)
    key = tx(b"SubtensorModule") + tx(b"TotalHotkeyAlpha") + hashlib.blake2b(hk, digest_size=16).digest() + hk + netuid.to_bytes(2, "little")
    v = rpc("state_getStorage", ["0x" + key.hex()])
    return int.from_bytes(bytes.fromhex(v[2:])[:8], "little") / 1e9 if v else 0.0


def report() -> None:
    try:
        tao = json.load(urllib.request.urlopen("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", timeout=20))["bittensor"]["usd"]
    except Exception:
        tao = float("nan")
    lines = []; grand_m = grand_usd = 0.0; foot = []
    for netuid, cfg in SUBNETS.items():
        found = miners(netuid)
        if not found:
            continue
        em, vp, burn, price, tempo = subnet(netuid)
        per_month = lambda e: e * (7200 / (tempo + 1)) * price * tao * 30
        field = sorted(((e, u) for u, e in enumerate(em) if not (u < len(vp) and vp[u])), reverse=True)
        rank = {u: i + 1 for i, (_, u) in enumerate(field)}; med = per_month(field[len(field) // 2][0])
        lines.append(f"__**{cfg['name']}**__")
        sub_m = sub_usd = 0.0
        for name, uid in found.items():                 # M1, M2 / R1, R2 ... in hotkey order; new miners appear automatically
            a = hotkey_alpha(netuid, json.load(open(f"{WALLET}/{name}pub.txt"))["publicKey"]); m = per_month(em[uid]); usd = a * price * tao
            sub_m += m; sub_usd += usd
            lines.append(f"**{name.upper()}** ({rank.get(uid, '?')}/{len(field)}): **${m:,.0f}/month**  Earned: **${usd:,.2f}**")
        grand_m += sub_m; grand_usd += sub_usd
        foot.append(f"{cfg['name']} median ${med:,.0f}/mo")
    lines.append(f"\n**Combined Totals**: **${grand_m:,.0f}/month**  Earned: **${grand_usd:,.2f}**")
    post({"title": "✅ Miner earnings — 4-hour report", "color": GREEN, "description": "\n".join(lines),
          "footer": {"text": " · ".join(foot + [f"TAO ${tao:,.2f}", now()])}})


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "health":
        health()
    elif cmd == "test":
        post({"title": "🔧 Miner watch connected", "color": GREEN, "description": "Health alerts (red) and 4-hour earnings (green) will post here.", "footer": {"text": now()}})
    else:
        report()
