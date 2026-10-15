"""D-series family 145 - one wide ridge model per plan window, current regime (decisions.md 521). Fit on 2021-24 (penalty by
leave-one-year-out CV), frozen; validated once on sealed 2025-01 -> 2026-08.

    python -m futuresres.reporting.d145_ridge
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d136_goldwin as d136
import futuresres.reporting.d19_model as d19
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d145_discovery.json"
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
VAL = (dt.date(2025, 1, 1), dt.date(2026, 8, 31))
TARGETS = d111.TARGETS
LAMBDAS = (1.0, 10.0, 100.0, 1000.0, 10000.0)
_M: dict = {}


def feats(tg: str):
    names, cols = [], []
    for p in d111.OC + d111.CC + d111.FRED:
        if not d111.eligible(p, tg):
            continue
        for h in (1, 5):
            S = d136.series(p, h); m = float(np.median([abs(v) for d, v in S.items() if DISC[0] <= d <= DISC[1]]) or 1.0)
            names.append(f"{p}:{h}d"); cols.append((S, m))
    return names, cols


def design(tg: str, lo, hi):
    names, cols = feats(tg); Y = d111.target(tg); D, X, YY = [], [], []
    for d, y in sorted(Y.items()):
        if lo <= d <= hi:
            q = d3.prev_weekday(d)
            X.append([float(np.clip(S.get(q, 0.0) / m, -5, 5)) for S, m in cols]); D.append(d); YY.append(y)
    return np.array(D), np.array(X), np.array(YY), names


def fit(tg: str) -> dict:
    D, X, Y, names = design(tg, *DISC); cost = TARGETS[tg]; yrs = np.array([d.year for d in D]); cv = {}
    for lam in LAMBDAS:
        oof = np.zeros(len(Y))
        for yr in sorted(set(yrs)):
            tr = yrs != yr
            Zt, mu, sd = d19.standardise(X[tr]); b0, beta = d19.ridge(Zt, Y[tr], lam)
            Zv, _, _ = d19.standardise(X[~tr], mu, sd); oof[~tr] = b0 + Zv @ beta
        cv[lam] = (np.sign(oof) * Y - cost)
    best = max(cv, key=lambda k: d19.sharpe(cv[k]))
    Z, mu, sd = d19.standardise(X); b0, beta = d19.ridge(Z, Y, best); net = cv[best]
    return {"target": tg, "names": names, "lambda": best, "b0": float(b0), "beta": beta.tolist(), "mu": mu.tolist(), "sd": sd.tolist(),
            "cv_net_bps": float(net.mean()), "cv_t": float(net.mean() / (net.std(ddof=1) / math.sqrt(len(net)))), "train_days": int(len(Y))}


def model(tg: str) -> dict:
    if tg not in _M:
        _M[tg] = {m["target"]: m for m in json.loads(OUT.read_text())["carried"]}[tg]["model"]
    return _M[tg]


def rows(p: str, h: int, tg: str, form: str, lo, hi, med=None):
    """fam.run interface: dates, sign(prediction), y."""
    mdl = model(tg); D, X, Y, names = design(tg, lo, hi); assert names == mdl["names"]
    pred = mdl["b0"] + d19.standardise(X, np.array(mdl["mu"]), np.array(mdl["sd"]))[0] @ np.array(mdl["beta"])
    return D, np.sign(pred), Y, None


def scan() -> dict:
    carried = []
    for tg in TARGETS:
        mdl = fit(tg)
        top = sorted(zip(mdl["names"], mdl["beta"]), key=lambda z: -abs(z[1]))[:4]
        print(f"{tg}: lambda {mdl['lambda']:g}; leave-one-year-out net {mdl['cv_net_bps']:+.2f} bps (t {mdl['cv_t']:+.2f}); " + ", ".join(f"{n} {b:+.1f}" for n, b in top), flush=True)
        carried.append({"target": tg, "predictor": "ridge", "h": 0, "form": "model", "dir": "follow", "median_abs": None,
                        "net_bps": mdl["cv_net_bps"], "t": mdl["cv_t"], "n": mdl["train_days"], "context_net": float("nan"), "model": mdl})
    out = {"window": [str(DISC[0]), str(DISC[1])], "tests": len(carried), "carried": carried}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    return out


if __name__ == "__main__":
    scan()
