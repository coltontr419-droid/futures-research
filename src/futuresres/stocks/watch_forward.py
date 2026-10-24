"""Forward watchlist logger (decisions.md 991, 993): monthly, record L18's top-10 discount z-score CEFs and any new CEF-activist 13Ds.

    python -m futuresres.stocks.watch_forward      # appends to reports/watch_forward.jsonl
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

import numpy as np

from futuresres.stocks import l18_cef
from futuresres.stocks.l19_cefact import ACT

ROOT = Path(__file__).resolve().parents[3]
LOG = ROOT / "reports" / "watch_forward.jsonl"


def l18_picks() -> dict:
    funds = json.loads((l18_cef.OUT / "funds.json").read_text())
    for s in funds:                                              # refresh the cache: forward picks need current prices and NAVs
        for sym in (s, f"X{s}X"):
            (l18_cef.OUT / f"{sym}.json").unlink(missing_ok=True)
    z = {}
    for s in funds:
        p, n = l18_cef.yahoo(s), l18_cef.yahoo(f"X{s}X")
        if not p or not n:
            continue
        P, N = l18_cef.series(p, "close"), l18_cef.series(n, "close")
        ds = sorted(d for d in P if d in N and N[d] > 0)[-252:]
        if len(ds) < 200:
            continue
        D = [P[d] / N[d] - 1 for d in ds]; sd = float(np.std(D, ddof=1))
        if sd > 0:
            z[s] = ((D[-1] - float(np.mean(D))) / sd, ds[-1], D[-1])
    top = sorted(z, key=lambda s: z[s][0])[:l18_cef.K]
    return {"asof": max(v[1] for v in z.values()), "top": [[s, round(z[s][0], 2), round(z[s][2], 4)] for s in top], "universe": len(z)}


def l19_new(since: str) -> list:
    u = (f"https://efts.sec.gov/LATEST/search-index?forms=SC%2013D,SCHEDULE%2013D&dateRange=custom&startdt={since}"
         f"&enddt={dt.date.today().isoformat()}")
    funds = set(json.loads((l18_cef.OUT / "funds.json").read_text())); out, frm = [], 0
    while True:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(u + f"&from={frm}", headers={"User-Agent": "futures-research-screen research-bot/1.0"}), timeout=60).read())
        hs = r["hits"]["hits"]
        for h in hs:
            s = h["_source"]
            if s["form"] not in ("SC 13D", "SCHEDULE 13D"):
                continue
            names = s["display_names"]; tk = next((m.group(1) for nm in names for m in [re.search(r"\(([A-Z]{2,5})(?:,|\))", nm)] if m and m.group(1) in funds), None)
            if tk and any(a in " ".join(names).lower() for a in ACT):
                out.append({"tk": tk, "date": s["file_date"], "names": names})
        frm += len(hs)
        if not hs or frm >= r["hits"]["total"]["value"]:
            return out


def main() -> None:
    prev = [json.loads(l) for l in open(LOG)] if LOG.exists() else []
    since = prev[-1]["run"] if prev else "2026-10-01"
    rec = {"run": dt.date.today().isoformat(), "l18": l18_picks(), "l19_new": l19_new(since)}
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec)[:600])


if __name__ == "__main__":
    main()
