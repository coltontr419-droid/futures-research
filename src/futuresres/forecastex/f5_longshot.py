"""F-family 5 (decisions.md 757): favourite / long-shot bias across every ForecastEx product, trades >= 24 h before expiration.

    python -m futuresres.forecastex.f5_longshot            # discovery: expirations before 2026-03-01
    python -m futuresres.forecastex.f5_longshot validate   # sealed 2026-03-01 -> 2026-10-19, once
"""

from __future__ import annotations

import collections
import csv
import datetime as dt
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.k1_longshot import PRIOR_SD

ROOT = Path(__file__).resolve().parents[3]
FX = ROOT / "data" / "forecastex"
SEAL = dt.date(2026, 3, 1); END = dt.date(2026, 10, 19)
SLIP, FEE = 0.01, 0.01


def ts(s: str) -> dt.datetime:
    m = re.match(r"(.*T\d\d:\d\d:\d\d)(?:\.\d+)?([+-]\d\d:\d\d)$", s)
    return dt.datetime.fromisoformat(m.group(1) + m.group(2))


def settlements() -> dict:
    out = {}
    for f in glob.glob(str(FX / "prices_all" / "*.csv")):
        for r in csv.DictReader(open(f)):
            if r["subtype"] == "YES" and r["settlement_price"] in ("1.00", "0.00"):
                out[r["event_contract"]] = int(float(r["settlement_price"]))
    return out


def run(validate: bool) -> dict:
    S = settlements(); cat = {}
    for f in glob.glob(str(FX / "summary" / "*.csv")):
        for r in csv.DictReader(open(f)):
            cat[r["product_id"]] = r["product_category"]
    per = {k: collections.defaultdict(lambda: [0.0, 0.0]) for k in ("longshot_NO", "favourite_YES")}
    bycat = {k: collections.defaultdict(lambda: [0.0, 0.0]) for k in per}
    for f in sorted(glob.glob(str(FX / "pairs_all" / "*.csv"))):
        for r in csv.DictReader(open(f)):
            c = r["event_contract"]
            if c not in S:
                continue
            exp = ts(r["expiration_date"]); d = exp.date()
            if (validate and not SEAL <= d <= END) or (not validate and d >= SEAL):
                continue
            if exp - ts(r["pair_time"]) < dt.timedelta(hours=24):
                continue
            y = float(r["yes_price"]); q = float(r["quantity"])
            if y <= 0.15:
                k = "longshot_NO"; pnl = (1.0 if S[c] == 0 else 0.0) - float(r["no_price"]) - SLIP - FEE
            elif y >= 0.85:
                k = "favourite_YES"; pnl = (1.0 if S[c] == 1 else 0.0) - y - SLIP - FEE
            else:
                continue
            ev = c.split("_")[0] + "_" + r["expiration_date"][:10]
            a = per[k][ev]; a[0] += pnl * q; a[1] += q
            b = bycat[k][cat.get(c.split("_")[0], "?")]; b[0] += pnl * q; b[1] += q
    res = {}
    for k in per:
        x = np.array([s_ / q for s_, q in per[k].values() if q > 0]); n = len(x)
        m = float(x.mean()) if n else float("nan"); t = float(m / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
        r = {"events": n, "contracts": sum(q for _, q in per[k].values()), "mean_net": m, "t": t,
             "by_category": {c_: round(s_ / q * 100, 2) for c_, (s_, q) in bycat[k].items() if q > 1000}}
        if validate:
            rng = np.random.default_rng(757)
            pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m).mean() * 100)
            post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
            r.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT"))
        else:
            r["carried"] = bool(t > 1.96 and m > 0)
        res[k] = r
        print(f"{k}: events {n}, contracts {r['contracts']:,.0f}, mean net {m*100:+.2f}c, t {t:+.2f} | by category (c/contract): {r['by_category']}"
              + (f" -> {r.get('decision')}" if validate else ("  CARRIED" if r["carried"] else "")), flush=True)
    (ROOT / "reports" / ("f5_validation.json" if validate else "f5_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    run(sys.argv[1:2] == ["validate"])
