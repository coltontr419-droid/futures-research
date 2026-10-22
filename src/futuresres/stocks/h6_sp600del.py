"""H-family 6 (decisions.md 863): S&P SmallCap 600 deletions for size — rebound after the index funds' forced sale.

    python -m futuresres.stocks.h6_sp600del            # discovery (effective before 2025-01-01)
    python -m futuresres.stocks.h6_sp600del validate   # sealed (from 2025-01-01), once
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
DIR = ROOT / "data" / "stocks" / "h6"
UA = {"User-Agent": "Mozilla/5.0"}
COST, PRIOR_SD, SEAL = 0.005, 0.02, "2025-01-01"
SIZE = re.compile(r"no longer representative|market cap|market capitali[sz]ation|size", re.I)
EXCL = re.compile(r"acquir|merg|spun|spin|S&P 400|MidCap|S&P 500|bought|taken private|bankrupt|delist", re.I)


def get(u: str) -> bytes:
    for k in range(4):
        try:
            time.sleep(0.4)
            return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read()
        except Exception:
            time.sleep(2 ** k)
    raise RuntimeError(u)


def deletions() -> list[dict]:
    w = json.loads(get("https://en.wikipedia.org/w/api.php?action=parse&page=List_of_S%26P_600_companies&prop=wikitext&format=json"))["parse"]["wikitext"]["*"]
    s = w[w.index("Recent and announced changes"):]; out = []
    for row in s.split("\n|-")[1:]:
        cells = [c.strip() for c in re.split(r"\|\||\n\|", row) if c.strip()]
        if len(cells) < 6:
            continue
        try:
            date = dt.datetime.strptime(re.sub(r"\[\[|\]\]", "", cells[0]).strip("| "), "%B %d, %Y").date()
        except ValueError:
            continue
        removed, reason = re.sub(r"[\[\]{}|]", "", cells[3]).strip(), re.sub(r"<ref.*", "", " ".join(cells[5:]), flags=re.S)
        sym = removed.split()[0] if removed else ""
        if sym and SIZE.search(reason) and not EXCL.search(reason.split("which")[0] if "replaced" in reason else reason):
            out.append({"sym": sym.replace(".", "-"), "eff": date.isoformat(), "reason": reason[:160]})
    return out


def run(validate: bool) -> None:
    DIR.mkdir(parents=True, exist_ok=True); D = [d for d in deletions() if "2023-01-01" <= d["eff"] <= "2026-10-20" and (d["eff"] >= SEAL) == validate]
    rows = []
    for d in D:
        eff = dt.date.fromisoformat(d["eff"]); a = int(dt.datetime(eff.year, eff.month, eff.day, tzinfo=dt.timezone.utc).timestamp()) - 20 * 86400
        try:
            r = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{d['sym']}?interval=1d&period1={a}&period2={a + 45 * 86400}"))["chart"]["result"][0]
        except Exception:
            continue
        days = [dt.datetime.fromtimestamp(t, dt.timezone.utc).date() for t in r["timestamp"]]; c = r["indicators"]["quote"][0]["close"]
        pre = [i for i, x in enumerate(days) if x < eff]
        if not pre or pre[-1] + 6 >= len(days) or None in (c[pre[-1]], c[pre[-1] + 1], c[pre[-1] + 5]):
            continue
        i = pre[-1]; rows.append({**d, "r1": c[i + 1] / c[i] - 1 - COST, "r5": c[i + 5] / c[i] - 1 - COST})
    print(f"H6 {'sealed' if validate else 'discovery'}: size deletions {len(D)}, priced {len(rows)}")
    res = {}
    for k in ("r1", "r5"):
        by = collections.defaultdict(list)
        for x in rows:
            by[x["eff"]].append(x[k])
        xs = np.array([v for vs in by.values() for v in vs]); dm = np.array([np.mean(v) for v in by.values()])
        if len(dm) < 3:
            continue
        m = float(xs.mean()); t = float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))))
        line = f"  {'next close' if k == 'r1' else '+5 closes'}: n {len(xs)}, mean {m*100:+.2f}%, median {np.median(xs)*100:+.2f}%, t {t:+.2f}"
        if validate:
            rng = np.random.default_rng(863)
            pct = float((np.array([(xs * rng.choice((-1.0, 1.0), len(xs))).mean() for _ in range(2000)]) < m).mean() * 100)
            post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + xs.var(ddof=1) / len(xs))
            res[k] = "CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT"); line += f" -> {res[k]}"
        else:
            res[k] = bool(m > 0 and t > 1.96); line += "  CARRIED" if res[k] else ""
        print(line)
    for x in rows[:40]:
        print(f"    {x['eff']} {x['sym']:6} r1 {x['r1']*100:+.1f}% r5 {x['r5']*100:+.1f}% | {x['reason'][:70]}")
    (ROOT / "reports" / ("h6_validation.json" if validate else "h6_discovery.json")).write_text(json.dumps({"res": res, "rows": rows}, indent=0, default=str) + "\n")


if __name__ == "__main__":
    run(sys.argv[1:2] == ["validate"])
