"""F-family 2 (decisions.md 728): ForecastEx hourly temperature contracts traded after the deciding METAR is public.

    python -m futuresres.forecastex.f2_hourly            # discovery only
    python -m futuresres.forecastex.f2_hourly validate   # the sealed window, once
"""

from __future__ import annotations

import bisect
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
STATION = {"HRULAX": "LAX", "HRULGA": "LGA", "HRUSFO": "SFO", "HRULAS": "LAS", "HRUMIA": "MIA"}
DISC = (dt.date(2026, 9, 23), dt.date(2026, 10, 7)); SEAL = (dt.date(2026, 10, 8), dt.date(2026, 10, 18))
LAG = dt.timedelta(minutes=3); SLIP, FEE = 0.01, 0.01
UTC = dt.timezone.utc


def ts(s: str) -> dt.datetime:
    m = re.match(r"(.*T\d\d:\d\d:\d\d)(?:\.\d+)?([+-]\d\d:\d\d)$", s)
    return dt.datetime.fromisoformat(m.group(1) + m.group(2)).astimezone(UTC)


def metars() -> dict:
    """{station: (sorted times, temps F)} from the T-group (tenths C) or the main body."""
    out = {}
    for s in STATION.values():
        rows = []
        for r in csv.DictReader(open(FX / "asos" / f"{s}.csv")):
            m = re.search(r" RMK .*?\bT([01])(\d{3})([01])\d{3}\b", r["metar"]); c = None
            if m:
                c = (-1 if m.group(1) == "1" else 1) * int(m.group(2)) / 10
            else:
                b = re.search(r" (M?\d\d)/(M?\d\d)? ", r["metar"])
                if b:
                    c = -int(b.group(1)[1:]) if b.group(1).startswith("M") else int(b.group(1))
            if c is not None:
                rows.append((dt.datetime.fromisoformat(r["valid"]).replace(tzinfo=UTC), round(c * 9 / 5 + 32)))
        rows.sort(); out[s] = ([t for t, _ in rows], [f for _, f in rows])
    return out


def settlements() -> dict:
    out = {}
    for f in glob.glob(str(FX / "prices_hr" / "*.csv")):
        for r in csv.DictReader(open(f)):
            if r["subtype"] == "YES" and r["date"] == r["expiration_date"][:10] and r["settlement_price"] in ("1.00", "0.00", "1", "0"):
                out[r["event_contract"]] = int(float(r["settlement_price"]))
    return out


def trades(window) -> tuple[dict, list]:
    M = metars(); S = settlements(); per = collections.defaultdict(list); hits = []
    for f in sorted(glob.glob(str(FX / "pairs_hr" / "*.csv"))):
        for r in csv.DictReader(open(f)):
            p, code, k = r["event_contract"].split("_")
            if p not in STATION or r["event_contract"] not in S:
                continue
            close = ts(r["expiration_date"]); d = close.astimezone(dt.timezone(dt.timedelta(hours=-5))).date()
            if not window[0] <= d <= window[1]:
                continue
            t = ts(r["pair_time"]); times, temps = M[STATION[p]]
            i = bisect.bisect_right(times, min(t - LAG, close)) - 1
            if i < 0 or times[i] <= close - dt.timedelta(minutes=60):
                continue
            F, X = temps[i], float(k)
            side = "YES" if F >= X + 2 else ("NO" if F <= X - 1 else None)
            if side is None:
                continue
            price = float(r["yes_price"] if side == "YES" else r["no_price"])
            if price > 0.90:
                continue
            won = S[r["event_contract"]] == (1 if side == "YES" else 0)
            per[d].append(((1.0 if won else 0.0) - price - SLIP - FEE, float(r["quantity"]), p, (close - t).total_seconds() / 60, price))
            hits.append(won)
    return per, hits


def main(argv) -> int:
    validate = argv[:1] == ["validate"]; w = SEAL if validate else DISC
    per, hits = trades(w)
    assert all(w[0] <= d <= w[1] for d in per)
    x = np.array([sum(n * q for n, q, *_ in v) / sum(q for _, q, *_ in v) for d, v in sorted(per.items())]); n = len(x)
    m = float(x.mean()) if n else float("nan"); t = float(m / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
    allq = [z for v in per.values() for z in v]; qty = sum(z[1] for z in allq)
    res = {"window": [str(w[0]), str(w[1])], "dates": n, "trades": len(allq), "contracts": qty, "mean_net_dated": m, "t": t,
           "hit_rate": float(np.mean(hits)) if hits else None, "pnl_dollars": float(sum(z[0] * z[1] for z in allq)),
           "by_city": {c: {"trades": sum(1 for z in allq if z[2] == c), "contracts": sum(z[1] for z in allq if z[2] == c),
                           "pnl": round(sum(z[0] * z[1] for z in allq if z[2] == c), 2)} for c in STATION},
           "mean_price": float(np.mean([z[4] for z in allq])) if allq else None,
           "minutes_to_close_median": float(np.median([z[3] for z in allq])) if allq else None}
    if validate:
        rng = np.random.default_rng(728)
        pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m).mean() * 100)
        post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
        res.update(placebo_pct=pct, posterior_zero_prior=post0,
                   decision="CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        res["carried"] = bool(t > 1.96 and m > 0)
    print(json.dumps(res, indent=1))
    (ROOT / "reports" / ("f2_validation.json" if validate else "f2_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
