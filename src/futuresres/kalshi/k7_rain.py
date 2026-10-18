"""K-series family 7 (decisions.md 716): Kalshi daily rain in ~35 cities priced by the NBM's PoP12.

    python -m futuresres.kalshi.k7_rain fetch      (stations from the market rules; NBM PoP12 from the IEM archive)
    python -m futuresres.kalshi.k7_rain            (discovery: 2026-07-15 -> 2026-09-12)
    python -m futuresres.kalshi.k7_rain --validate (once, sealed 2026-09-13 -> 2026-10-17)
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

from futuresres.kalshi.k1_longshot import DATA, ET, _q, _t, fee

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "k7_discovery.json"
NBM = DATA / "nbm_pop"
DISC = (dt.date(2026, 7, 15), dt.date(2026, 9, 12))
VAL = (dt.date(2026, 9, 13), dt.date(2026, 10, 17))
# the 2026 archive's NBM text runs are at 00/06/12/18Z (not 01/07/13/19 as in 2021-25): the nearest earlier runs are used (decisions.md 716 note)
POINTS = {"D 10:00 (06Z run)": (0, 10, 6), "D-1 14:00 (12Z run)": (-1, 14, 12)}
THETAS = (0.05, 0.10)
URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/mos.py?station={s}&model=NBS&sts={a}T00:00Z&ets={b}T00:00Z&format=csv"


def event_day(ev):
    return dt.datetime.strptime(ev.split("-")[1][:7], "%y%b%d").date()


# stations from the markets' rules (CLIxxx); West Palm Beach settles on "DJT" (Palm Beach International, renamed) = KPBI in the NBM archive
STATIONS = {k: ("KPBI" if v == "KDJT" else v) for k, v in json.loads((DATA / "rain_stations.json").read_text()).items()}


def markets():
    """(day, city code, station, market dict)."""
    for f in sorted((DATA / "KXRAIN").glob("*.json")):
        ev = json.loads(f.read_text()); D = event_day(ev["event"])
        for m in ev["markets"]:
            code = m["ticker"].split("-")[-1]
            if STATIONS.get(code):
                yield D, code, STATIONS[code], m


def fetch() -> None:
    NBM.mkdir(parents=True, exist_ok=True)
    stations = sorted(set(STATIONS.values()))
    print(len(stations), "stations", stations, flush=True)
    for s in stations:
        f = NBM / f"{s}.csv"
        if f.exists():
            continue
        rows = []
        a = dt.date(2026, 7, 10)
        while a < dt.date(2026, 10, 19):
            b = min(a + dt.timedelta(days=30), dt.date(2026, 10, 19))
            txt = ""
            for k in range(8):                               # the archive rate-limits: back off when told to slow down
                try:
                    txt = urllib.request.urlopen(urllib.request.Request(URL.format(s=s, a=a, b=b), headers={"User-Agent": "futures-research"}), timeout=180).read().decode()
                except Exception:
                    txt = ""
                if txt.startswith("runtime"):
                    break
                time.sleep(60 * (k + 1))
            time.sleep(10)
            for r in csv.DictReader(io.StringIO(txt)):
                if r.get("p12") not in (None, "") and r["runtime"][11:13] in ("06", "12"):
                    rows.append((r["runtime"], r["ftime"], r["p12"]))
            a = b
        if not rows:
            print(s, "NO ROWS - not saved", flush=True); continue
        with f.open("w", newline="") as fh:
            w = csv.writer(fh); w.writerow(["runtime", "ftime", "p12"]); w.writerows(rows)
        print(s, len(rows), "rows", flush=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["fetch"]:
        fetch()


def pops() -> dict:
    """station -> {(run datetime, valid datetime): PoP12 as a fraction}."""
    out = {}
    for f in NBM.glob("*.csv"):
        d = {}
        for r in csv.DictReader(open(f)):
            try:
                d[(dt.datetime.fromisoformat(r["runtime"]), dt.datetime.fromisoformat(r["ftime"]))] = float(r["p12"]) / 100
            except ValueError:
                pass
        out[f.stem] = d
    return out


def features(P, station, D, off, run_h):
    """The three PoP12 values (periods ending D 12Z, D+1 00Z, D+1 12Z) from the run at run_h Z on D+off; None if any is missing."""
    d = P.get(station, {}); run = dt.datetime.combine(D + dt.timedelta(days=off), dt.time(run_h))
    ends = [dt.datetime.combine(D, dt.time(12)), dt.datetime.combine(D + dt.timedelta(days=1), dt.time(0)), dt.datetime.combine(D + dt.timedelta(days=1), dt.time(12))]
    v = [d.get((run, e)) for e in ends]
    return None if any(x is None for x in v) else v


def fit(X, y, iters=50):
    X = np.c_[np.ones(len(X)), np.asarray(X)]; y = np.asarray(y, float); w = np.zeros(X.shape[1])
    for _ in range(iters):                                   # Newton steps, lightly ridged
        p = 1 / (1 + np.exp(-X @ w)); W = p * (1 - p)
        H = X.T @ (X * W[:, None]) + 1e-3 * np.eye(X.shape[1]); g = X.T @ (y - p) - 1e-3 * w
        w = w + np.linalg.solve(H, g)
    return w


def prob(w, x):
    return float(1 / (1 + math.exp(-(w[0] + sum(a * b for a, b in zip(w[1:], x))))))


def rows(P, lo, hi):
    for D, code, station, m in markets():
        if lo <= D <= hi and m.get("result") in ("yes", "no"):
            yield D, code, station, m


def models(P):
    W = {}
    for name, (off, hh, run) in POINTS.items():
        X, y = [], []
        for D, code, station, m in rows(P, *DISC):
            f = features(P, station, D, off, run)
            if f:
                X.append(f); y.append(m["result"] == "yes")
        W[name] = (fit(X, y), len(y))
    return W


def trades(P, W, lo, hi):
    for D, code, station, m in rows(P, lo, hi):
        if not m.get("candles"):
            continue
        for name, (off, hh, run) in POINTS.items():
            f = features(P, station, D, off, run)
            if not f:
                continue
            p = prob(W[name][0], f)
            tsd = int(dt.datetime.combine(D + dt.timedelta(days=off), dt.time(hh, 0), ET).timestamp())
            c = next((x for x in m["candles"] if int(x["end_period_ts"]) == tsd), None)
            if c is None:
                continue
            bid, ask = _q(c, "yes_bid"), _q(c, "yes_ask")
            if bid is None or ask is None or not (bid > 0 and ask < 1 and ask - bid <= 0.10):
                continue
            ey = p - ask - fee(ask); en = (1 - p) - (1 - bid) - fee(1 - bid)
            for k, th in enumerate(THETAS):
                if ey > th and ey >= en:
                    yield D, name, k, (1.0 if m["result"] == "yes" else 0.0) - ask - fee(ask)
                elif en > th:
                    yield D, name, k, (1.0 if m["result"] == "no" else 0.0) - (1 - bid) - fee(1 - bid)


def stats(days):
    ds = sorted(days); x = np.array([np.mean(days[d]) for d in ds])
    return {"days": len(ds), "contracts": int(sum(len(v) for v in days.values())), "mean_net": float(x.mean()) if len(x) else float("nan"), "t": _t(x), "daily": x}


def scan():
    P = pops(); W = models(P)
    for k, (w, n) in W.items():
        print(f"  model {k}: weights {np.round(w, 2).tolist()} on {n} discovery market-days", flush=True)
    cells = {}
    for D, name, k, pnl in trades(P, W, *DISC):
        cells.setdefault((name, k), {}).setdefault(D, []).append(pnl)
    res = []
    for name in POINTS:
        for k, th in enumerate(THETAS):
            r = {"point": name, "theta": th, **(stats(cells[(name, k)]) if (name, k) in cells else {"days": 0})}; r.pop("daily", None)
            r["carried"] = bool(r["days"] > 30 and r["t"] > 1.96 and r["mean_net"] > 0); res.append(r)
            print(f"  {name:20} theta {th*100:.0f}c days {r['days']:3} contracts {r.get('contracts', 0):5} net {r.get('mean_net', float('nan'))*100:+6.2f}c "
                  f"t {r.get('t', float('nan')):+5.2f}{'  CARRIED' if r['carried'] else ''}", flush=True)
    OUT.write_text(json.dumps({"tests": len(res), "all": res, "carried": [r for r in res if r["carried"]],
                               "weights": {k: w.tolist() for k, (w, n) in W.items()}}, indent=1) + "\n")
    print(f"{sum(r['carried'] for r in res)} carried of {len(res)}", flush=True)


def validate():
    P = pops(); W = models(P); car = json.loads(OUT.read_text())["carried"]; rng = np.random.default_rng(716); out = []
    rowsv = {}
    for D, name, k, pnl in trades(P, W, *VAL):
        rowsv.setdefault((name, k), {}).setdefault(D, []).append(pnl)
    for r in car:
        k = THETAS.index(r["theta"]); st = stats(rowsv.get((r["point"], k), {})); x = st.pop("daily"); n = len(x); m = st["mean_net"]
        null = np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]); pct = float((null < m).mean() * 100)
        post0 = m * 0.02 ** 2 / (0.02 ** 2 + x.var(ddof=1) / n)
        dec = "CONFIRM" if (st["t"] > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
        out.append({"point": r["point"], "theta": r["theta"], **st, "placebo_pct": pct, "decision": dec})
        print(f"  sealed {r['point']} theta {r['theta']*100:.0f}c: days {n} net {m*100:+.2f}c t {st['t']:+.2f} placebo {pct:.0f}% -> {dec}", flush=True)
    (ROOT / "reports" / "k7_validation.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__" and sys.argv[1:2] != ["fetch"]:
    validate() if "--validate" in sys.argv else scan()
