"""D-series family 19 - one combined ridge model per window (decisions.md 194). Fit on 2018-01 -> 2022-12 (penalty by
leave-one-year-out CV), frozen, then scored once on sealed 2023-01 -> 2026-08 by signals/d_model.py.

    python -m futuresres.reporting.d19_model --fit
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "d19_models.json"
DISC = (dt.date(2018, 1, 1), dt.date(2022, 12, 31))
VAL = (dt.date(2023, 1, 1), dt.date(2026, 8, 31))
TARGETS = ("NKD_win", "DAX_win", "MGC_win", "MNQ_win", "MCL", "ZS")
#: target -> list of (feature series, "same" | "prev")
HANDOFF = {
    "NKD_win": [("MNQ_win", "prev"), ("DAX_win", "prev"), ("MGC_win", "prev"), ("MCL", "prev"), ("ZS", "prev"), ("NKD_win", "prev"), ("NKD_pre", "same")],
    "ZS": [("MNQ_win", "prev"), ("DAX_win", "prev"), ("MGC_win", "prev"), ("MCL", "prev"), ("NKD_win", "prev"), ("ZS", "prev")],
    "MCL": [("MNQ_win", "prev"), ("DAX_win", "prev"), ("MGC_win", "prev"), ("ZS", "prev"), ("NKD_win", "prev"), ("MCL", "prev")],
    "DAX_win": [("NKD_win", "same"), ("MNQ_win", "prev"), ("MGC_win", "prev"), ("MCL", "prev"), ("ZS", "prev"), ("DAX_win", "prev"), ("DAX_pre", "same")],
    "MGC_win": [("NKD_win", "same"), ("MNQ_win", "prev"), ("DAX_win", "prev"), ("MCL", "prev"), ("ZS", "prev"), ("MGC_win", "prev"), ("MGC_pre", "same")],
    "MNQ_win": [("NKD_win", "same"), ("DAX_morn", "same"), ("MGC_morn", "same"), ("MCL", "prev"), ("ZS", "prev"), ("MNQ_win", "prev"), ("MNQ_on", "same")],
}
COST = {"MNQ_win": 0.5, "MGC_win": 0.8, "MCL": 5.4, "NKD_win": 0.2, "DAX_win": 0.3, "ZS": 0.7}
LAMBDAS = (1.0, 10.0, 100.0, 1000.0, 10000.0)


def features(S: dict, target: str):
    """dates, y (target bps), X (raw features with NaN), names."""
    own = S[target]; ds = sorted(own); r = np.array([own[d] for d in ds])
    s20 = np.full(len(r), np.nan)
    for i in range(20, len(r)):
        s20[i] = r[i - 20:i].std(ddof=1)
    names = [f"{f}({w})" for f, w in HANDOFF[target]] + ["trend5", "trend20", "vol_state", "Mon", "Tue", "Wed", "Thu"]
    D, Y, X = [], [], []
    for i, d in enumerate(ds):
        if i < 270:
            continue
        row = []
        for f, w in HANDOFF[target]:
            row.append(S[f].get(d if w == "same" else d3.prev_weekday(d), np.nan))
        med = np.nanmedian(s20[i - 250:i])
        row += [r[i - 5:i].sum(), r[i - 20:i].sum(), s20[i] / med if med > 0 else np.nan] + [1.0 if d.weekday() == k else 0.0 for k in range(4)]
        D.append(d); Y.append(r[i]); X.append(row)
    return np.array(D), np.array(Y), np.array(X, float), names


def standardise(X, mu=None, sd=None):
    if mu is None:
        mu = np.nanmean(X, axis=0); sd = np.nanstd(X, axis=0); sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    return np.nan_to_num(Z, nan=0.0), mu, sd


def ridge(Z, y, lam):
    """beta for standardised Z (intercept free: y's mean)."""
    b0 = y.mean(); k = Z.shape[1]
    beta = np.linalg.solve(Z.T @ Z + lam * np.eye(k), Z.T @ (y - b0))
    return b0, beta


def sharpe(x) -> float:
    return float(x.mean() / x.std(ddof=1)) if len(x) > 2 and x.std() > 0 else -9.0


def fit(target: str, S: dict) -> dict:
    D, Y, X, names = features(S, target)
    m = np.array([DISC[0] <= d <= DISC[1] for d in D]); Dd, Yd, Xd = D[m], Y[m], X[m]
    assert Dd.max() <= DISC[1]
    yrs = np.array([d.year for d in Dd]); cv = {}
    for lam in LAMBDAS:
        oof = np.zeros(len(Yd))
        for yr in sorted(set(yrs)):
            tr = yrs != yr
            Zt, mu, sd = standardise(Xd[tr]); b0, beta = ridge(Zt, Yd[tr], lam)
            Zv, _, _ = standardise(Xd[~tr], mu, sd); oof[~tr] = b0 + Zv @ beta
        cv[lam] = sharpe(np.sign(oof) * Yd - COST[target])
    best = max(cv, key=cv.get)
    Z, mu, sd = standardise(Xd); b0, beta = ridge(Z, Yd, best)
    insample = np.sign(b0 + Z @ beta) * Yd - COST[target]
    return {"target": target, "names": names, "lambda": best, "cv_sharpe_daily": cv, "b0": float(b0), "beta": beta.tolist(),
            "mu": mu.tolist(), "sd": sd.tolist(), "train_days": int(len(Yd)), "train_mean_y": float(Yd.mean()),
            "insample_net_bps": float(insample.mean()), "share_long_insample": float((b0 + Z @ beta > 0).mean())}


def predict(model: dict, X: np.ndarray) -> np.ndarray:
    Z, _, _ = standardise(X, np.array(model["mu"]), np.array(model["sd"]))
    return model["b0"] + Z @ np.array(model["beta"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--fit", action="store_true")
    a = ap.parse_args(argv)
    if a.fit:
        S = d3.series(); out = {}
        for t in TARGETS:
            mdl = fit(t, S); out[t] = mdl
            top = sorted(zip(mdl["names"], mdl["beta"]), key=lambda z: -abs(z[1]))[:4]
            print(f"{t:8}: lambda {mdl['lambda']:>7.0f}; out-of-fold daily Sharpe {mdl['cv_sharpe_daily'][mdl['lambda']]:+.3f}; in-sample net "
                  f"{mdl['insample_net_bps']:+.2f} bps; long {mdl['share_long_insample']:.0%}; largest: "
                  + ", ".join(f"{n} {b:+.1f}" for n, b in top), flush=True)
        OUT.write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
