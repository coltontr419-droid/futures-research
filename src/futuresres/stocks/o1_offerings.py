"""O-family 1 (decisions.md 925): follow-on offering pricings — buy the close after the drop, hold 5 / 20 sessions.

    python -m futuresres.stocks.o1_offerings fetch
    python -m futuresres.stocks.o1_offerings [validate]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

from futuresres.stocks.i1_insider import bars

ROOT = Path(__file__).resolve().parents[3]
BUYBACK = "--buyback" in sys.argv                    # decisions.md 927: O-family 2
OUT = ROOT / "data" / "stocks" / ("o2" if BUYBACK else "o1")
UA = {"User-Agent": "futures-research-screen research-bot/1.0"}
COST, PRIOR_SD, SEAL = 0.003, 0.02, "2026-01-01"


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True); hits = {}
    q = urllib.parse.quote('"share repurchase program" "authorized"' if BUYBACK else '"announces pricing of" "public offering"')
    for a, b in (("2025-06-02", "2025-09-30"), ("2025-10-01", "2025-12-31"), ("2026-01-01", "2026-04-30"), ("2026-05-01", "2026-09-30")):
        frm = 0
        while True:
            u = f"https://efts.sec.gov/LATEST/search-index?q={q}&forms=8-K&dateRange=custom&startdt={a}&enddt={b}&from={frm}"
            for k in range(4):
                try:
                    d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read())
                    if "hits" in d:
                        break
                    time.sleep(5 * (k + 1))
                except Exception:
                    time.sleep(3 * (k + 1))
            else:
                break
            hs = d["hits"]["hits"]
            for h in hs:
                s = h["_source"]; m = re.search(r"\(([A-Z][A-Z0-9.\-]{0,6})(?:,|\))", s["display_names"][0])
                if m:
                    hits.setdefault((m.group(1), s["file_date"]), s["display_names"][0])
            frm += len(hs); time.sleep(0.3)
            if not hs or frm >= min(d["hits"]["total"]["value"], 9900):
                break
    ev, last = [], {}
    for (sym, fd), name in sorted(hits.items(), key=lambda x: x[0][1]):
        if sym in last and (dt.date.fromisoformat(fd) - dt.date.fromisoformat(last[sym])).days < 30:
            continue
        last[sym] = fd; ev.append({"sym": sym, "date": fd, "name": name})
    (OUT / "events.json").write_text(json.dumps(ev)); print("events", len(ev))


def run(validate: bool) -> None:
    B = bars(); sd, so, sc, _ = B["__SPY"]; si = {d: i for i, d in enumerate(sd)}; res = collections.defaultdict(list)
    E = [e for e in json.loads((OUT / "events.json").read_text()) if (e["date"] >= SEAL) == validate]
    for e in E:
        b = B.get(e["sym"])
        if not b:
            continue
        ds, o, c, vol = b
        i0 = next((i for i, d in enumerate(ds) if d > e["date"]), None)
        if i0 is None or i0 < 21 or not c[i0]:
            continue
        dv = [c[j] * vol[j] for j in range(i0 - 20, i0) if c[j] and vol[j]]
        if not dv or (c[i0 - 1] or 0) < 1.0 or float(np.median(dv)) < 1e6:
            continue
        for h in (5, 20):
            x = i0 + h
            if x >= len(ds) or not c[x]:
                continue
            a, z = si.get(ds[i0]), si.get(ds[x])
            if a is None or z is None:
                continue
            if BUYBACK:                                 # entry at the open after the filing; hold h sessions (to the close of i0 + h - 1)
                x2 = i0 + h - 1; z2 = si.get(ds[x2])
                if not o[i0] or not c[x2] or z2 is None:
                    continue
                raw = c[x2] / o[i0] - 1 - COST; res[h].append((e["date"], raw, raw - (sc[z2] / so[a] - 1)))
            else:
                raw = c[x] / c[i0] - 1 - COST; res[h].append((e["date"], raw, raw - (sc[z] / sc[a] - 1)))
    print(f"{'O2' if BUYBACK else 'O1'} {'sealed' if validate else 'discovery'}: events {len(E)}")
    for h, v in sorted(res.items()):
        by = collections.defaultdict(list)
        for d, _, adj in v:
            by[d].append(adj)
        a = np.array([x[2] for x in v]); rw = np.array([x[1] for x in v]); dm = np.array([np.mean(x) for x in by.values()])
        if len(dm) < 3:
            continue
        t = float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm)))); m = float(a.mean())
        line = f"  hold {h:2}d: n {len(a):4} raw {rw.mean()*100:+.2f}% adj {m*100:+.2f}% (median {np.median(a)*100:+.2f}%) t {t:+.2f}"
        if h == (20 if BUYBACK else 5):
            if validate:
                rng = np.random.default_rng(927 if BUYBACK else 925); pct = float((np.array([(a * rng.choice((-1.0, 1.0), len(a))).mean() for _ in range(4000)]) < m).mean() * 100)
                post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + a.var(ddof=1) / len(a))
                line += f" placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
            else:
                line += "  CARRIED" if (m > 0 and t > 1.96 and rw.mean() > 0) else "  not carried"
        print(line)


if __name__ == "__main__":
    a = sys.argv[1:2]
    fetch() if a == ["fetch"] else run(a == ["validate"])
