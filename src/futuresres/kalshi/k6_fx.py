"""K-series family 6 - Kalshi EUR/USD and USD/JPY 10:00 ranges priced by our own model (decisions.md 690).

    python -m futuresres.kalshi.k6_fx             (discovery before 2025-07-01)
    python -m futuresres.kalshi.k6_fx --validate  (once, sealed 2025-07-01 -> 2026-09-30, carried cells only)
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
OUT = ROOT / "reports" / "k6_discovery.json"
DISC_END = dt.date(2025, 7, 1)
VAL = (dt.date(2025, 7, 1), dt.date(2026, 9, 30))
PAIRS = {"KXEURUSD": "eurusd", "KXUSDJPY": "usdjpy"}
POINTS = {"D-1 12:00": (-1, 12), "D-1 16:00": (-1, 16), "D 08:00": (0, 8)}
THETAS = (0.03, 0.06)


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def event_day(ev: str):
    p = ev.split("-")[1]
    try:
        return dt.datetime.strptime(p[:7], "%y%b%d").date()
    except ValueError:
        return None


class FX:
    def __init__(self, series: str):
        D, C = hd.load(PAIRS[series]); self.C = C; self.ix = {d: i for i, d in enumerate(D)}
        rv = np.full(len(D), np.nan)
        for i in range(len(D)):
            c = C[i]; f = np.isfinite(c)
            if f.sum() > 1000:
                rv[i] = float(np.sum(np.diff(np.log(c[f])) ** 2))
        self.rv = rv; self.settle = {}
        for f in (DATA / series).glob("*.json"):
            ev = json.loads(f.read_text()); d = event_day(ev["event"])
            for m in ev["markets"]:
                v = m.get("expiration_value")
                if d and v not in (None, ""):
                    try:
                        self.settle[d] = float(str(v).replace(",", "")); break
                    except ValueError:
                        pass

    def sigma_day(self, d):
        i = self.ix.get(d)
        if i is None:
            return float("nan")
        p = self.rv[max(0, i - 40):i]; p = p[np.isfinite(p)][-20:]
        return float(math.sqrt(p.mean())) if len(p) >= 15 else float("nan")

    def level(self, d, minute):
        i = self.ix.get(d)
        if i is None:
            return float("nan")
        s = hd.at(self.C, i, minute - 1)
        prev = [x for x in self.settle if x < d]
        if not prev:
            return float("nan")
        p = max(prev); j = self.ix.get(p)
        if j is None or (d - p).days > 7:
            return float("nan")
        return s + (self.settle[p] - hd.at(self.C, j, 599))


def trades(series, M: FX, lo, hi):
    for f in sorted((DATA / series).glob("*.json")):
        ev = json.loads(f.read_text()); D = event_day(ev["event"])
        if D is None or not (lo <= D < hi):
            continue
        for name, (off, hh) in POINTS.items():
            dday = D + dt.timedelta(days=off)
            if dday.weekday() >= 5:
                continue
            S = M.level(dday, hh * 60); sg = M.sigma_day(D)
            hours = (D - dday).days * 24 + 10 - hh
            if not (np.isfinite(S) and np.isfinite(sg)) or hours <= 0:
                continue
            sd = sg * math.sqrt(hours / 24)
            ts = int(dt.datetime.combine(dday, dt.time(hh, 0), ET).timestamp())
            for m in ev["markets"]:
                if m.get("result") not in ("yes", "no") or not m.get("candles"):
                    continue
                st, lo_, hi_ = m.get("strike_type"), m.get("floor_strike"), m.get("cap_strike")
                ge = lambda x: _phi(math.log(S / x) / sd)
                if st == "between" and lo_ is not None and hi_ is not None:
                    p = ge(float(lo_)) - ge(float(hi_))
                elif st == "less" and hi_ is not None:
                    p = 1 - ge(float(hi_))
                elif st == "greater" and lo_ is not None:
                    p = ge(float(lo_))
                else:
                    continue
                c = next((x for x in m["candles"] if int(x["end_period_ts"]) == ts), None)
                if c is None:
                    continue
                bid, ask = _q(c, "yes_bid"), _q(c, "yes_ask")
                if bid is None or ask is None or not (bid > 0 and ask < 1 and ask - bid <= 0.10):
                    continue
                ey = p - ask - fee(ask); en = (1 - p) - (1 - bid) - fee(1 - bid)
                for j, th in enumerate(THETAS):
                    if ey > th and ey >= en:
                        yield D, name, j, (1.0 if m["result"] == "yes" else 0.0) - ask - fee(ask)
                    elif en > th:
                        yield D, name, j, (1.0 if m["result"] == "no" else 0.0) - (1 - bid) - fee(1 - bid)


def stats(days):
    ds = sorted(days); x = np.array([np.mean(days[d]) for d in ds]); months = {}
    for d, v in zip(ds, x):
        months.setdefault((d.year, d.month), []).append(v)
    return {"days": len(ds), "contracts": int(sum(len(v) for v in days.values())), "mean_net": float(x.mean()) if len(x) else float("nan"),
            "t": _t(x), "t_monthly": _t([np.sum(v) for v in months.values()]), "daily": x}


def scan():
    res = []
    for s in PAIRS:
        M = FX(s); cells = {}
        for D, name, j, pnl in trades(s, M, dt.date(2000, 1, 1), DISC_END):
            cells.setdefault((name, j), {}).setdefault(D, []).append(pnl)
        for name in POINTS:
            for j, th in enumerate(THETAS):
                r = {"series": s, "point": name, "theta": th, **(stats(cells[(name, j)]) if (name, j) in cells else {"days": 0})}
                r.pop("daily", None)
                r["carried"] = bool(r["days"] > 30 and r["t"] > 1.96 and r["mean_net"] > 0 and r["t_monthly"] > 1.96); res.append(r)
                print(f"  {s:9} {name:10} theta {th*100:.0f}c days {r['days']:4} contracts {r.get('contracts', 0):5} net {r.get('mean_net', float('nan'))*100:+6.2f}c "
                      f"t {r.get('t', float('nan')):+5.2f} (monthly {r.get('t_monthly', float('nan')):+5.2f}){'  CARRIED' if r['carried'] else ''}", flush=True)
    OUT.write_text(json.dumps({"discovery_end": str(DISC_END), "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}, indent=1) + "\n")
    print(f"{sum(r['carried'] for r in res)} carried of {len(res)}", flush=True)


def validate(cells_):
    rng = np.random.default_rng(690); out = []
    for s, name, th in cells_:
        M = FX(s); rows = {}; j = THETAS.index(th)
        for D, nm, jj, pnl in trades(s, M, VAL[0], VAL[1] + dt.timedelta(days=1)):
            if nm == name and jj == j:
                rows.setdefault(D, []).append(pnl)
        st = stats(rows); x = st.pop("daily"); n = len(x); m = st["mean_net"]
        null = np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]); pct = float((null < m).mean() * 100)
        post0 = m * 0.02 ** 2 / (0.02 ** 2 + x.var(ddof=1) / n)
        dec = "CONFIRM" if (st["t"] > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
        out.append({"series": s, "point": name, "theta": th, **st, "placebo_pct": pct, "decision": dec})
        print(f"  sealed {s} {name} theta {th*100:.0f}c: days {n} net {m*100:+.2f}c t {st['t']:+.2f} placebo {pct:.0f}% -> {dec}", flush=True)
    (ROOT / "reports" / "k6_validation.json").write_text(json.dumps({"window": [str(VAL[0]), str(VAL[1])], "cells": out}, indent=1) + "\n")
    return out


if __name__ == "__main__":
    if "--validate" in sys.argv:
        validate([(r["series"], r["point"], r["theta"]) for r in json.loads(OUT.read_text())["carried"]])
    else:
        scan()
