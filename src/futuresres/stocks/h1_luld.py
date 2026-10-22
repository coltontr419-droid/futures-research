"""H-family 1 (decisions.md 852): small-cap LULD pause reopenings — continuation or reversal?

    python -m futuresres.stocks.h1_luld fetch       # halts (Nasdaq Trader RSS by date) + Yahoo 1-minute bars (cached)
    python -m futuresres.stocks.h1_luld             # discovery
    python -m futuresres.stocks.h1_luld validate    # sealed half, once
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
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "stocks" / "h1"
ET = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0"}
COST, PRIOR_SD = 0.010, 0.02
RULES = [(side, hold) for side in ("with", "against") for hold in (15, 30)]


def fetch_url(u: str) -> bytes:
    for k in range(4):
        try:
            time.sleep(0.5)
            return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read()
        except Exception:
            time.sleep(2 ** k)
    raise RuntimeError(u)


def trading_days() -> list[dt.date]:
    end = dt.date(2026, 10, 21); d = end - dt.timedelta(days=28); out = []
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def halts(day: dt.date) -> list[dict]:
    x = fetch_url(f"https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts&haltdate={day:%m%d%Y}").decode("utf-8", "replace")
    out = []
    for it in re.findall(r"<item>(.*?)</item>", x, re.S):
        g = lambda tag: (re.search(rf"<ndaq:{tag}>(.*?)</ndaq:{tag}>", it, re.S) or [None, ""])[1].strip()
        if g("ReasonCode") == "LUDP" and g("ResumptionTradeTime"):
            out.append({"sym": g("IssueSymbol"), "halt": g("HaltTime"), "resume": g("ResumptionTradeTime"), "day": day.isoformat()})
    return out


def bars(sym: str, day: dt.date) -> dict:
    a = int(dt.datetime(day.year, day.month, day.day, 9, 30, tzinfo=ET).timestamp()); b = a + 390 * 60
    d = json.loads(fetch_url(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1m&period1={a}&period2={b}"))
    r = d["chart"]["result"][0]; q = r["indicators"]["quote"][0]
    return {int(t): (c, v) for t, c, v in zip(r.get("timestamp") or [], q.get("close") or [], q.get("volume") or []) if c is not None}


def fetch() -> None:
    DIR.mkdir(parents=True, exist_ok=True); f = DIR / "events.jsonl"
    done = {(json.loads(l)["sym"], json.loads(l)["day"]) for l in open(f)} if f.exists() else set()
    with open(f, "a") as fh:
        for day in trading_days():
            H = halts(day); seen = set()
            for h in H:
                if h["sym"] in seen or (h["sym"], h["day"]) in done:
                    continue
                seen.add(h["sym"])
                try:
                    B = bars(h["sym"], day)
                except Exception:
                    B = {}
                fh.write(json.dumps({**h, "bars": B}) + "\n")
            fh.flush(); print(day, "LUDP halts", len(H), "symbols", len(seen), flush=True)


def ret(e: dict) -> dict | None:
    day = dt.date.fromisoformat(e["day"]); B = {int(k): v for k, v in e["bars"].items()}
    if not B:
        return None
    ts = lambda s: int(dt.datetime.combine(day, dt.time.fromisoformat(s[:8]), tzinfo=ET).timestamp())
    th, tr = ts(e["halt"]), ts(e["resume"])
    if not (ts("09:45:00") <= th <= ts("15:30:00")):
        return None
    pre = [t for t in sorted(B) if t < th]
    if len(pre) < 6:
        return None
    p_h, p_5 = B[pre[-1]][0], B[pre[-6]][0]
    if p_h < 1.0 or p_h == p_5:
        return None
    dirn = 1.0 if p_h > p_5 else -1.0
    post = [t for t in sorted(B) if t >= tr + 60]                  # first FULL minute after resumption
    if not post:
        return None
    t0 = post[0]; p0 = B[t0][0]; out = {}
    for side, hold in RULES:
        later = [t for t in sorted(B) if t >= t0 + hold * 60]
        if not later:
            continue
        r = (B[later[0]][0] / p0 - 1) * dirn * (1 if side == "with" else -1) - COST
        out[(side, hold)] = r
    return {"day": e["day"], "r": out, "usd_1m": p0 * (B[t0][1] or 0)}


def run(validate: bool) -> None:
    days = trading_days(); cut = days[len(days) // 2].isoformat()
    E = [x for x in (ret(json.loads(l)) for l in open(DIR / "events.jsonl")) if x]
    E = [x for x in E if (x["day"] >= cut) == validate]
    print(f"{'sealed' if validate else 'discovery'}: events {len(E)}, days {len({x['day'] for x in E})}, median 1-min $ volume after reopen "
          f"${np.median([x['usd_1m'] for x in E]) if E else 0:,.0f}")
    res = {}
    for rule in RULES:
        by = collections.defaultdict(list)
        for x in E:
            if rule in x["r"]:
                by[x["day"]].append(x["r"][rule])
        xs = np.array([v for vs in by.values() for v in vs]); dm = np.array([np.mean(v) for v in by.values()])
        if len(dm) < 3:
            continue
        m = float(xs.mean()); t = float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))))
        line = f"  {rule[0]:7} +{rule[1]}m: n {len(xs)}, mean {m*100:+.2f}%, t(days) {t:+.2f}"
        if validate:
            rng = np.random.default_rng(852)
            pct = float((np.array([(xs * rng.choice((-1.0, 1.0), len(xs))).mean() for _ in range(2000)]) < m).mean() * 100)
            post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + xs.var(ddof=1) / len(xs))
            dec = "CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
            line += f", placebo {pct:.0f}th, posterior {post0*100:+.2f}% -> {dec}"; res[f"{rule}"] = dec
        else:
            res[f"{rule}"] = bool(m > 0 and t > 1.96); line += "  CARRIED" if res[f"{rule}"] else ""
        print(line)
    (ROOT / "reports" / ("h1_validation.json" if validate else "h1_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    a = sys.argv[1:2]
    fetch() if a == ["fetch"] else run(a == ["validate"])
