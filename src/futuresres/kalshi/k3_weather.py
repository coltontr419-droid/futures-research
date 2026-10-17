"""K-series family 3 - Kalshi daily-high temperature contracts priced by the National Blend of Models (decisions.md 672).

    python -m futuresres.kalshi.k3_weather             (discovery: before 2025-07-01)
    python -m futuresres.kalshi.k3_weather --validate  (once, sealed 2025-07-01 -> 2026-10-16, the carried cells only)
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
OUT = ROOT / "reports" / "k3_discovery.json"
DISC_END = dt.date(2025, 7, 1)
VAL = (dt.date(2025, 7, 1), dt.date(2026, 10, 16))
CITY = {"KXHIGHNY": "KNYC", "KXHIGHCHI": "KMDW", "KXHIGHMIA": "KMIA", "KXHIGHAUS": "KAUS", "KXHIGHLAX": "KLAX", "KXHIGHDEN": "KDEN", "KXHIGHPHIL": "KPHL"}
TIMES = {"T1": -1, "T2": 0}                    # decision day relative to the settlement day; 10:00 New York; that day's 07Z run
THETAS = (0.05, 0.10)
VARIANTS = ("raw", "calibrated")


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


RUN_HOUR = {"T1": 7, "T2": 7}
DEC_HOUR = {"T1": 10, "T2": 10}


def nbm(station: str, run_hour: int = 7) -> dict:
    """(run date, local day D) -> (txn, xnd) from the run at run_hour Z, forecast valid D+1 00Z."""
    out = {}
    with (DATA / "nbm" / f"{station}.csv").open() as fh:
        for r in csv.DictReader(fh):
            rt = dt.datetime.fromisoformat(r["runtime"]); ft = dt.datetime.fromisoformat(r["ftime"])
            if rt.hour != run_hour or ft.hour != 0:
                continue
            try:
                out[(rt.date(), ft.date() - dt.timedelta(days=1))] = (float(r["txn"]), float(r["xnd"]) if r["xnd"] else float("nan"))
            except ValueError:
                continue
    return out


def event_day(ev: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(ev.split("-")[1], "%y%b%d").date()
    except ValueError:
        return None


def bounds(m: dict):
    st, lo, hi = m.get("strike_type"), m.get("floor_strike"), m.get("cap_strike")
    if st == "between" and lo is not None and hi is not None:
        return float(lo), float(hi)
    if st == "greater" and lo is not None:
        return float(lo) + 1, math.inf
    if st == "less" and hi is not None:
        return -math.inf, float(hi) - 1
    return None


def prob(b, mu, sd) -> float:
    lo, hi = b
    up = 1.0 if hi == math.inf else _phi((hi + 0.5 - mu) / sd)
    dn = 0.0 if lo == -math.inf else _phi((lo - 0.5 - mu) / sd)
    return up - dn


def load_events(series: str):
    for f in sorted((DATA / series).glob("*.json")):
        ev = json.loads(f.read_text()); D = event_day(ev["event"])
        if D is None:
            continue
        obs = None
        for m in ev["markets"]:
            v = m.get("expiration_value")
            if v not in (None, ""):
                try:
                    obs = float(str(v).replace(",", "")); break
                except ValueError:
                    pass
        yield D, obs, ev["markets"]


def calibrate() -> dict:
    """Per (series, time): bias and SD scale from discovery days only."""
    cal = {}
    for s, stn in CITY.items():
        for tn, off in TIMES.items():
            F = nbm(stn, RUN_HOUR[tn]); res, xs = [], []
            for D, obs, _ in load_events(s):
                if D >= DISC_END or obs is None:
                    continue
                fc = F.get((D + dt.timedelta(days=off), D))
                if fc and np.isfinite(fc[1]):
                    res.append(obs - fc[0]); xs.append(max(fc[1], 1.0))
            if len(res) > 30:
                cal[(s, tn)] = (float(np.mean(res)), float(np.std(res) / np.mean(xs)), len(res))
    return cal


def trades(lo: dt.date, hi: dt.date, cal: dict):
    """(day, series, time, variant, theta index, net P&L per contract)."""
    for s, stn in CITY.items():
        FF = {tn: nbm(stn, RUN_HOUR[tn]) for tn in TIMES}
        for D, obs, ms in load_events(s):
            if not (lo <= D < hi):
                continue
            for tn, off in TIMES.items():
                fc = FF[tn].get((D + dt.timedelta(days=off), D))
                if not fc or not np.isfinite(fc[1]):
                    continue
                ts = int(dt.datetime.combine(D + dt.timedelta(days=off), dt.time(DEC_HOUR[tn], 0), ET).timestamp())
                for m in ms:
                    b = bounds(m)
                    if b is None or m.get("result") not in ("yes", "no") or not m.get("candles"):
                        continue
                    c = next((x for x in m["candles"] if int(x["end_period_ts"]) == ts), None)
                    if c is None:
                        continue
                    bid, ask = _q(c, "yes_bid"), _q(c, "yes_ask")
                    if bid is None or ask is None or not (bid > 0 and ask < 1 and ask - bid <= 0.10):
                        continue
                    for v in VARIANTS:
                        if v == "raw":
                            mu, sd = fc[0], max(fc[1], 1.0)
                        elif (s, tn) in cal:
                            bias, sc, _ = cal[(s, tn)]; mu, sd = fc[0] + bias, max(fc[1], 1.0) * sc
                        else:
                            continue
                        p = prob(b, mu, sd); ey = p - ask - fee(ask); en = (1 - p) - (1 - bid) - fee(1 - bid)
                        for k, th in enumerate(THETAS):
                            if ey > th and ey >= en:
                                yield D, s, tn, v, k, (1.0 if m["result"] == "yes" else 0.0) - ask - fee(ask)
                            elif en > th:
                                yield D, s, tn, v, k, (1.0 if m["result"] == "no" else 0.0) - (1 - bid) - fee(1 - bid)


def stats(days: dict) -> dict:
    ds = sorted(days); x = np.array([np.mean(days[d]) for d in ds]); months = {}
    for d, v in zip(ds, x):
        months.setdefault((d.year, d.month), []).append(v)
    return {"days": len(ds), "contracts": int(sum(len(v) for v in days.values())), "mean_net": float(x.mean()) if len(x) else float("nan"),
            "t": _t(x), "t_monthly": _t([np.sum(v) for v in months.values()]), "first": str(ds[0]) if ds else None, "last": str(ds[-1]) if ds else None}


def scan() -> dict:
    cal = calibrate()
    for k_, v in sorted(cal.items()):
        print(f"  calibration {k_[0]:11} {k_[1]}: bias {v[0]:+.2f}F, SD scale {v[1]:.2f} ({v[2]} days)", flush=True)
    cells, city = {}, {}
    for D, s, tn, v, k, pnl in trades(dt.date(2000, 1, 1), DISC_END, cal):
        cells.setdefault((tn, v, k), {}).setdefault(D, []).append(pnl)
        city.setdefault((tn, v, k, s), []).append(pnl)
    res = []
    for tn in TIMES:
        for v in VARIANTS:
            for k, th in enumerate(THETAS):
                r = {"time": tn, "variant": v, "theta": th, **(stats(cells[(tn, v, k)]) if (tn, v, k) in cells else {"days": 0})}
                r["by_city"] = {s: {"n": len(city.get((tn, v, k, s), [])), "mean_net": float(np.mean(city[(tn, v, k, s)])) if city.get((tn, v, k, s)) else None} for s in CITY}
                r["carried"] = bool(r["days"] > 30 and r["t"] > 1.96 and r["mean_net"] > 0 and r["t_monthly"] > 1.96); res.append(r)
                print(f"  {tn} {v:10} theta {th*100:.0f}c days {r['days']:4} contracts {r.get('contracts', 0):6} net {r.get('mean_net', float('nan'))*100:+6.2f}c "
                      f"t {r.get('t', float('nan')):+5.2f} (monthly {r.get('t_monthly', float('nan')):+5.2f}) {r.get('first')}..{r.get('last')}{'  CARRIED' if r['carried'] else ''}", flush=True)
                print("      " + " ".join(f"{s[6:]} {x['mean_net']*100:+.1f}c/{x['n']}" for s, x in r["by_city"].items() if x["n"]), flush=True)
    carried = sorted([r for r in res if r["carried"]], key=lambda r: -r["t"])[:5]
    OUT.write_text(json.dumps({"discovery_end": str(DISC_END), "tests": len(res), "calibration": {f"{a}|{b}": v for (a, b), v in cal.items()},
                               "all": res, "carried": carried}, indent=1) + "\n")
    print(f"{len(carried)} carried of {len(res)}", flush=True)
    return res


if __name__ == "__main__":
    if "--3b" in sys.argv:                      # decisions.md 674: the day before at 14:00 New York with the 13Z run
        TIMES.clear(); TIMES["T1b"] = -1; RUN_HOUR["T1b"] = 13; DEC_HOUR["T1b"] = 14
        OUT = ROOT / "reports" / "k3b_discovery.json"
        scan(); sys.exit(0)
    if "--validate" in sys.argv:
        raise SystemExit("validation runs once, after the discovery result is recorded (decisions.md 672)")
    scan()


def validate(cells: list[tuple[str, str, int]], tag: str) -> list[dict]:
    """Once, on the sealed window: each carried (time, variant, theta index) cell; §664.4's rule; trials logged by the caller."""
    cal = calibrate(); lo, hi = VAL; rows = {}; city = {}
    for D, s, tn, v, k, pnl in trades(lo, hi + dt.timedelta(days=1), cal):
        rows.setdefault((tn, v, k), {}).setdefault(D, []).append(pnl); city.setdefault((tn, v, k, s), []).append(pnl)
    rng = np.random.default_rng(672); out = []
    for tn, v, k in cells:
        dd = rows.get((tn, v, k), {}); ds = sorted(dd); x = np.array([np.mean(dd[d]) for d in ds]); n = len(x)
        m = float(x.mean()); t = _t(x)
        null = np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]); pct = float((null < m).mean() * 100)
        se2 = x.var(ddof=1) / n; post0 = m * 0.02 ** 2 / (0.02 ** 2 + se2)
        dec = "CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
        months = {}
        for d, val in zip(ds, x):
            months.setdefault((d.year, d.month), []).append(val)
        r = {"time": tn, "variant": v, "theta": THETAS[k], "days": n, "contracts": int(sum(len(a) for a in dd.values())), "mean_net": m, "t": t,
             "placebo_pct": pct, "posterior_zero_prior": post0, "decision": dec, "months_positive": int(sum(np.sum(a) > 0 for a in months.values())),
             "months": len(months), "by_city": {s: (float(np.mean(city[(tn, v, k, s)])), len(city[(tn, v, k, s)])) for s in CITY if city.get((tn, v, k, s))}}
        out.append(r)
        print(f"  {tag} {tn} {v} theta {THETAS[k]*100:.0f}c: days {n} contracts {r['contracts']} net {m*100:+.2f}c t {t:+.2f} placebo {pct:.0f}% "
              f"post0 {post0*100:+.2f}c months + {r['months_positive']}/{r['months']} -> {dec}", flush=True)
        print("      " + " ".join(f"{s[6:]} {a*100:+.1f}c/{b}" for s, (a, b) in r["by_city"].items()), flush=True)
    (ROOT / "reports" / f"{tag}_validation.json").write_text(json.dumps({"window": [str(lo), str(hi)], "cells": out}, indent=1) + "\n")
    return out
