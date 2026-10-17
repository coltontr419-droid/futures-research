"""A77 - the confirmed NKD / DAX edges in CFD prop accounts with a static drawdown (The5ers High Stakes as modelled; decisions.md 670).
No trial.

    python -m futuresres.reporting.a77_cfd_static
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a21_more_accounts as a21
import futuresres.reporting.a27_standalone as a27
from futuresres.reporting.a76_live_windows import EXITS, SRC, _raw

ROOT = Path(__file__).resolve().parents[3]
SIZE, FEE = 10_000.0, 78.0
T1, T2, FLOOR, DAILY, PDAY, SPLIT, CYCLE = 0.10, 0.05, 0.90, 0.05, 0.005, 0.80, 10
COST_BPS = {"NKD": 2.2 + 1.0, "DAX": 0.6 + 1.0}
MK = {"NKD": "NKD", "DAX": "FDXM"}
DISC = (dt.date(2021, 1, 1), dt.date(2024, 12, 31))


def rel_paths(era: str):
    """Per market: (h, l, c relative returns with the deployed side, {date: row})."""
    out = {}
    for m in ("NKD", "DAX"):
        h, l, c, ix = _raw(MK[m], era, EXITS[MK[m]][0]); n = np.float32(a21.notional(SRC[MK[m]]))
        out[m] = (h / n, l / n, c / n, ix)
    return out


def sd_2124(R) -> dict:
    sd = {}
    for m, (h, l, c, ix) in R.items():
        rows = [i for d, i in ix.items() if DISC[0] <= d <= DISC[1]]
        sd[m] = float(np.std(c[rows, -1]))
    return sd


def bracket(h, l, c, W, L):
    A, T = c.shape
    hitW = h >= W[:, None]; hitL = l <= -L[:, None]; big = T + 1
    tw = np.where(hitW.any(1), hitW.argmax(1), big); tl = np.where(hitL.any(1), hitL.argmax(1), big)
    out = c[:, -1].astype(np.float64).copy(); stop = (tl < big) & (tl <= tw); take = (tw < big) & ~stop
    out[stop] = -L[stop]; out[take] = W[take]
    return out


def simulate(R, sd, cal, markets, r, s, k, window=84, flip=None):
    """Back-to-back $10K accounts from every start in cal; returns per-start dict of arrays."""
    S = len(cal); starts = np.arange(0, S - window); A = len(starts)
    phase = np.zeros(A, int); bal = np.ones(A); pdays = np.zeros(A, int); since = np.zeros(A, int)
    fees = np.full(A, FEE); paid = np.zeros(A); evals = np.ones(A); payn = np.zeros(A, int); passes = np.zeros(A, int)
    nm = len(markets); cap_each = DAILY / nm
    for d in range(window):
        idx = starts + d; day_pnl = np.zeros(A)
        for m in markets:
            h, l, c, ix = R[m]
            rows = np.array([ix.get(cal[i], -1) for i in idx]); has = rows >= 0
            if not has.any():
                continue
            q = r / sd[m]; cost = q * COST_BPS[m] / 1e4
            room = bal + day_pnl - FLOOR
            L = np.minimum(np.minimum(s * r, cap_each), room - 1e-4)
            W = k * L if k else np.full(A, 1e9)
            trade = has & (room > cost + 1e-3) & (L > cost)
            rr = np.where(has, rows, 0)
            hh, ll, cc = h[rr], l[rr], c[rr]
            if flip is not None:
                sg = flip[m][rr]
                hh, ll, cc = a27.flip(hh, ll, cc, sg)
            # thresholds in relative-return units of the path: P&L = q x path
            pnl = q * bracket(hh, ll, cc, np.where(trade, (W + cost) / q, 1e9), np.where(trade, np.maximum(L - cost, 1e-6) / q, 1e9)) - cost
            day_pnl += np.where(trade, pnl, 0.0)
        bal = bal + day_pnl
        br = bal <= FLOOR + 1e-9
        pdays += (day_pnl >= PDAY) & (phase < 2)
        ok1 = (phase == 0) & ~br & (bal >= 1 + T1) & (pdays >= 3); ok2 = (phase == 1) & ~br & (bal >= 1 + T2) & (pdays >= 3)
        passes += ok1 | ok2
        since += (phase == 2)
        pay = (phase == 2) & ~br & (since >= CYCLE) & (bal > 1)
        paid += np.where(pay, SPLIT * (bal - 1) * SIZE, 0.0); payn += pay
        bal = np.where(pay, 1.0, bal); since = np.where(pay, 0, since)
        phase = np.where(ok1, 1, np.where(ok2, 2, phase))
        bal = np.where(ok1 | ok2, 1.0, bal); pdays = np.where(ok1 | ok2, 0, pdays); since = np.where(ok2, 0, since)
        # breach (or no room left for a trade): re-buy
        dead = br | ((bal - FLOOR) < 2e-3)
        fees += np.where(dead & (d + 1 < window), FEE, 0.0); evals += dead & (d + 1 < window)
        phase = np.where(dead, 0, phase); bal = np.where(dead, 1.0, bal); pdays = np.where(dead, 0, pdays); since = np.where(dead, 0, since)
    return {"net": paid - fees, "paid": paid, "fees": fees, "evals": evals, "payouts": payn, "passes": passes, "start": starts}


def summ(x, mask):
    n = x["net"][mask]
    return {"runs": int(mask.sum()), "net_mean": float(n.mean()), "net_median": float(np.median(n)), "p_pos": float((n > 0).mean()),
            "p10": float(np.percentile(n, 10)), "paid": float(x["paid"][mask].mean()), "fees": float(x["fees"][mask].mean()),
            "evals": float(x["evals"][mask].mean()), "payouts": float(x["payouts"][mask].mean())}


def main() -> int:
    warnings.filterwarnings("ignore"); out = {"grid_2021_24": {}}
    Rp, Rq = rel_paths("post"), rel_paths("pre"); sd = sd_2124(Rp)
    calp = sorted(set(Rp["NKD"][3]) | set(Rp["DAX"][3])); calq = sorted(set(Rq["NKD"][3]) | set(Rq["DAX"][3]))
    st = np.array(calp[: len(calp) - 84]); m24 = np.array([x < dt.date(2025, 1, 1) for x in st]); m25 = ~m24
    print("window SD 2021-24 (bps):", {m: round(v * 1e4, 1) for m, v in sd.items()}, flush=True)
    MS = {"NKD": ("NKD",), "DAX": ("DAX",), "both": ("NKD", "DAX")}
    for mk, r, s, k in itertools.product(MS, (0.01, 0.02, 0.03), (1, 2), (1, 2, None)):
        x = simulate(Rp, sd, calp, MS[mk], r, s, k); key = f"{mk}|r{r:.0%}|stop {s}x|take {k or 'close'}"
        out["grid_2021_24"][key] = float(x["net"][m24].mean())
    top = sorted(out["grid_2021_24"].items(), key=lambda kv: -kv[1])[:8]
    for kk, v in top:
        print(f"  {kk:32}: 2021-24 {v:+,.0f}", flush=True)
    best = top[0][0]; mk, r_, s_, k_ = best.split("|"); r = float(r_[1:-1]) / 100; s = int(s_.split()[1][:-1]); k = None if k_.endswith("close") else float(k_.split()[1])
    xp = simulate(Rp, sd, calp, MS[mk], r, s, k); xq = simulate(Rq, sd, calq, MS[mk], r, s, k)
    res = {"key": best, "2021-24": summ(xp, m24), "2025 starts": summ(xp, m25), "2021-26": summ(xp, np.ones(len(st), bool)), "2010-20": summ(xq, np.ones(len(xq["net"]), bool))}
    z, zq = [], []
    for seed in range(6):
        rng = np.random.default_rng(seed)
        fp = {m: rng.random(len(Rp[m][2])) < 0.5 for m in Rp}; fq = {m: rng.random(len(Rq[m][2])) < 0.5 for m in Rq}
        z.append(simulate(Rp, sd, calp, MS[mk], r, s, k, flip=fp)["net"].mean()); zq.append(simulate(Rq, sd, calq, MS[mk], r, s, k, flip=fq)["net"].mean())
    res["zero edge 2021-26"], res["zero edge 2010-20"] = float(np.mean(z)), float(np.mean(zq))
    out["chosen"] = res
    for p in ("2021-24", "2025 starts", "2021-26", "2010-20"):
        y = res[p]
        print(f"{best} {p:12}: mean {y['net_mean']:+,.0f} median {y['net_median']:+,.0f} P>0 {y['p_pos']:.0%} p10 {y['p10']:+,.0f} | paid {y['paid']:,.0f} "
              f"fees {y['fees']:,.0f} evals {y['evals']:.1f} payouts {y['payouts']:.1f}", flush=True)
    print(f"zero edge: 2021-26 {res['zero edge 2021-26']:+,.0f} | 2010-20 {res['zero edge 2010-20']:+,.0f}", flush=True)
    (ROOT / "reports" / "a77_cfd_static.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
