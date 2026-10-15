"""D-series family 169 - walk-forward re-selection: do recently strong cross-market rules persist one more year? (decisions.md 592)

    python -m futuresres.reporting.d169_walkforward
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d136_goldwin as d136
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d169_walkforward.json"
YEARS = range(2013, 2027)
TARGETS = d111.TARGETS
PRED = d111.OC + d111.CC + d111.FRED + d111.FX


def matrices(tg: str):
    """dates, y, X (cells x dates: the predictor value or NaN), cell names."""
    Y = d111.target(tg); ds = sorted(d for d in Y if d.year >= 2010); y = np.array([Y[d] for d in ds])
    names, rows = [], []
    for p in PRED:
        if not d111.eligible(p, tg):
            continue
        for h in (1, 5):
            S = d136.series(p, h)
            rows.append([S.get(d3.prev_weekday(d), np.nan) for d in ds]); names.append(f"{p}:{h}d")
    return np.array(ds), y, np.array(rows, float), names


def pick(X, y, mask, cost):
    """Best cell on the training mask: (row, form, direction, median) or None. Forms: all / strong (|x| > training median)."""
    best = None
    for f in ("all", "strong"):
        A = np.abs(X[:, mask]); med = np.nanmedian(A, axis=1)
        S = np.sign(X[:, mask]); S = np.nan_to_num(S)
        if f == "strong":
            S = np.where(A > med[:, None], S, 0.0)
        n = (S != 0).sum(1); g = (S * y[mask]).sum(1) / np.maximum(n, 1)
        d = np.where(g >= 0, 1.0, -1.0)
        net = d[:, None] * S * y[mask] - cost * (S != 0)
        mu = net.sum(1) / np.maximum(n, 1)
        var = ((net - mu[:, None]) ** 2 * (S != 0)).sum(1) / np.maximum(n - 1, 1)
        t = mu / np.sqrt(var / np.maximum(n, 1) + 1e-12)
        t[n < 100] = -9
        i = int(np.argmax(t))
        if t[i] > 2.0 and mu[i] > 0 and (best is None or t[i] > best[4]):
            best = (i, f, d[i], med[i], t[i])
    return best


def walk(shuffle_rng=None) -> dict:
    out = {}
    for tg, cost in TARGETS.items():
        ds, y, X, names = M[tg]; yrs = np.array([d.year for d in ds]); res = []
        for Y in YEARS:
            tr = (yrs >= Y - 3) & (yrs <= Y - 1); te = yrs == Y
            if not te.any():
                continue
            ytr = y.copy()
            if shuffle_rng is not None:
                idx = np.where(tr)[0]; ytr[idx] = y[rng_perm(shuffle_rng, idx)]
            b = pick(X, ytr, tr, cost)
            if b is None:
                res.append({"year": Y, "rule": None, "n": 0, "sum": 0.0}); continue
            i, f, dirn, med, tt = b; x = X[i, te]; s = np.nan_to_num(np.sign(x))
            if f == "strong":
                s = np.where(np.abs(x) > med, s, 0.0)
            net = (dirn * s * y[te] - cost)[s != 0]
            res.append({"year": Y, "rule": f"{names[i]} {f} {'follow' if dirn > 0 else 'fade'}", "train_t": float(tt), "n": int(len(net)),
                        "sum": float(net.sum()), "mean": float(net.mean()) if len(net) else 0.0, "net": net.tolist() if shuffle_rng is None else None})
        out[tg] = res
    return out


def rng_perm(rng, idx):
    return rng.permutation(idx)


def pooled(W: dict, lo: int = 2014, hi: int = 2026):
    x = np.concatenate([np.array(r["net"]) for tg in W for r in W[tg] if lo <= r["year"] <= hi and r["n"]] or [np.array([])])
    return x


def pooled_mean_fast(W: dict, lo=2014, hi=2026) -> float:
    n = sum(r["n"] for tg in W for r in W[tg] if lo <= r["year"] <= hi); s = sum(r["sum"] for tg in W for r in W[tg] if lo <= r["year"] <= hi)
    return s / n if n else 0.0


def main() -> int:
    global M
    M = {tg: matrices(tg) for tg in TARGETS}
    W = walk(); x = pooled(W)
    t = float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))
    by = {Y: float(np.mean(np.concatenate([np.array(r["net"]) for tg in W for r in W[tg] if r["year"] == Y and r["n"]] or [np.zeros(1)]))) for Y in YEARS}
    x2526 = pooled(W, 2025, 2026)
    rng = np.random.default_rng(592); draws = [pooled_mean_fast(walk(rng)) for _ in range(200)]
    pct = float((np.array(draws) < x.mean()).mean() * 100)
    pos_years = sum(1 for Y in range(2014, 2027) if by[Y] > 0)
    print(f"pooled OOS 2014-2026: n {len(x)} net {x.mean():+.2f} bps t {t:+.2f}; positive years {pos_years}/13; 2025-26 {x2526.mean():+.2f} "
          f"(n {len(x2526)}); placebo pct {pct:.0f}", flush=True)
    for Y in YEARS:
        print(f"  {Y}: {by[Y]:+6.2f} | " + "; ".join(f"{tg} {next((r['rule'] or '-') for r in W[tg] if r['year'] == Y)}" for tg in W), flush=True)
    for tg in W:
        xs = np.concatenate([np.array(r["net"]) for r in W[tg] if r["year"] >= 2014 and r["n"]] or [np.zeros(1)])
        print(f"  {tg}: OOS n {len(xs)} net {xs.mean():+.2f} t {xs.mean() / (xs.std(ddof=1) / math.sqrt(len(xs))) if len(xs) > 2 else float('nan'):+.2f}", flush=True)
    OUT.write_text(json.dumps({"pooled": {"n": len(x), "net": float(x.mean()), "t": t, "positive_years": pos_years, "net_2025_26": float(x2526.mean()),
                                          "placebo_pct": pct}, "by_year": by,
                               "rules": {tg: [{k: v for k, v in r.items() if k != "net"} for r in W[tg]] for tg in W}}, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
