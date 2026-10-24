"""Calendar families (decisions.md 938): SPY turn-of-month, pre-holiday, pre-FOMC — Yahoo daily 2005-2026.

    python -m futuresres.stocks.k_calendar [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL = 0.0002, 0.02, "2019-01-01"
MONTHS = {m: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                                      "November", "December"), 1)}


def fomc_dates() -> list[str]:
    f = ROOT / "data" / "stocks" / "fomc_dates.json"
    if f.exists():
        return json.loads(f.read_text())
    out = set()
    pages = [f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{y}.htm" for y in range(2005, 2021)]
    pages.append("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
    for u in pages:
        try:
            t = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read().decode("utf-8", "replace")
        except Exception:
            continue
        time.sleep(0.5)
        txt = re.sub(r"<[^>]+>", " ", t); txt = re.sub(r"\s+", " ", txt)
        if "historical" in u:
            y = int(re.search(r"(\d{4})", u.rsplit("/", 1)[1]).group(1))
            for m, d1, d2 in re.findall(r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2})(?:-(\d{1,2}))? Meeting", txt):
                if "Conference Call" in m:
                    continue
                out.add(dt.date(y, MONTHS[m], int(d2 or d1)).isoformat())
        else:
            for blk in re.split(r"(\d{4}) FOMC Meetings", txt)[1:]:
                pass
            parts = re.split(r"(20\d\d) FOMC Meetings", txt)
            for i in range(1, len(parts) - 1, 2):
                y = int(parts[i]); body = parts[i + 1]
                for m, d1, d2 in re.findall(r"(January|February|March|April|May|June|July|August|September|October|November|December)(?:/[A-Za-z]+)? (\d{1,2})-(\d{1,2})", body):
                    try:
                        out.add(dt.date(y, MONTHS[m], int(d2)).isoformat())
                    except ValueError:
                        pass
    L = sorted(out); f.write_text(json.dumps(L)); return L


def main(validate: bool) -> None:
    r = json.loads((ROOT / "data" / "stocks" / "spy_long.json").read_text())["chart"]["result"][0]
    ds = [dt.datetime.fromtimestamp(t, dt.timezone.utc).date() for t in r["timestamp"]]
    c = r["indicators"]["adjclose"][0]["adjclose"]
    keep = [(d, x) for d, x in zip(ds, c) if x is not None]; ds = [d for d, _ in keep]; c = [x for _, x in keep]
    n = len(ds); base = (c[-1] / c[0]) ** (1 / n) - 1                       # mean daily drift (geometric) for the excess benchmark
    sel = lambda d: (d.isoformat() >= SEAL) == validate
    out = {"TOM": [], "PRE-HOL": [], "PRE-FOMC": []}
    # turn of month: buy close of second-to-last session, sell close of 3rd session of next month
    for i in range(2, n - 4):
        if ds[i].month != ds[i + 1].month and sel(ds[i]):
            a, b = i - 1, i + 3
            out["TOM"].append(c[b] / c[a] - 1 - COST - ((1 + base) ** (b - a) - 1))
    # pre-holiday: a weekday missing between consecutive sessions (not a weekend)
    for i in range(2, n - 1):
        gap = (ds[i + 1] - ds[i]).days
        missing = [ds[i] + dt.timedelta(days=k) for k in range(1, gap) if (ds[i] + dt.timedelta(days=k)).weekday() < 5]
        if missing and sel(ds[i]):
            out["PRE-HOL"].append(c[i] / c[i - 1] - 1 - COST - base)
    F = set(fomc_dates()); idx = {d.isoformat(): i for i, d in enumerate(ds)}
    for fd in F:
        i = idx.get(fd)
        if i and sel(ds[i]):
            out["PRE-FOMC"].append(c[i] / c[i - 1] - 1 - COST - base)
    print(f"calendar {'sealed' if validate else 'discovery'} (FOMC dates {len(F)})")
    for k, v in out.items():
        x = np.array(v)
        if len(x) < 5:
            print(f"  {k}: n {len(x)}"); continue
        m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
        line = f"  {k:8}: n {len(x):3}, excess mean {m*100:+.3f}%, t {t:+.2f}"
        if validate:
            rng = np.random.default_rng(938); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
            post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
            line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
        else:
            line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
