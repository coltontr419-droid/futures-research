"""K-series family 4 - Kalshi US gas-price contracts priced by the wholesale-to-retail lag (decisions.md 678).

    python -m futuresres.kalshi.k4_gas             (fit on EIA 2010-22; discovery before 2025-07-01)
    python -m futuresres.kalshi.k4_gas --validate  (once, sealed 2025-07-01 -> 2026-10-16, the carried cells only)
"""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.a22_more_markets as a22
from futuresres.kalshi.k1_longshot import DATA, ET, _q, _t, fee

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "k4_discovery.json"
DISC_END = dt.date(2025, 7, 1)
VAL = (dt.date(2025, 7, 1), dt.date(2026, 10, 16))
FIT = (dt.date(2010, 1, 1), dt.date(2022, 12, 31))
POINTS = {("KXAAAGASW", 6): "weekly D-6", ("KXAAAGASW", 3): "weekly D-3", ("KXAAAGASM", 14): "monthly D-14", ("KXAAAGASD", 1): "daily D-1"}
THETAS = (0.05, 0.10)


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


class Gas:
    def __init__(self) -> None:
        z = a22.load("RB=F", "1d")
        self.rb_d = [t.date() for t in z["ts"].to_list()]; self.rb_v = z["c"].to_list()
        rows = list(csv.DictReader(open(DATA / "gas" / "eia_gas_weekly.csv")))
        self.eia = [(dt.date.fromisoformat(r["date"][:10]), float(r["retail"])) for r in rows]
        self.aaa = aaa_levels()
        self.fit()

    def rb(self, d: dt.date) -> float:
        """RBOB close on the last trading day strictly before d (known at noon on d)."""
        i = bisect.bisect_left(self.rb_d, d) - 1
        return float(self.rb_v[i]) if i >= 0 else float("nan")

    def x(self, t: dt.date, retail: float, margin: float) -> list[float]:
        dr = [self.rb(t - dt.timedelta(days=7 * k)) - self.rb(t - dt.timedelta(days=7 * (k + 1))) for k in range(3)]
        out = [1.0]
        for v in dr:
            out += [max(v, 0.0), min(v, 0.0)]
        return out + [retail - self.rb(t) - margin]

    def margin(self, i: int) -> float:
        """Trailing 52-week mean of EIA retail - RBOB up to week i (exclusive)."""
        lo = max(0, i - 52); v = [r - self.rb(d) for d, r in self.eia[lo:i]]
        v = [a for a in v if np.isfinite(a)]
        return float(np.mean(v)) if len(v) >= 26 else float("nan")

    def fit(self) -> None:
        X, y = [], []
        for i in range(53, len(self.eia) - 1):
            d, r = self.eia[i]
            if not (FIT[0] <= d <= FIT[1]):
                continue
            row = self.x(d, r, self.margin(i))
            if all(np.isfinite(row)):
                X.append(row); y.append(self.eia[i + 1][1] - r)
        X, y = np.array(X), np.array(y)
        self.beta, *_ = np.linalg.lstsq(X, y, rcond=None); res = y - X @ self.beta
        self.sigma = float(res.std(ddof=X.shape[1])); self.n_fit = len(y)

    def weekly_mean(self, t: dt.date) -> float:
        """Predicted 1-week change in retail from day t: the EIA gap term uses the latest EIA week before t."""
        j = bisect.bisect_left([d for d, _ in self.eia], t) - 1
        if j < 53:
            return float("nan")
        row = self.x(t, self.eia[j][1], self.margin(j))
        return float(np.dot(self.beta, row)) if all(np.isfinite(row)) else float("nan")

    def level(self, t: dt.date) -> float:
        ks = [d for d in self.aaa if d <= t]
        return self.aaa[max(ks)] if ks and (t - max(ks)).days <= 4 else float("nan")


def aaa_levels() -> dict:
    out = {}
    for s in ("KXAAAGASD", "KXAAAGASW", "KXAAAGASM"):
        for f in (DATA / s).glob("*.json"):
            ev = json.loads(f.read_text()); D = event_day(ev["event"])
            for m in ev["markets"]:
                v = m.get("expiration_value")
                if D and v not in (None, ""):
                    try:
                        out[D] = float(str(v).replace("$", "").replace(",", "")); break
                    except ValueError:
                        pass
    return out


def event_day(ev: str):
    for part in ev.split("-")[1:]:
        try:
            return dt.datetime.strptime(part, "%y%b%d").date()
        except ValueError:
            continue
    return None


def daily_fit(G: Gas):
    """phi and sigma_d for the daily model, on discovery days only."""
    ds = sorted(d for d in G.aaa if d < DISC_END); X, y = [], []
    for a, b, c in zip(ds, ds[1:], ds[2:]):
        if (b - a).days == 1 and (c - b).days == 1:
            w = G.weekly_mean(c)
            if np.isfinite(w):
                X.append((G.aaa[b] - G.aaa[a], w / 7)); y.append(G.aaa[c] - G.aaa[b])
    X, y = np.array(X), np.array(y)
    d1 = X[:, 0] - X[:, 1]; phi = float(np.clip(np.dot(d1, y - X[:, 1]) / np.dot(d1, d1), 0, 1))
    res = y - (phi * X[:, 0] + (1 - phi) * X[:, 1])
    return phi, float(res.std()), len(y)


