"""§976: value an option leg at a snapshot where its strike is not listed — Black-76 on the parity forward, IV interpolated in strike.

Rows are normalised tuples (strike, cp, bid, ask, delta); delta may be None.
"""

from __future__ import annotations

import datetime as dt
import math


def _n(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black(F: float, K: float, T: float, s: float, cp: str) -> float:
    if T <= 0 or s <= 0:
        return max(F - K, 0.0) if cp == "C" else max(K - F, 0.0)
    d1 = (math.log(F / K) + 0.5 * s * s * T) / (s * math.sqrt(T)); d2 = d1 - s * math.sqrt(T)
    return F * _n(d1) - K * _n(d2) if cp == "C" else K * _n(-d2) - F * _n(-d1)


def implied(p: float, F: float, K: float, T: float, cp: str) -> float | None:
    if p <= (max(F - K, 0.0) if cp == "C" else max(K - F, 0.0)) + 1e-9 or T <= 0:
        return None
    lo, hi = 1e-4, 5.0
    if black(F, K, T, hi, cp) < p:
        return None
    for _ in range(60):
        m = 0.5 * (lo + hi)
        lo, hi = (m, hi) if black(F, K, T, m, cp) < p else (lo, m)
    return 0.5 * (lo + hi)


def forward(rows: list[tuple]) -> float | None:
    """F = K* + C* - P* at the strike with both quotes whose call delta is nearest 0.50 (or, without deltas, the smallest |C - P|)."""
    C = {r[0]: r for r in rows if r[1] == "C" and r[2] > 0 and r[3] > 0}; P = {r[0]: r for r in rows if r[1] == "P" and r[2] > 0 and r[3] > 0}
    ks = [k for k in C if k in P]
    if not ks:
        return None
    mid = lambda r: (r[2] + r[3]) / 2
    k = min(ks, key=lambda k: abs(C[k][4] - 0.5) if C[k][4] is not None else abs(mid(C[k]) - mid(P[k])))
    return k + mid(C[k]) - mid(P[k])


def leg(rows: list[tuple], k: float, cp: str, side: str, date: str, ex: str, F: float | None = None) -> float | None:
    """bid ('bid') or ask ('ask') for strike k: the listed quote if present, else the §976 model value; None if no IV is available."""
    r = next((r for r in rows if r[0] == k and r[1] == cp and r[2] > 0 and r[3] > 0), None)
    if r:
        return r[3] if side == "ask" else r[2]
    F = F if F else forward(rows)
    T = (dt.date.fromisoformat(ex) - dt.date.fromisoformat(date)).days / 365.0
    if not F or T <= 0:
        return None
    pts = []
    for q in rows:
        if q[1] == cp and q[2] > 0 and q[3] > 0:
            v = implied((q[2] + q[3]) / 2, F, q[0], T, cp)
            if v:
                pts.append((q[0], v, (q[3] - q[2]) / ((q[3] + q[2]) / 2)))
    if not pts:
        return None
    pts.sort()
    if k <= pts[0][0]:
        s, sp = pts[0][1], pts[0][2]
    elif k >= pts[-1][0]:
        s, sp = pts[-1][1], pts[-1][2]
    else:
        i = next(i for i in range(1, len(pts)) if pts[i][0] >= k); a, b = pts[i - 1], pts[i]
        w = (k - a[0]) / (b[0] - a[0]); s = a[1] + w * (b[1] - a[1]); sp = (a if w < 0.5 else b)[2]
    m = black(F, k, T, s, cp)
    return m * (1 + sp / 2) if side == "ask" else m * (1 - sp / 2)
