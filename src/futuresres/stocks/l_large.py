"""L-families 5-7 (decisions.md 943): large-cap weekly reversal, single-stock overnight momentum, large-cap gap-down — long history.

    python -m futuresres.stocks.l_large [validate]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
LONG = ROOT / "data" / "stocks" / "long" / "daily.jsonl"
COST, PRIOR_SD, SEAL, K, TOPN = 0.001, 0.02, "2023-01-01", 20, 200


def verdict(x: np.ndarray, validate: bool, seed: int) -> str:
    m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    s = f"n {len(x)}, excess {m*100:+.3f}%, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(seed); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        return s + f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    return s + ("  CARRIED" if m > 0 and t > 1.96 else "  not carried")


def main(validate: bool) -> None:
    cal = set(); raw = {}
    for l in open(LONG):
        x = json.loads(l); d = [dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat() for t in x["t"]]
        raw[x["sym"]] = (d, x["o"], x["c"], x["a"], x["v"]); cal.update(d)
    cal = sorted(cal); ci = {d: i for i, d in enumerate(cal)}; T = len(cal); syms = sorted(raw)
    A = np.full((len(syms), T), np.nan); O = A.copy(); V = A.copy()
    for j, s in enumerate(syms):
        d, o, c, a, v = raw[s]
        for k, dd in enumerate(d):
            if a[k] and c[k] and o[k]:
                i = ci[dd]; f = a[k] / c[k]; A[j, i] = a[k]; O[j, i] = o[k] * f; V[j, i] = (v[k] or 0) * c[k]
    del raw
    on = O[:, 1:] / A[:, :-1] - 1                      # overnight return into session i (close i-1 -> open i)
    intra = A / O - 1                                  # open -> close of session i
    res = {"L5": [], "L6": [], "L7": []}
    for i in range(260, T - 6):
        if (cal[i] >= SEAL) != validate:
            continue
        dv = np.nanmedian(V[:, i - 63:i], axis=1); ok = np.isfinite(dv) & np.isfinite(A[:, i]) & (A[:, i] >= 5)
        if ok.sum() < 300:
            continue
        top = np.argsort(np.where(ok, dv, -1))[::-1][:TOPN]
        wd = dt.date.fromisoformat(cal[i]).weekday()
        if wd == 4 and i + 5 < T:                          # L5: Friday i, Monday i+1 open -> Friday i+5 close
            r5 = A[top, i] / A[top, i - 5] - 1; fwd = A[top, i + 5] / O[top, i + 1] - 1
            g = np.isfinite(r5) & np.isfinite(fwd)
            if g.sum() > 100:
                worst = np.argsort(np.where(g, r5, np.inf))[:K]
                res["L5"].append(float(np.nanmean(fwd[worst])) - COST - float(np.nanmean(fwd[g])))
        # L6: overnight momentum, buy close i, sell open i+1
        if i + 1 < T:
            cum = np.nansum(on[top, i - 21:i], axis=1); nx = on[top, i]          # on[:, i] = close i -> open i+1
            g = np.isfinite(nx) & (np.isfinite(on[top, i - 21:i]).sum(axis=1) > 15)
            if g.sum() > 100:
                best = np.argsort(np.where(g, cum, -np.inf))[::-1][:K]
                res["L6"].append(float(np.nanmean(nx[best])) - COST - float(np.nanmean(nx[g])))
        # L7: gap-down >= 3% at the open of session i (overnight return into i), buy open sell close
        gap = on[top, i - 1]; ic = intra[top, i]; g = np.isfinite(gap) & np.isfinite(ic)
        sel = g & (gap <= -0.03)
        if sel.sum() and g.sum() > 100:
            res["L7"].append(float(np.nanmean(ic[sel])) - COST - float(np.nanmean(ic[g])))
    print(f"L large-cap {'sealed' if validate else 'discovery'}")
    for k, seed in (("L5", 9435), ("L6", 9436), ("L7", 9437)):
        x = np.array(res[k])
        if len(x) > 5:
            print(f"  {k}: " + verdict(x, validate, seed))


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
