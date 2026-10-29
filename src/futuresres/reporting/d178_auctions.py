"""D-series family 178 (decisions.md §1129): Treasury coupon-auction strength (bid-to-cover, indirect share vs the last 6 in the bucket) -> ZN next session.

    python -m futuresres.reporting.d178_auctions fetch
    python -m futuresres.reporting.d178_auctions [validate]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np
from curl_cffi import requests

import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d12_extreme as d12

ROOT = Path(__file__).resolve().parents[3]
F = ROOT / "data" / "treasury" / "auctions.json"
API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
DISC = (dt.date(2010, 1, 1), dt.date(2022, 12, 31)); VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))


def fetch() -> None:
    F.parent.mkdir(parents=True, exist_ok=True); rows, page = [], 1
    while True:
        r = requests.get(API, params={"filter": "security_type:in:(Note,Bond),auction_date:gte:2009-01-01", "page[size]": 1000, "page[number]": page,
                                      "fields": "auction_date,security_type,security_term,bid_to_cover_ratio,indirect_bidder_accepted,total_accepted"}, timeout=60).json()
        rows += r["data"]
        if page >= r["meta"]["total-pages"]:
            break
        page += 1
    F.write_text(json.dumps(rows)); print(len(rows))


def signals():
    rows = sorted(json.loads(F.read_text()), key=lambda r: r["auction_date"]); hist = collections.defaultdict(list); day = collections.defaultdict(lambda: ([], []))
    for r in rows:
        try:
            m = re.match(r"(\d+)-Year(?: (\d+)-Month)?", r["security_term"]); yrs = round(int(m.group(1)) + (int(m.group(2) or 0)) / 12)
            btc = float(r["bid_to_cover_ratio"]); ind = float(r["indirect_bidder_accepted"]) / float(r["total_accepted"])
        except (TypeError, ValueError, AttributeError, ZeroDivisionError):
            continue
        h = hist[yrs]
        if len(h) >= 6:
            d = dt.date.fromisoformat(r["auction_date"])
            day[d][0].append(btc - np.mean([a for a, _ in h[-6:]])); day[d][1].append(ind - np.mean([b for _, b in h[-6:]]))
        h.append((btc, ind))
    return {d: (float(np.mean(a)), float(np.mean(b))) for d, (a, b) in day.items()}


def cell(S, G, k, rule, lo, hi):
    days = sorted(S["ZN"]); x, al, sd = [], [], []
    for d, g in sorted(G.items()):
        if not (lo <= d <= hi):
            continue
        nxt = next((v for v in days if v > d), None)
        if nxt is None or (nxt - d).days > 4:
            continue
        side = (1.0 if g[k] > 0 else -1.0) * rule; y = S["ZN"][nxt]; c = d12.COST["ZN"]
        x.append(side * y - c); al.append((side - 1) * y - (c if side < 0 else 0.0)); sd.append(side)
    return np.array(x), np.array(al), np.array(sd)


def t(x):
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def main(validate: bool) -> None:
    S = d10.series(); G = signals(); out = {"cells": []}
    for k, nm in ((0, "bid_to_cover"), (1, "indirect_share")):
        for rule, rn in ((1, "follow"), (-1, "fade")):
            x, _, _ = cell(S, G, k, rule, *DISC); r = {"measure": nm, "rule": rn, "n": len(x), "mean_bps": round(float(x.mean()), 2), "t": round(t(x), 2)}
            out["cells"].append(r); print("discovery", r)
            if validate and r["mean_bps"] > 0 and r["t"] > 1.96:
                x, al, sd = cell(S, G, k, rule, *VAL); y = (x + d12.COST["ZN"]) * sd; rng = np.random.default_rng(1129); m = x.mean()
                pct = float((np.array([(np.roll(sd, rng.integers(1, len(sd))) * y - d12.COST["ZN"]).mean() for _ in range(2000)]) < m).mean() * 100)
                v = "CONFIRM" if t(x) > 1.645 and t(al) > 1.645 and pct >= 95 else ("WATCHLIST" if m > 0 else "REJECT")
                r.update(sealed_n=len(x), sealed_mean=round(float(m), 2), sealed_t=round(t(x), 2), vs_long_t=round(t(al), 2), placebo=pct, decision=v); print("sealed", r)
    (ROOT / "reports" / f"d178_{'sealed' if validate else 'discovery'}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    if sys.argv[1:] == ["fetch"]:
        fetch()
    else:
        main(sys.argv[1:] == ["validate"])
