"""F-family 3 (decisions.md 739): ForecastEx FNQ trades in the last 15 minutes against the lead-month Nasdaq futures price.

    python -m futuresres.forecastex.f3_fnq            # discovery only
    python -m futuresres.forecastex.f3_fnq validate   # the sealed window, once
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
from zoneinfo import ZoneInfo

import numpy as np
import pyarrow.parquet as pq

from futuresres.kalshi.k1_longshot import PRIOR_SD

ROOT = Path(__file__).resolve().parents[3]
FX = ROOT / "data" / "forecastex"
CT = ZoneInfo("America/Chicago")
DISC = (dt.date(2025, 5, 1), dt.date(2026, 2, 28)); SEAL = (dt.date(2026, 3, 1), dt.date(2026, 10, 9))
D, SLIP, FEE = 0.0025, 0.01, 0.01
import os as _os
F4 = _os.environ.get("F4") == "1"                    # F-family 4 (decisions.md 740): roll days only, 13:00-15:00 CT, |d| >= 0.40%
if F4:
    D = 0.0040


def ts(s: str) -> dt.datetime:
    m = re.match(r"(.*T\d\d:\d\d:\d\d)(?:\.\d+)?([+-]\d\d:\d\d)$", s)
    return dt.datetime.fromisoformat(m.group(1) + m.group(2))


def mnq(lo: dt.date, hi: dt.date) -> dict:
    """{date: (sorted minute-end times UTC, closes)} for the day's highest-volume MNQ contract (lead month)."""
    fs = glob.glob(str(ROOT / "data/parquet/symbol=MNQ/**/*.parquet"), recursive=True) + glob.glob(str(ROOT / "data/parquet_update/symbol=MNQ/**/*.parquet"), recursive=True)
    rows = collections.defaultdict(list)
    for f in fs:
        t = pq.read_table(f, columns=["ts_event", "contract", "close", "volume"]).to_pylist()
        for r in t:
            e = r["ts_event"]; d = e.astimezone(CT).date()
            if lo <= d <= hi:
                rows[d].append((e, r["contract"], r["close"], r["volume"]))
    out = {}
    for d, rs in rows.items():
        # lead month = the nearest quarterly contract not yet past its final settlement (3rd Friday), as ForecastEx defines it - not the
        # volume leader, which rolls a week earlier (a ~1% roll spread on Nasdaq)
        lead = min({c for _, c, _, _ in rs if expiry(c) >= d}, key=expiry, default=None)
        if lead is None:
            continue
        xs = sorted({(e, cl) for e, c, cl, _ in rs if c == lead})
        vol = collections.Counter()
        for _, c, _, v in rs:
            vol[c] += v
        if F4 and vol.most_common(1)[0][0] == lead:
            continue                                  # not a roll day
        out[d] = ([e + dt.timedelta(minutes=1) for e, _ in xs], [cl for _, cl in xs])   # bar end = open time + 1 min
    return out


def expiry(contract: str) -> dt.date:
    """Third Friday of the contract month, e.g. MNQZ2026 -> 2026-12-18."""
    mon = {"H": 3, "M": 6, "U": 9, "Z": 12}[contract[3]]; yr = int(contract[4:])
    first = dt.date(yr, mon, 1); fri = first + dt.timedelta(days=(4 - first.weekday()) % 7)
    return fri + dt.timedelta(days=14)


def settlements() -> dict:
    out = {}
    for f in glob.glob(str(FX / "prices_all" / "*.csv")):
        for r in csv.DictReader(open(f)):
            if r["event_contract"].startswith("FNQ_") and r["subtype"] == "YES" and r["settlement_price"] in ("1.00", "0.00"):
                out[r["event_contract"]] = int(float(r["settlement_price"]))
    return out


def main(argv) -> int:
    validate = argv[:1] == ["validate"]; w = SEAL if validate else DISC
    S = settlements(); M = mnq(w[0], w[1]); per = collections.defaultdict(list); hits = []
    for f in sorted(glob.glob(str(FX / "pairs_all" / "*.csv"))):
        for r in csv.DictReader(open(f)):
            c = r["event_contract"]
            if not c.startswith("FNQ_") or c not in S:
                continue
            _, ds, k = c.split("_"); d = dt.datetime.strptime(ds, "%m%d%y").date()
            if not w[0] <= d <= w[1] or d not in M:
                continue
            t = ts(r["pair_time"]).astimezone(CT)
            if t.date() != d or not (dt.time(13, 0) if F4 else dt.time(14, 45)) <= t.time() < dt.time(15, 0):
                continue
            times, cl = M[d]; i = bisect.bisect_right(times, t - dt.timedelta(minutes=1)) - 1
            if i < 0 or (t - times[i]) > dt.timedelta(minutes=5):
                continue
            F = cl[i]; K = float(k); dd = (F - K) / F
            side = "YES" if dd >= D else ("NO" if dd <= -D else None)
            if side is None:
                continue
            price = float(r["yes_price"] if side == "YES" else r["no_price"])
            if price > 0.90:
                continue
            won = S[c] == (1 if side == "YES" else 0); hits.append(won)
            per[d].append(((1.0 if won else 0.0) - price - SLIP - FEE, float(r["quantity"]), price))
    assert all(w[0] <= d <= w[1] for d in per)
    x = np.array([sum(n * q for n, q, _ in v) / sum(q for _, q, _ in v) for _, v in sorted(per.items())]); n = len(x)
    m_ = float(x.mean()) if n else float("nan"); t_ = float(m_ / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
    allq = [z for v in per.values() for z in v]
    res = {"window": [str(w[0]), str(w[1])], "dates": n, "trades": len(allq), "contracts": sum(z[1] for z in allq), "mean_net_dated": m_, "t": t_,
           "hit_rate": float(np.mean(hits)) if hits else None, "pnl_dollars": float(sum(z[0] * z[1] for z in allq)),
           "mean_price": float(np.mean([z[2] for z in allq])) if allq else None}
    if validate:
        rng = np.random.default_rng(739)
        pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m_).mean() * 100)
        post0 = m_ * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
        res.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t_ > 1.645 and pct >= 95 and m_ > 0 and post0 > 0) else ("WATCHLIST" if m_ > 0 else "REJECT"))
    else:
        res["carried"] = bool(t_ > 1.96 and m_ > 0)
    print(json.dumps(res, indent=1))
    (ROOT / "reports" / (("f4" if F4 else "f3") + ("_validation.json" if validate else "_discovery.json"))).write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
