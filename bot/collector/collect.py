"""Free 1-minute data collector (decisions.md 659). Once a day: Yahoo Finance 1-minute bars (~7 days of history are served) for a
fixed list of symbols, one gzip CSV per symbol per complete UTC day. Builds a long record for future research at no cost.
Plain Python (no packages), separate from the trading bot. A hard size cap: past it nothing more is written and the report says so;
nothing is ever deleted. Sundays (or --report): a short Discord report - rows per symbol, missing weekdays, failures, disk used.

    python collect.py [--report] [--dry]          (systemd timer futures-collector.timer, daily 22:30 UTC)

Settings: DATA_DIR (default /opt/futures-data), CAP_GB (default 2); the report posts with the bot's DISCORD_TOKEN / DISCORD_CHANNEL_ID
from /opt/futures-bot/.env (read, never printed).
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

SYMBOLS = ["NKD=F", "^N225", "^GDAXI", "NQ=F", "ES=F", "YM=F", "RTY=F", "GC=F", "SI=F", "HG=F", "CL=F", "NG=F", "ZN=F", "ZB=F",
           "6E=F", "6J=F", "6B=F", "DX-Y.NYB", "^VIX", "ZS=F", "ZC=F", "ZW=F", "BTC-USD", "ETH-USD", "^STOXX50E", "^FTSE", "^HSI"]
DATA = Path(os.environ.get("DATA_DIR", "/opt/futures-data"))
CAP = float(os.environ.get("CAP_GB", "2")) * 1e9
ENV = Path("/opt/futures-bot/.env")
UA = {"User-Agent": "Mozilla/5.0"}


def used() -> int:
    return sum(f.stat().st_size for f in DATA.rglob("*") if f.is_file()) if DATA.exists() else 0


def fetch(sym: str) -> list[tuple]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?interval=1m&range=7d"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())
    r = d["chart"]["result"][0]; q = r["indicators"]["quote"][0]; out = []
    for i, t in enumerate(r.get("timestamp") or []):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], (q.get("volume") or [None] * (i + 1))[i]
        if None not in (o, h, l, c):
            out.append((int(t), o, h, l, c, int(v or 0)))
    return out


def path(sym: str, day: dt.date) -> Path:
    safe = sym.replace("^", "idx_").replace("=", "_").replace(".", "_")
    return DATA / "1m" / safe / f"{day.isoformat()}.csv.gz"


def rows_in(p: Path) -> int:
    with gzip.open(p, "rt") as f:
        return max(sum(1 for _ in f) - 1, 0)


def collect(dry: bool = False) -> dict:
    today = dt.datetime.now(dt.timezone.utc).date(); st = {"run": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                                          "written": {}, "errors": {}, "capped": False}
    size = used()                                    # measured once, then added to as files are written
    for sym in SYMBOLS:
        try:
            bars = fetch(sym)
        except Exception as e:                       # one symbol's failure never stops the others
            st["errors"][sym] = str(e)[:200]; time.sleep(2); continue
        by = {}
        for b in bars:
            by.setdefault(dt.datetime.fromtimestamp(b[0], dt.timezone.utc).date(), []).append(b)
        n = 0
        for day, rows in sorted(by.items()):
            if day >= today:                         # only complete UTC days
                continue
            p = path(sym, day)
            if p.exists() and rows_in(p) >= len(rows):
                continue
            if size > CAP:
                st["capped"] = True; break
            if not dry:
                p.parent.mkdir(parents=True, exist_ok=True)
                buf = io.StringIO(); w = csv.writer(buf); w.writerow(["utc_epoch", "open", "high", "low", "close", "volume"]); w.writerows(rows)
                old = p.stat().st_size if p.exists() else 0
                tmp = p.with_suffix(".tmp"); tmp.write_bytes(gzip.compress(buf.getvalue().encode())); tmp.replace(p)
                size += p.stat().st_size - old
            n += len(rows)
        st["written"][sym] = n
        time.sleep(1)
    if not dry:
        DATA.mkdir(parents=True, exist_ok=True)
        with (DATA / "runs.jsonl").open("a") as f:
            f.write(json.dumps(st) + "\n")
    return st


def report() -> str:
    today = dt.datetime.now(dt.timezone.utc).date(); days = [today - dt.timedelta(days=k) for k in range(7, 0, -1)]
    wk = [d for d in days if d.weekday() < 5]
    lines, gaps = [], []
    for sym in SYMBOLS:
        have = [d for d in days if path(sym, d).exists()]
        rows = sum(rows_in(path(sym, d)) for d in have)
        miss = [d for d in wk if d not in have and not sym.endswith("-USD")]
        if miss:
            gaps.append(f"{sym} ({', '.join(d.strftime('%a %d') for d in miss)})")
        lines.append(f"{sym} {rows:,}")
    runs = [json.loads(x) for x in (DATA / "runs.jsonl").read_text().splitlines()] if (DATA / "runs.jsonl").exists() else []
    recent = [r for r in runs if r["run"][:10] >= days[0].isoformat()]
    errs = sorted({s for r in recent for s in r["errors"]})
    total = sum(1 for _ in (DATA / "1m").rglob("*.csv.gz")) if (DATA / "1m").exists() else 0
    u = used()
    return (f"**Data collector - weekly report** ({days[0]:%d %b} - {days[-1]:%d %b}, UTC days)\n"
            f"Runs: {len(recent)}; files stored: {total:,}; disk {u / 1e6:,.0f} MB of {CAP / 1e9:.0f} GB"
            + (" - **CAP REACHED, collection stopped**" if u > CAP else "") + "\n"
            f"Rows this week: " + ", ".join(lines) + "\n"
            + (f"Missing weekdays: {'; '.join(gaps)}\n" if gaps else "No missing weekdays.\n")
            + (f"Download failures: {', '.join(errs)}" if errs else "No download failures."))


def post(text: str) -> None:
    env = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1); env[k.strip()] = v.strip()
    req = urllib.request.Request(f"https://discord.com/api/v10/channels/{env['DISCORD_CHANNEL_ID']}/messages",
                                 data=json.dumps({"content": text[:1990]}).encode(), method="POST",
                                 headers={"Authorization": f"Bot {env['DISCORD_TOKEN']}", "Content-Type": "application/json", **UA})
    urllib.request.urlopen(req, timeout=30).read()


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    st = collect(dry)
    print(json.dumps({k: (v if k != "written" else sum(v.values())) for k, v in st.items()}))
    if "--report" in sys.argv or (dt.datetime.now(dt.timezone.utc).weekday() == 6 and not dry):
        txt = report(); print(txt)
        if not dry:
            post(txt)
