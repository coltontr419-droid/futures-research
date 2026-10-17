"""K-series family 2 - S&P contracts priced by our own model against Kalshi's quotes (decisions.md 668).

    python -m futuresres.kalshi.k2_model             (discovery: before 2025-07-01)
    python -m futuresres.kalshi.k2_model --validate  (once, sealed 2025-07-01 -> 2026-09-30, the carried cells only)
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.hd_grid as hd
from futuresres.kalshi.k1_longshot import DATA, ET, _q, _t, fee

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "k2_discovery.json"
DISC_END = dt.date(2025, 7, 1)
VAL = (dt.date(2025, 7, 1), dt.date(2026, 9, 30))
SERIES = ("KXINXU", "KXINX")
HOURS = (10, 12, 14, 15)
THETAS = (0.03, 0.06)
PRIOR_SD = 0.02


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


class Model:
    def __init__(self) -> None:
        D, C = hd.load("spxusd"); self.C = C; self.ix = {d: i for i, d in enumerate(D)}; self.days = list(D)
        rv = np.full(len(D), np.nan)
        for i in range(len(D)):
            c = C[i, 570:960]; f = np.isfinite(c)
            if f.sum() > 300:
                lc = np.log(c[f]); rv[i] = float(np.sum(np.diff(lc) ** 2))
        self.rv = rv
        self.settle = settlements()

    def sigma(self, d: dt.date) -> float:
        i = self.ix.get(d)
        if i is None:
            return float("nan")
        prev = self.rv[max(0, i - 40):i]; prev = prev[np.isfinite(prev)][-20:]
        return float(math.sqrt(prev.mean())) if len(prev) >= 15 else float("nan")

    def level(self, d: dt.date, hh: int) -> float:
        """The CFD at hh:00 plus the previous settlement day's basis."""
        i = self.ix.get(d)
        if i is None:
            return float("nan")
        s = hd.at(self.C, i, hh * 60 - 1)
        prev = [x for x in self.settle if x < d]
        if not prev:
            return float("nan")
        p = max(prev); j = self.ix.get(p)
        if j is None or p < d - dt.timedelta(days=7):
            return float("nan")
        cfd = hd.at(self.C, j, 959)
        return s + (self.settle[p] - cfd)

    def prob(self, m: dict, d: dt.date, hh: int) -> float:
        S, sg = self.level(d, hh), self.sigma(d); tau = (960 - hh * 60) / 390
        if not (np.isfinite(S) and np.isfinite(sg)) or sg <= 0:
            return float("nan")
        def ge(x):
            return _phi(math.log(S / x) / (sg * math.sqrt(tau)))
        st, lo, hi = m.get("strike_type"), m.get("floor_strike"), m.get("cap_strike")
        if st in ("greater", "greater_or_equal") and lo:
            return ge(float(lo) + (0.01 if st == "greater" else 0.0))
        if st == "less" and hi:
            return 1 - ge(float(hi))
        if st == "between" and lo and hi:
            return ge(float(lo)) - ge(float(hi) + 0.01)
        return float("nan")


def settlements() -> dict:
    out = {}
    for s in SERIES:
        for f in (DATA / s).glob("*.json"):
            for m in json.loads(f.read_text())["markets"]:
                v = m.get("expiration_value")
                if v not in (None, ""):
                    d = dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(ET).date()
                    try:
                        out[d] = float(str(v).replace(",", ""))
                    except ValueError:
                        continue
    return out


def trades(M: Model, series: str, lo: dt.date, hi: dt.date):
    """(day, hour, theta index, net P&L per contract) for every contract the rule trades."""
    for f in sorted((DATA / series).glob("*.json")):
        for m in json.loads(f.read_text())["markets"]:
            if m.get("result") not in ("yes", "no") or not m.get("candles"):
                continue
            ct = dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(ET); day = ct.date()
            if not (lo <= day < hi) or (ct.hour, ct.minute) != (16, 0):
                continue
            by_end = {int(c["end_period_ts"]): c for c in m["candles"]}
            for hh in HOURS:
                c = by_end.get(int(dt.datetime.combine(day, dt.time(hh, 0), ET).timestamp()))
                if c is None:
                    continue
                bid, ask = _q(c, "yes_bid"), _q(c, "yes_ask")
                if bid is None or ask is None or not (bid > 0 and ask < 1 and ask - bid <= 0.10):
                    continue
                p = M.prob(m, day, hh)
                if not np.isfinite(p):
                    continue
                ey = p - ask - fee(ask); en = (1 - p) - (1 - bid) - fee(1 - bid)
                for k, th in enumerate(THETAS):
                    if ey > th and ey >= en:
                        yield day, hh, k, (1.0 if m["result"] == "yes" else 0.0) - ask - fee(ask)
                    elif en > th:
                        yield day, hh, k, (1.0 if m["result"] == "no" else 0.0) - (1 - bid) - fee(1 - bid)


def stats(days: dict) -> dict:
    ds = sorted(days); x = np.array([np.mean(days[d]) for d in ds]); months = {}
    for d, v in zip(ds, x):
        months.setdefault((d.year, d.month), []).append(v)
    return {"days": len(ds), "contracts": int(sum(len(v) for v in days.values())), "mean_net": float(x.mean()) if len(x) else float("nan"),
            "t": _t(x), "t_monthly": _t([np.sum(v) for v in months.values()]), "first": str(ds[0]) if ds else None, "last": str(ds[-1]) if ds else None}


def scan() -> dict:
    M = Model(); res = []
    for s in SERIES:
        cells = {}
        for day, hh, k, pnl in trades(M, s, dt.date(2000, 1, 1), DISC_END):
            cells.setdefault((hh, k), {}).setdefault(day, []).append(pnl)
        for hh in HOURS:
            for k, th in enumerate(THETAS):
                r = {"series": s, "hour": hh, "theta": th, **(stats(cells[(hh, k)]) if (hh, k) in cells else {"days": 0})}
                r["carried"] = bool(r["days"] > 30 and r["t"] > 1.96 and r["mean_net"] > 0 and r["t_monthly"] > 1.96); res.append(r)
                print(f"  {s:7} {hh:2}:00 theta {th*100:.0f}c days {r['days']:4} contracts {r.get('contracts', 0):5} net {r.get('mean_net', float('nan'))*100:+6.2f}c "
                      f"t {r.get('t', float('nan')):+5.2f} (monthly {r.get('t_monthly', float('nan')):+5.2f}) {r.get('first')}..{r.get('last')}{'  CARRIED' if r['carried'] else ''}", flush=True)
    carried = sorted([r for r in res if r["carried"]], key=lambda r: -r["t"])[:5]
    OUT.write_text(json.dumps({"discovery_end": str(DISC_END), "tests": len(res), "all": res, "carried": carried}, indent=1) + "\n")
    print(f"{len(carried)} carried of {len(res)}", flush=True)
    return res


if __name__ == "__main__":
    if "--validate" in sys.argv:
        raise SystemExit("validation runs once, after the discovery result is recorded (decisions.md 668)")
    scan()
