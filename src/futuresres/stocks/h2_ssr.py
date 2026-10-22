"""H-family 2 (decisions.md 853): Rule 201 (SSR) days — does a stock that triggered the short-sale restriction drift up while it applies?

    python -m futuresres.stocks.h2_ssr fetch      # universe + Yahoo daily bars (cached, resumable)
    python -m futuresres.stocks.h2_ssr            # discovery
    python -m futuresres.stocks.h2_ssr validate   # sealed, once
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "stocks" / "h2"
UA = {"User-Agent": "Mozilla/5.0"}
COST, PRIOR_SD = 0.005, 0.02
START, SEAL, END = "2025-07-01", "2026-03-01", "2026-10-20"
RULES = ("close->next open", "close->next close", "next open->next close")


def get(u: str) -> dict:
    for k in range(4):
        try:
            time.sleep(0.3)
            return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={**UA, "Accept": "application/json"}), timeout=60).read())
        except Exception:
            time.sleep(2 ** k)
    raise RuntimeError(u)


def fetch() -> None:
    DIR.mkdir(parents=True, exist_ok=True); uf = DIR / "universe.json"
    if not uf.exists():
        rows = get("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true")["data"]["rows"]
        uf.write_text(json.dumps([r["symbol"].strip() for r in rows if r["symbol"].strip().isalpha()]))
    syms = json.loads(uf.read_text()); f = DIR / "daily.jsonl"
    done = {json.loads(l)["sym"] for l in open(f)} if f.exists() else set()
    a = int(dt.datetime(2025, 5, 1, tzinfo=dt.timezone.utc).timestamp()); b = int(dt.datetime(2026, 10, 22, tzinfo=dt.timezone.utc).timestamp())
    with open(f, "a") as fh:
        for i, s in enumerate(syms):
            if s in done:
                continue
            try:
                r = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval=1d&period1={a}&period2={b}")["chart"]["result"][0]; q = r["indicators"]["quote"][0]
                fh.write(json.dumps({"sym": s, "t": r["timestamp"], "o": q["open"], "h": q["high"], "l": q["low"], "c": q["close"], "v": q["volume"]}) + "\n")
            except Exception:
                fh.write(json.dumps({"sym": s, "err": 1}) + "\n")
            if i % 250 == 0:
                fh.flush(); print(f"  {i}/{len(syms)}", flush=True)


def events() -> list[dict]:
    out = []
    for l in open(DIR / "daily.jsonl"):
        d = json.loads(l)
        if d.get("err"):
            continue
        days = [dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat() for t in d["t"]]
        o, h, lo, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]; last = -99
        for i in range(21, len(days) - 1):
            if None in (c[i - 1], lo[i], c[i], o[i + 1], c[i + 1]) or not START <= days[i] <= END:
                continue
            dv = [c[j] * v[j] for j in range(i - 20, i) if c[j] is not None and v[j] is not None]
            if c[i - 1] < 1.0 or not dv or np.median(dv) < 1e6 or i - last < 10:
                continue
            if lo[i] <= 0.90 * c[i - 1]:
                last = i
                out.append({"sym": d["sym"], "day": days[i], "r": {RULES[0]: o[i + 1] / c[i] - 1 - COST, RULES[1]: c[i + 1] / c[i] - 1 - COST,
                                                                   RULES[2]: c[i + 1] / o[i + 1] - 1 - COST}})
    return out


def run(validate: bool) -> None:
    E = [e for e in events() if (e["day"] >= SEAL) == validate]; res = {}
    print(f"{'sealed' if validate else 'discovery'}: SSR events {len(E)}, days {len({e['day'] for e in E})}")
    for rule in RULES:
        for tag, sub in (("all", E), ("excl. last 60 days", [e for e in E if e["day"] < "2026-08-21"])):
            by = collections.defaultdict(list)
            for e in sub:
                by[e["day"]].append(e["r"][rule])
            xs = np.array([x for v in by.values() for x in v]); dm = np.array([np.mean(v) for v in by.values()])
            if len(dm) < 3:
                continue
            m = float(xs.mean()); t = float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))))
            line = f"  {rule:22} [{tag}]: n {len(xs)}, mean {m*100:+.2f}%, t(days) {t:+.2f}"
            if tag == "all":
                if validate:
                    rng = np.random.default_rng(853)
                    pct = float((np.array([(xs * rng.choice((-1.0, 1.0), len(xs))).mean() for _ in range(2000)]) < m).mean() * 100)
                    post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + xs.var(ddof=1) / len(xs))
                    res[rule] = "CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
                    line += f", placebo {pct:.0f}th -> {res[rule]}"
                else:
                    res[rule] = bool(m > 0 and t > 1.96); line += "  CARRIED" if res[rule] else ""
            print(line)
    (ROOT / "reports" / ("h2_validation.json" if validate else "h2_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    a = sys.argv[1:2]
    fetch() if a == ["fetch"] else run(a == ["validate"])
