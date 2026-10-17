"""K-series family 1 - the longshot bias in Kalshi's S&P and Nasdaq daily contracts (decisions.md 664).

    python -m futuresres.kalshi.k1_longshot             (discovery: events settling before 2025-07-01)
    python -m futuresres.kalshi.k1_longshot --validate  (once, sealed 2025-07-01 -> 2026-10-16, the carried cells only)
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "kalshi"
OUT = ROOT / "reports" / "k1_discovery.json"
ET = ZoneInfo("America/New_York")
DISC_END = dt.date(2025, 7, 1)
VAL = (dt.date(2025, 7, 1), dt.date(2026, 10, 16))
SERIES = ("KXINX", "KXINXU", "KXNASDAQ100")
HOURS = (10, 12, 14, 15)
BUCKETS = ((0.01, 0.05), (0.05, 0.10), (0.10, 0.20))


def _q(c: dict, side: str) -> float | None:
    x = c.get(side) or {}
    v = x.get("close_dollars", x.get("close"))
    return float(v) if v not in (None, "") else None


def fee(q: float, n: int = 100) -> float:
    """Taker fee per contract: ceil(0.07 x n x q x (1 - q)) cents per order of n, over n."""
    return math.ceil(round(0.07 * n * q * (1 - q) * 100, 6)) / 100 / n


def trades(series: str, side: str = "no"):
    """(settlement date, hour, bucket index, net P&L per contract, candle volume) for every qualifying contract."""
    for f in sorted((DATA / series).glob("*.json")):
        ev = json.loads(f.read_text())
        for m in ev["markets"]:
            if m.get("result") not in ("yes", "no") or not m.get("candles"):
                continue
            ct = dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(ET); day = ct.date()
            by_end = {int(c["end_period_ts"]): c for c in m["candles"]}
            for h in HOURS:
                ts = int(dt.datetime.combine(day, dt.time(h, 0), ET).timestamp())
                c = by_end.get(ts)
                if c is None or ts >= ct.timestamp():
                    continue
                bid, ask = _q(c, "yes_bid"), _q(c, "yes_ask")
                if bid is None or ask is None or not (bid > 0 and ask < 1 and ask - bid <= 0.10):
                    continue
                mid = (bid + ask) / 2
                for k, (lo, hi) in enumerate(BUCKETS):
                    if lo < mid <= hi:
                        if side == "no":
                            q = 1 - bid                          # buy NO at 1 - yes bid
                            pnl = (1.0 if m["result"] == "no" else 0.0) - q - fee(q)
                        else:                                    # 1b (decisions.md 666): buy YES at the yes ask
                            pnl = (1.0 if m["result"] == "yes" else 0.0) - ask - fee(ask)
                        vol = float(c.get("volume_fp", c.get("volume")) or 0)
                        yield day, h, k, pnl, vol


def _t(x) -> float:
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std() > 0 else float("nan")


def cells(lo: dt.date, hi: dt.date) -> dict:
    out = {}
    for s in SERIES:
        for day, h, k, pnl, vol in trades(s):
            if lo <= day < hi:
                c = out.setdefault((s, h, k), {"days": {}, "vol": []})
                c["days"].setdefault(day, []).append(pnl); c["vol"].append(vol)
    return out


def stats(c: dict) -> dict:
    days = sorted(c["days"]); daily = np.array([np.mean(c["days"][d]) for d in days])
    months = {}
    for d, v in zip(days, daily):
        months.setdefault((d.year, d.month), []).append(v)
    return {"days": len(days), "contracts": int(sum(len(v) for v in c["days"].values())), "mean_net": float(daily.mean()) if len(daily) else float("nan"),
            "t": _t(daily), "t_monthly": _t([np.sum(v) for v in months.values()]), "median_hour_volume": float(np.median(c["vol"])) if c["vol"] else 0.0,
            "first": str(days[0]) if days else None, "last": str(days[-1]) if days else None}


def scan() -> dict:
    C = cells(dt.date(2000, 1, 1), DISC_END); res = []
    for s in SERIES:
        for h in HOURS:
            for k, (lo, hi) in enumerate(BUCKETS):
                r = {"series": s, "hour": h, "bucket": f"{lo*100:.0f}-{hi*100:.0f}c", **(stats(C[(s, h, k)]) if (s, h, k) in C else {"days": 0})}
                r["carried"] = bool(r["days"] > 30 and r["t"] > 1.96 and r["mean_net"] > 0 and r["t_monthly"] > 1.96)
                res.append(r)
                if r["days"]:
                    print(f"  {s:11} {h:2}:00 {r['bucket']:7} days {r['days']:4} contracts {r['contracts']:5} net {r['mean_net']*100:+6.2f}c t {r['t']:+5.2f} "
                          f"(monthly {r['t_monthly']:+5.2f}) vol {r['median_hour_volume']:,.0f} {r['first']}..{r['last']}{'  CARRIED' if r['carried'] else ''}", flush=True)
                else:
                    print(f"  {s:11} {h:2}:00 {r['bucket']:7} no data", flush=True)
    carried = sorted([r for r in res if r["carried"]], key=lambda r: -r["t"])[:5]
    OUT.write_text(json.dumps({"discovery_end": str(DISC_END), "tests": len(res), "all": res, "carried": carried}, indent=1) + "\n")
    print(f"{len(carried)} carried of {len(res)} (≈ {0.025 * len(res):.1f} expected by chance one-sided)", flush=True)
    return res


#: 1b (decisions.md 666): the cells tested once on the sealed window, buying YES
CELLS_1B = (("KXNASDAQ100", 10, 0), ("KXNASDAQ100", 10, 2), ("KXNASDAQ100", 12, 2), ("KXNASDAQ100", 12, 0))
PRIOR_SD = 0.02                                      # zero-mean prior on the mean net per contract: 2 cents


def validate_1b() -> dict:
    lo, hi = VAL; out = []
    rows = {}
    for day, h, k, pnl, vol in trades("KXNASDAQ100", side="yes"):
        if lo <= day <= hi:
            rows.setdefault((h, k), {}).setdefault(day, []).append(pnl)
    rng = np.random.default_rng(664)
    for s_, h, k in CELLS_1B:
        dd = rows.get((h, k), {}); days = sorted(dd); x = np.array([np.mean(dd[d]) for d in days])
        n = len(x); t = _t(x); m = float(x.mean()) if n else float("nan")
        null = np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) if n else np.array([0.0])
        pct = float((null < m).mean() * 100); se2 = x.var(ddof=1) / n if n > 2 else float("nan")
        post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + se2)            # zero-mean prior; the flat-prior posterior mean is m
        dec = "CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
        r = {"series": s_, "hour": h, "bucket": f"{BUCKETS[k][0]*100:.0f}-{BUCKETS[k][1]*100:.0f}c", "days": n,
             "contracts": int(sum(len(v) for v in dd.values())), "mean_net": m, "t": t, "placebo_pct": pct, "posterior_zero_prior": post0, "decision": dec}
        out.append(r)
        print(f"  1b {s_} {h}:00 {r['bucket']}: days {n} contracts {r['contracts']} net {m*100:+.2f}c t {t:+.2f} placebo {pct:.0f}% "
              f"posterior(0-prior) {post0*100:+.2f}c -> {dec}", flush=True)
    (ROOT / "reports" / "k1b_validation.json").write_text(json.dumps({"window": [str(lo), str(hi)], "cells": out}, indent=1) + "\n")
    return {"cells": out}


if __name__ == "__main__":
    if "--validate-1b" in sys.argv:
        validate_1b()
    elif "--validate" in sys.argv:
        raise SystemExit("family 1 carried nothing (decisions.md 665); its validation does not run")
    else:
        scan()