def trades(G: Gas, dfit, lo: dt.date, hi: dt.date):
    phi, sd_d, _ = dfit
    for (s, k), name in POINTS.items():
        for f in sorted((DATA / s).glob("*.json")):
            ev = json.loads(f.read_text()); D = event_day(ev["event"])
            if D is None or not (lo <= D < hi):
                continue
            t = D - dt.timedelta(days=k); L0 = G.level(t); w = G.weekly_mean(t)
            if not (np.isfinite(L0) and np.isfinite(w)):
                continue
            if s == "KXAAAGASD":
                prev = G.aaa.get(t - dt.timedelta(days=1))
                if prev is None:
                    continue
                mu = L0 + phi * (L0 - prev) + (1 - phi) * w / 7; sd = sd_d
            else:
                mu = L0 + w * k / 7; sd = G.sigma * math.sqrt(k / 7)
            ts = int(dt.datetime.combine(t, dt.time(12, 0), ET).timestamp())
            for m in ev["markets"]:
                K = m.get("floor_strike")
                if m.get("strike_type") != "greater" or K is None or m.get("result") not in ("yes", "no") or not m.get("candles"):
                    continue
                c = next((x for x in m["candles"] if int(x["end_period_ts"]) == ts), None)
                if c is None:
                    continue
                bid, ask = _q(c, "yes_bid"), _q(c, "yes_ask")
                if bid is None or ask is None or not (bid > 0 and ask < 1 and ask - bid <= 0.10):
                    continue
                p = 1 - _phi((float(K) - mu) / sd); ey = p - ask - fee(ask); en = (1 - p) - (1 - bid) - fee(1 - bid)
                for j, th in enumerate(THETAS):
                    if ey > th and ey >= en:
                        yield D, name, j, (1.0 if m["result"] == "yes" else 0.0) - ask - fee(ask)
                    elif en > th:
                        yield D, name, j, (1.0 if m["result"] == "no" else 0.0) - (1 - bid) - fee(1 - bid)


def stats(days: dict) -> dict:
    ds = sorted(days); x = np.array([np.mean(days[d]) for d in ds]); months = {}
    for d, v in zip(ds, x):
        months.setdefault((d.year, d.month), []).append(v)
    return {"days": len(ds), "contracts": int(sum(len(v) for v in days.values())), "mean_net": float(x.mean()) if len(x) else float("nan"),
            "t": _t(x), "t_monthly": _t([np.sum(v) for v in months.values()]), "first": str(ds[0]) if ds else None, "last": str(ds[-1]) if ds else None}


def scan() -> dict:
    G = Gas(); dfit = daily_fit(G)
    print(f"  weekly model on EIA 2010-22 ({G.n_fit} weeks): beta {np.round(G.beta, 3).tolist()}, sigma {G.sigma*100:.2f}c a week", flush=True)
    print(f"  daily model (discovery days {dfit[2]}): phi {dfit[0]:.2f}, sigma {dfit[1]*100:.2f}c a day; AAA days known {len(G.aaa)}", flush=True)
    cells = {}
    for D, name, j, pnl in trades(G, dfit, dt.date(2000, 1, 1), DISC_END):
        cells.setdefault((name, j), {}).setdefault(D, []).append(pnl)
    res = []
    for name in POINTS.values():
        for j, th in enumerate(THETAS):
            r = {"point": name, "theta": th, **(stats(cells[(name, j)]) if (name, j) in cells else {"days": 0})}
            r["carried"] = bool(r["days"] > 30 and r["t"] > 1.96 and r["mean_net"] > 0 and r["t_monthly"] > 1.96); res.append(r)
            print(f"  {name:13} theta {th*100:.0f}c days {r['days']:4} contracts {r.get('contracts', 0):5} net {r.get('mean_net', float('nan'))*100:+6.2f}c "
                  f"t {r.get('t', float('nan')):+5.2f} (monthly {r.get('t_monthly', float('nan')):+5.2f}) {r.get('first')}..{r.get('last')}{'  CARRIED' if r['carried'] else ''}", flush=True)
    carried = sorted([r for r in res if r["carried"]], key=lambda r: -r["t"])[:5]
    OUT.write_text(json.dumps({"discovery_end": str(DISC_END), "tests": len(res), "beta": G.beta.tolist(), "sigma_week": G.sigma,
                               "daily": dfit, "all": res, "carried": carried}, indent=1) + "\n")
    print(f"{len(carried)} carried of {len(res)}", flush=True)
    return res


if __name__ == "__main__":
    if "--validate" in sys.argv:
        raise SystemExit("validation runs once, after the discovery result is recorded (decisions.md 678)")
    scan()
