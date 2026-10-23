"""E-family 2 (decisions.md 912): post-earnings drift after large positive surprises.

    python -m futuresres.stocks.e2_pead fetch       # Nasdaq earnings calendar by day (cached) + SPY
    python -m futuresres.stocks.e2_pead             # discovery (reports before 2026-01-01)
    python -m futuresres.stocks.e2_pead validate    # sealed (from 2026-01-01), once
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "stocks" / "e2"
H2 = ROOT / "data" / "stocks" / "h2" / "daily.jsonl"
COST, PRIOR_SD, SEAL = 0.002, 0.02, "2026-01-01"
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def get(u: str):
    for k in range(4):
        try:
            time.sleep(0.4)
            return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read())
        except Exception:
            time.sleep(2 ** k)
    return None


def num(s) -> float | None:
    if s in (None, "", "N/A"):
        return None
    v = re.sub(r"[^\d.\-()]", "", str(s)).replace("(", "-").replace(")", "")
    try:
        return float(v)
    except ValueError:
        return None


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True); f = OUT / "calendar.jsonl"
    done = {json.loads(l)["date"] for l in open(f)} if f.exists() else set()
    d = dt.date(2025, 6, 2)
    with open(f, "a") as fh:
        while d <= dt.date(2026, 9, 30):
            if d.weekday() < 5 and d.isoformat() not in done:
                r = get(f"https://api.nasdaq.com/api/calendar/earnings?date={d.isoformat()}")
                rows = ((r or {}).get("data") or {}).get("rows") or []
                fh.write(json.dumps({"date": d.isoformat(), "rows": rows}) + "\n"); fh.flush()
            d += dt.timedelta(days=1)
    spy = get("https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&period1=1746057600&period2=1792800000")
    (OUT / "spy.json").write_text(json.dumps(spy)); print("calendar days", sum(1 for _ in open(f)), flush=True)


def bars() -> dict:
    B = {}
    for l in open(H2):
        x = json.loads(l)
        if x.get("err") or not x.get("t"):
            continue
        B[x["sym"]] = ([dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat() for t in x["t"]], x["o"], x["c"])
    s = json.loads((OUT / "spy.json").read_text())["chart"]["result"][0]; q = s["indicators"]["quote"][0]
    B["__SPY"] = ([dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat() for t in s["timestamp"]], q["open"], q["close"])
    return B


def run(validate: bool) -> None:
    B = bars(); sd, so, sc = B["__SPY"]; si = {d: i for i, d in enumerate(sd)}
    res = collections.defaultdict(list)
    for l in open(OUT / "calendar.jsonl"):
        day = json.loads(l)
        if (day["date"] >= SEAL) != validate:
            continue
        for r in day["rows"]:
            fc, sp, mc, ne = num(r.get("epsForecast")), num(r.get("surprise")), num(r.get("marketCap")), num(r.get("noOfEsts"))
            if fc is None or sp is None or abs(fc) < 0.05 or (ne or 0) < 2 or (mc or 0) < 3e8 or sp < 20:
                continue
            b = B.get(r["symbol"].strip())
            if not b:
                continue
            ds, o, c = b; idx = {d: i for i, d in enumerate(ds)}
            i0 = idx.get(day["date"])
            if i0 is None:
                continue
            e = i0 if "pre-market" in (r.get("time") or "") else i0 + 1
            for h in (5, 20):
                x = e + h - 1
                if x >= len(ds) or o[e] is None or c[x] is None or o[e] <= 0:
                    continue
                raw = c[x] / o[e] - 1 - COST
                a, z = si.get(ds[e]), si.get(ds[x])
                if a is None or z is None:
                    continue
                adj = raw - (sc[z] / so[a] - 1)
                for tag in (("≥20%", True), ("≥50%", sp >= 50)):
                    if tag[1]:
                        res[(tag[0], h)].append((day["date"], raw, adj))
    print(f"E2 {'sealed' if validate else 'discovery'}")
    for (tag, h), v in sorted(res.items()):
        by = collections.defaultdict(list)
        for d, raw, adj in v:
            by[d].append(adj)
        a = np.array([x[2] for x in v]); rw = np.array([x[1] for x in v]); dm = np.array([np.mean(x) for x in by.values()])
        if len(dm) < 3:
            continue
        t = float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm)))); m = float(a.mean())
        line = f"  surprise {tag} hold {h:2}d: n {len(a):4} raw {rw.mean()*100:+.2f}% adj {m*100:+.2f}% (median {np.median(a)*100:+.2f}%) t {t:+.2f}"
        if (tag, h) == ("≥20%", 5):
            if validate:
                rng = np.random.default_rng(912); pct = float((np.array([(a * rng.choice((-1.0, 1.0), len(a))).mean() for _ in range(4000)]) < m).mean() * 100)
                post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + a.var(ddof=1) / len(a))
                line += f" placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
            else:
                line += "  CARRIED" if (m > 0 and t > 1.96 and rw.mean() > 0) else "  not carried"
        print(line)


if __name__ == "__main__":
    a = sys.argv[1:2]
    fetch() if a == ["fetch"] else run(a == ["validate"])
