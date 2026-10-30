"""Hourly earnings log for our UIDs vs each subnet median (futures-research decisions.md 1174, 1188). Appends one row per miner to /opt/tag101/earnings_all.csv
(the Tag101-only earnings.csv holds the history up to 2026-10-30 17:00 UTC)."""
import csv, datetime as dt, json, os, sys, urllib.request
sys.path.insert(0, "/opt/tag101")
from chainrpc import subnet
from minerwatch import SUBNETS, miners
try:
    tao = json.load(urllib.request.urlopen("https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd", timeout=20))["bittensor"]["usd"]
except Exception:
    tao = float("nan")
when = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")
for netuid, cfg in SUBNETS.items():
    found = miners(netuid)
    if not found:
        continue
    em, vp, burn, price, tempo = subnet(netuid)
    per_month = lambda e: e * (7200 / (tempo + 1)) * price * tao * 30
    field = sorted(e for e, v in zip(em, vp + [0] * len(em)) if not v)
    med = field[len(field) // 2] if field else 0
    for name, uid in found.items():
        row = {"utc": when, "subnet": cfg["name"], "miner": name, "uid": uid, "alpha_per_tempo": round(em[uid], 4), "usd_month": round(per_month(em[uid]), 1),
               "median_usd_month": round(per_month(med), 1), "tao_usd": tao, "alpha_tao": round(price, 6)}
        f = "/opt/tag101/earnings_all.csv"; new = not os.path.exists(f)
        with open(f, "a", newline="") as h:
            w = csv.DictWriter(h, fieldnames=list(row)); new and w.writeheader(); w.writerow(row)
print("logged")
