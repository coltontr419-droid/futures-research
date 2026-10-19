"""F-family 1 (decisions.md 726): buy NO on ForecastEx daily-high contracts at the trade price + 1c slippage + 1c fee.

    python -m futuresres.forecastex.f1_wu            # discovery only
    python -m futuresres.forecastex.f1_wu validate   # the sealed window, once
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
from zoneinfo import ZoneInfo

import numpy as np

from futuresres.forecastex.f0_settle import fx_settlements

ROOT = Path(__file__).resolve().parents[3]
TZ = {"UHLAX": "America/Los_Angeles", "UHMDW": "America/Chicago", "UHAUS": "America/Chicago", "UHMIA": "America/New_York", "UHPHL": "America/New_York"}
SEAL = dt.date(2026, 7, 1)
END = dt.date(2026, 10, 17)
SLIP, FEE = 0.01, 0.01
from futuresres.kalshi.k1_longshot import PRIOR_SD  # noqa: E402


def trades(settle):
    """{(product, window): {date: [(net per contract, qty)]}}"""
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for f in sorted(glob.glob(str(ROOT / "data/forecastex/pairs/*.csv"))):
        for r in csv.DictReader(open(f)):
            p, ds, k = r["event_contract"].split("_")
            if p not in TZ:
                continue
            y = float(r["yes_price"])
            if not 0.10 <= y <= 0.90:
                continue
            d = dt.datetime.strptime(ds, "%m%d%y").date(); s = settle.get((p, d), {}).get(float(k))
            if s is None:
                continue
            m = re.match(r"(.*T\d\d:\d\d:\d\d)(?:\.\d+)?([+-]\d\d:\d\d)$", r["pair_time"])
            t = dt.datetime.fromisoformat(m.group(1) + m.group(2)).astimezone(ZoneInfo(TZ[p]))
            day10 = dt.datetime.combine(d, dt.time(10), ZoneInfo(TZ[p])); day16 = dt.datetime.combine(d, dt.time(16), ZoneInfo(TZ[p]))
            w = "a" if t < day10 else ("b" if t < day16 else None)
            if w is None:
                continue
            cost = float(r["no_price"]) + SLIP + FEE
            out[(p, w)][d].append(((1.0 - s) - cost, float(r["quantity"])))
    return out


def daily(xs):
    return {d: sum(n * q for n, q in v) / sum(q for _, q in v) for d, v in xs.items()}


def stats(dd):
    v = np.array(list(dd.values()))
    t = v.mean() / (v.std(ddof=1) / np.sqrt(len(v))) if len(v) > 2 else float("nan")
    mon = collections.defaultdict(list)
    for d, x in dd.items():
        mon[d.strftime("%Y-%m")].append(x)
    return {"dates": len(v), "mean": float(v.mean()), "t": float(t), "months": {m: round(float(np.mean(x)), 4) for m, x in sorted(mon.items())}}


def main(argv) -> int:
    settle = fx_settlements(); T = trades(settle); res = {}
    validate = argv[:1] == ["validate"]
    for key in sorted(T):
        dd = daily({d: v for d, v in T[key].items() if (SEAL <= d <= END if validate else d < SEAL)})
        assert validate or all(d < SEAL for d in dd)
        qty = sum(q for d, v in T[key].items() if (SEAL <= d <= END if validate else d < SEAL) for _, q in v)
        s = stats(dd); s["contracts_per_date"] = qty / max(len(dd), 1)
        if not validate:
            s["carried"] = bool(s["t"] > 1.96 and s["mean"] > 0 and sum(x > 0 for x in s["months"].values()) >= 4)
        res[f"{key[0]}|{key[1]}"] = s
        print(f"{key[0]} {key[1]}: {s['dates']} dates, mean {s['mean']*100:+.2f}c/contract, t {s['t']:+.2f}, {s['contracts_per_date']:,.0f} contracts/date, months "
              + " ".join(f"{m[5:]}:{x*100:+.1f}" for m, x in s['months'].items()) + (f"  CARRIED" if s.get("carried") else ""), flush=True)
    if validate:
        rng = np.random.default_rng(726); carried = [k for k, v in json.loads((ROOT / "reports" / "f1_discovery.json").read_text()).items() if v["carried"]]
        for k in carried:
            p, w = k.split("|"); dd = daily({d: v for d, v in T[(p, w)].items() if SEAL <= d <= END}); x = np.array(list(dd.values())); n = len(x)
            m = float(x.mean()); t = float(m / (x.std(ddof=1) / np.sqrt(n)))
            pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m).mean() * 100)
            post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
            dec = "CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
            res[k].update(placebo_pct=pct, posterior_zero_prior=post0, decision=dec)
            print(f"VALIDATION {k}: {n} dates, net {m*100:+.2f}c t {t:+.2f} placebo {pct:.0f}% posterior(0-prior) {post0*100:+.2f}c -> {dec}", flush=True)
    (ROOT / "reports" / ("f1_validation.json" if validate else "f1_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
