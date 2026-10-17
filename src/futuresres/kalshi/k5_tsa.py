"""K-series family 5 - Kalshi weekly TSA screenings priced by a nowcast from the days already published (decisions.md 688).

    python -m futuresres.kalshi.k5_tsa             (discovery: weeks ending before 2025-07-01)
    python -m futuresres.kalshi.k5_tsa --validate  (once, sealed 2025-07-01 -> 2026-10-11, carried cells only)
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.k1_longshot import DATA, ET, _q, _t, fee

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "k5_discovery.json"
DISC_END = dt.date(2025, 7, 1)
VAL = (dt.date(2025, 7, 1), dt.date(2026, 10, 11))
POINTS = {"Tue (k=1)": 1, "Thu (k=3)": 3, "Sat (k=5)": 5}
THETAS = (0.05, 0.10)


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def tsa() -> dict:
    return {dt.date.fromisoformat(r["date"]): float(r["screened"]) for r in csv.DictReader(open(DATA / "tsa" / "tsa_daily.csv"))}


def nowcast(T: dict, end: dt.date, k: int):
    """(mu, known days) for the week ending `end` with its first k days known."""
    days = [end - dt.timedelta(days=6 - i) for i in range(7)]
    if any(d - dt.timedelta(days=364) not in T for d in days):
        return None
    known = days[:k]
    if k > 0:
        if any(d not in T for d in known):
            return None
        r = sum(T[d] for d in known) / sum(T[d - dt.timedelta(days=364)] for d in known)
    else:
        prev = [d - dt.timedelta(days=7) for d in days]
        if any(d not in T or d - dt.timedelta(days=364) not in T for d in prev):
            return None
        r = sum(T[d] for d in prev) / sum(T[d - dt.timedelta(days=364)] for d in prev)
    tot = sum(T[d] for d in known) + sum(T[d - dt.timedelta(days=364)] * r for d in days[k:])
    return tot / 7


def event_end(ev: str):
    try:
        return dt.datetime.strptime(ev.split("-")[1], "%y%b%d").date()
    except ValueError:
        return None


def sigmas(T: dict) -> dict:
    """sigma_k: SD of (actual - nowcast)/actual over discovery weeks (all Sundays with full data)."""
    out = {}
    for k in POINTS.values():
        e = []
        d = dt.date(2020, 1, 5)
        while d < DISC_END:
            mu = nowcast(T, d, k); days = [d - dt.timedelta(days=6 - i) for i in range(7)]
            if mu is not None and all(x in T for x in days):
                act = sum(T[x] for x in days) / 7; e.append((act - mu) / act)
            d += dt.timedelta(days=7)
        out[k] = (float(np.std(e)), len(e), float(np.mean(e)))
    return out


def trades(T, sg, lo, hi):
    for f in sorted((DATA / "KXTSAW").glob("*.json")):
        ev = json.loads(f.read_text()); E = event_end(ev["event"])
        if E is None or not (lo <= E < hi):
            continue
        for name, k in POINTS.items():
            mu = nowcast(T, E, k)
            if mu is None:
                continue
            dday = E - dt.timedelta(days=6 - k)                  # decision day: the (k+1)th day of the week, noon
            ts = int(dt.datetime.combine(dday, dt.time(12, 0), ET).timestamp()); sd = sg[k][0] * mu
            for m in ev["markets"]:
                X = m.get("floor_strike")
                if m.get("strike_type") != "greater" or X is None or m.get("result") not in ("yes", "no") or not m.get("candles"):
                    continue
                c = next((x for x in m["candles"] if int(x["end_period_ts"]) == ts), None)
                if c is None:
                    continue
                bid, ask = _q(c, "yes_bid"), _q(c, "yes_ask")
                if bid is None or ask is None or not (bid > 0 and ask < 1 and ask - bid <= 0.10):
                    continue
                p = 1 - _phi((float(X) - mu) / sd); ey = p - ask - fee(ask); en = (1 - p) - (1 - bid) - fee(1 - bid)
                for j, th in enumerate(THETAS):
                    if ey > th and ey >= en:
                        yield E, name, j, (1.0 if m["result"] == "yes" else 0.0) - ask - fee(ask)
                    elif en > th:
                        yield E, name, j, (1.0 if m["result"] == "no" else 0.0) - (1 - bid) - fee(1 - bid)


def stats(days: dict) -> dict:
    ds = sorted(days); x = np.array([np.mean(days[d]) for d in ds]); months = {}
    for d, v in zip(ds, x):
        months.setdefault((d.year, d.month), []).append(v)
    return {"weeks": len(ds), "contracts": int(sum(len(v) for v in days.values())), "mean_net": float(x.mean()) if len(x) else float("nan"),
            "t": _t(x), "t_monthly": _t([np.sum(v) for v in months.values()]), "first": str(ds[0]) if ds else None, "last": str(ds[-1]) if ds else None,
            "weekly": x}


def scan():
    T = tsa(); sg = sigmas(T)
    for k, v in sg.items():
        print(f"  nowcast error with {k} days known: SD {v[0]:.2%}, bias {v[2]:+.2%} ({v[1]} weeks)", flush=True)
    cells = {}
    for E, name, j, pnl in trades(T, sg, dt.date(2000, 1, 1), DISC_END):
        cells.setdefault((name, j), {}).setdefault(E, []).append(pnl)
    res = []
    for name in POINTS:
        for j, th in enumerate(THETAS):
            r = {"point": name, "theta": th, **(stats(cells[(name, j)]) if (name, j) in cells else {"weeks": 0})}
            r.pop("weekly", None)
            r["carried"] = bool(r["weeks"] > 30 and r["t"] > 1.96 and r["mean_net"] > 0 and r["t_monthly"] > 1.96); res.append(r)
            print(f"  {name:10} theta {th*100:.0f}c weeks {r['weeks']:4} contracts {r.get('contracts', 0):5} net {r.get('mean_net', float('nan'))*100:+6.2f}c "
                  f"t {r.get('t', float('nan')):+5.2f} (monthly {r.get('t_monthly', float('nan')):+5.2f}) {r.get('first')}..{r.get('last')}{'  CARRIED' if r['carried'] else ''}", flush=True)
    OUT.write_text(json.dumps({"discovery_end": str(DISC_END), "sigmas": {str(k): v for k, v in sg.items()}, "tests": len(res), "all": res,
                               "carried": [r for r in res if r["carried"]]}, indent=1) + "\n")
    print(f"{sum(r['carried'] for r in res)} carried of {len(res)}", flush=True)


def validate(cells_) -> list[dict]:
    T = tsa(); sg = sigmas(T); rows = {}
    for E, name, j, pnl in trades(T, sg, VAL[0], VAL[1] + dt.timedelta(days=1)):
        rows.setdefault((name, j), {}).setdefault(E, []).append(pnl)
    rng = np.random.default_rng(688); out = []
    for name, j in cells_:
        st = stats(rows.get((name, j), {})); x = st.pop("weekly"); n = len(x); m = st["mean_net"]
        null = np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]); pct = float((null < m).mean() * 100)
        post0 = m * 0.02 ** 2 / (0.02 ** 2 + x.var(ddof=1) / n)
        dec = "CONFIRM" if (st["t"] > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
        r = {"point": name, "theta": THETAS[j], **st, "placebo_pct": pct, "posterior_zero_prior": post0, "decision": dec}; out.append(r)
        print(f"  sealed {name} theta {THETAS[j]*100:.0f}c: weeks {n} contracts {st['contracts']} net {m*100:+.2f}c t {st['t']:+.2f} placebo {pct:.0f}% -> {dec}", flush=True)
    (ROOT / "reports" / "k5_validation.json").write_text(json.dumps({"window": [str(VAL[0]), str(VAL[1])], "cells": out}, indent=1) + "\n")
    return out


if __name__ == "__main__":
    if "--validate" in sys.argv:
        c = json.loads(OUT.read_text())["carried"]
        validate([(r["point"], THETAS.index(r["theta"])) for r in c])
    else:
        scan()
