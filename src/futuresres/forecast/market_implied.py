"""§1044 / §1085: market-implied forecasts for price-threshold questions from live Yahoo option chains (Metaculus bot module).

    python -m futuresres.forecast.market_implied NVDA 250 2026-12-31            P(close > 250 on that date)
    python -m futuresres.forecast.market_implied ^SPX 7000 2026-12-31 --touch   P(touches 7000 at any time before then)
    python -m futuresres.forecast.market_implied ^SPX - 2026-12-31 --cdf        percentiles of the close on that date

P(S_T > K) is the risk-neutral digital: minus the slope of the call price in strike, from a smoothed implied-vol smile (OTM mids on
the parity forward), interpolated in total variance between the expiries around the date. A variance-premium factor c (fitted in F3)
scales the vol. Touch probabilities use the driftless reflection rule P(max > K) ≈ 2 P(S_T > K), capped at 1.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys

import numpy as np

from futuresres.options.smile import black, implied

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
C_FACTOR = 1.0          # variance-premium factor; set from reports/f3_threshold.json once F3 is read


class Yahoo:
    def __init__(self):
        from curl_cffi import requests                    # Yahoo answers 429 to plain urllib; a browser TLS fingerprint passes
        self.s = requests.Session(impersonate="chrome")
        try:
            self.s.get("https://fc.yahoo.com", timeout=20)  # answers 404 but sets the cookie the crumb needs
        except Exception:
            pass
        self.crumb = self.s.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=20).text

    def chain(self, sym: str, date: int | None = None) -> dict:
        q = {"crumb": self.crumb} | ({"date": date} if date else {})
        r = self.s.get(f"https://query2.finance.yahoo.com/v7/finance/options/{sym}", params=q, timeout=20)
        return r.json()["optionChain"]["result"][0]


def smile(res: dict, today: dt.date) -> dict | None:
    """Forward, T and a smoothed vol function for one expiry."""
    o = res["options"][0]; ex = dt.datetime.fromtimestamp(o["expirationDate"], dt.timezone.utc).date()
    T = max((ex - today).days, 0.5) / 365.0
    mid = lambda r: (r["bid"] + r["ask"]) / 2 if r.get("bid") and r.get("ask") and r["ask"] >= r["bid"] > 0 else None
    C = {r["strike"]: mid(r) for r in o["calls"]}; P = {r["strike"]: mid(r) for r in o["puts"]}
    both = [k for k in C if C[k] and P.get(k)]
    if len(both) < 3:
        return None
    k0 = min(both, key=lambda k: abs(C[k] - P[k])); F = k0 + C[k0] - P[k0]
    pts = []
    for K in sorted(set(C) | set(P)):
        p, cp = (C.get(K), "C") if K >= F else (P.get(K), "P")      # out-of-the-money side only
        v = implied(p, F, K, T, cp) if p else None
        if v and 0.02 < v < 3.0:
            pts.append((math.log(K / F), v))
    if len(pts) < 5:
        return None
    x = np.array([a for a, _ in pts]); y = np.array([b for _, b in pts])
    w = np.exp(-0.5 * (x / (0.25 + 2 * np.sqrt(T))) ** 2)              # weight the centre; tails still shape the fit
    deg = 4 if len(pts) >= 12 else 2
    coef = np.polyfit(x, y, deg, w=w)
    lo, hi = x.min(), x.max()
    def vol(K):
        k = min(max(math.log(K / F), lo), hi)                           # flat extrapolation beyond the quoted wings
        return float(max(np.polyval(coef, k), 0.02))
    return {"ex": ex, "T": T, "F": F, "vol": vol, "lo": F * math.exp(lo), "hi": F * math.exp(hi)}


def digital(s: dict, K: float, c: float = C_FACTOR) -> float:
    """Risk-neutral P(S_T > K) = -dC/dK on the smoothed smile (undiscounted, forward measure)."""
    h = K * 1e-3
    up, dn = K + h, K - h
    cu = black(s["F"], up, s["T"], c * s["vol"](up), "C"); cd = black(s["F"], dn, s["T"], c * s["vol"](dn), "C")
    return float(min(max(-(cu - cd) / (2 * h), 0.0), 1.0))


def surface(sym: str, target: dt.date, y: Yahoo | None = None) -> tuple[dict, dict | None, float]:
    """The expiries around the target date (b may be None when the date is past the last expiry)."""
    y = y or Yahoo(); today = dt.date.today()
    first = y.chain(sym); exps = sorted(first["expirationDates"])
    ds = [dt.datetime.fromtimestamp(e, dt.timezone.utc).date() for e in exps]
    after = [e for e, d in zip(exps, ds) if d >= target]; before = [e for e, d in zip(exps, ds) if today < d < target]
    a = smile(y.chain(sym, after[0]), today) if after else None
    b = smile(y.chain(sym, before[-1]), today) if before else None
    if a is None:
        a, b = b, None
    w = 1.0
    if a and b:                                           # total-variance interpolation weight toward the later expiry
        Tt = max((target - today).days, 0.5) / 365.0
        w = (Tt - b["T"]) / (a["T"] - b["T"])
    return a, b, w


def p_above(sym: str, K: float, target: dt.date, touch: bool = False, c: float = C_FACTOR, y: Yahoo | None = None) -> float:
    """P(close > K on the target date); with touch, P(the price reaches K at any time before then)."""
    a, b, w = surface(sym, target, y)
    Tt = max((target - dt.date.today()).days, 0.5) / 365.0
    if b is None:                                         # one expiry: keep its smile, re-scale to the target's horizon
        vol, F = (lambda k: a["vol"](k) * math.sqrt(a["T"] / Tt)), a["F"]
    else:                                                 # total variance blended per strike between the two expiries
        vol = lambda k: math.sqrt(max((1 - w) * b["vol"](k) ** 2 * b["T"] + w * a["vol"](k) ** 2 * a["T"], 1e-10) / Tt)
        F = b["F"] + w * (a["F"] - b["F"])
    p = digital({"F": F, "T": Tt, "vol": vol}, K, c)
    if touch:                                             # driftless reflection: P(touch) ~ 2 P(end beyond K)
        p = min(1.0, 2 * p) if K > F else min(1.0, 2 * (1 - p))
    return p


def cdf(sym: str, target: dt.date, qs=(0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99), c: float = C_FACTOR) -> dict:
    """Percentiles of the close on the target date (bisection on the digital)."""
    y = Yahoo(); out = {}
    a, b, w = surface(sym, target, y)
    base = (b or a)["F"]
    for q in qs:                                          # P(S_T > K) = 1 - q
        lo, hi = base * 0.2, base * 5
        for _ in range(40):
            m = math.sqrt(lo * hi)
            lo, hi = (m, hi) if p_above(sym, m, target, c=c, y=y) > 1 - q else (lo, m)
        out[q] = math.sqrt(lo * hi)
    return out


def main(argv=None) -> int:
    a = list(argv if argv is not None else sys.argv[1:])
    sym, K, date = a[0], a[1], dt.date.fromisoformat(a[2])
    if "--cdf" in a:
        for q, v in cdf(sym, date).items():
            print(f"  {q:>5.0%}: {v:,.2f}")
        return 0
    p = p_above(sym, float(K), date, touch="--touch" in a)
    print(f"{sym} {'touches' if '--touch' in a else 'closes above'} {float(K):,.2f} by/on {date}: {p:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
