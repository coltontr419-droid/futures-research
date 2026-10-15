"""A53 - Tradeify's 50K Lightning (instant funded) for the two rule accounts (decisions.md 606). No trial."""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.a43_scale as a43

ROOT = Path(__file__).resolve().parents[3]
PRICE, START, DD, DLL = 492.0, 50_000.0, 2_000.0, 1_250.0
GOALS = (3_000.0, 2_000.0); CONS = (0.20, 0.25, 0.30); CAPS = (2_000.0, 2_000.0, 2_000.0, 2_500.0)
TAKES, STOPS = (400, 500, 600), (300, 400, 600, 800)


def day(h, l, c, W, L, cost):
    """One bracketed day on one-contract-scaled $ paths: take W, stop L (net), soft DLL; returns (pnl, intraday low)."""
    hitW = np.where(h >= W + cost)[0]; hitL = np.where(l <= -(L - cost))[0]
    tw = hitW[0] if len(hitW) else 10 ** 9; tl = hitL[0] if len(hitL) else 10 ** 9
    if tl <= tw and tl < 10 ** 9:
        p = -L
        low = -L
    elif tw < 10 ** 9:
        p = W; low = float(l[: tw + 1].min()) - cost
    else:
        p = float(c[-1]) - cost; low = float(l.min()) - cost
    return max(p, -DLL), max(low, -DLL)


def run(h, l, c, n, rt, W, L, window=84):
    S = len(c); cost = rt * n; H, Lo, C = h * n, l * n, c * n; nets, pays, firsts = [], [], []
    for s0 in range(S - window):
        fees = PRICE; paid = 0.0; first = -1; eq = START; pk = START; k = 0; cyc = 0.0; best = 0.0
        for d in range(window):
            i = s0 + d
            floor = START if pk >= START + DD else pk - DD
            pnl, low = day(H[i], Lo[i], C[i], W, L, cost)
            if eq + low <= floor:                      # intraday touch of the floor: failed; a new account
                fees += PRICE; eq = START; pk = START; k = 0; cyc = 0.0; best = 0.0; continue
            eq += pnl; pk = max(pk, eq); cyc += pnl; best = max(best, pnl)
            goal = GOALS[0] if k == 0 else GOALS[1]; cons = CONS[min(k, 2)]
            if cyc >= goal and best <= cons * goal:
                amt = min(CAPS[min(k, 3)], eq - START)
                if amt >= 1_000:
                    paid += 0.9 * amt; eq -= amt; k += 1; cyc = 0.0; best = 0.0
                    if first < 0:
                        first = d + 1
        nets.append(paid - fees); pays.append(paid); firsts.append(first)
    return np.array(nets), np.array(firsts)


def main() -> int:
    warnings.filterwarnings("ignore"); R = a43.masks(); out = {}
    for mkt, n in (("NKD", 1), ("FDXM", 2)):
        rt = a23.MARKETS[mkt][1]
        (h, l, c), d = a23.market_paths(mkt, "post"); dd = [x.astype(object) for x in d]
        h, l, c = a27.flip(h, l, c, np.array([R[mkt](v) for v in dd]))
        st = np.array(dd[: len(dd) - 84]); m24 = st < dt.date(2025, 1, 1); m25 = ~m24; grid = {}
        for W, L in itertools.product(TAKES, STOPS):
            net, first = run(h, l, c, n, rt, W, L)
            grid[(W, L)] = {"m24": float(net[m24].mean()), "p24": float((first[m24] > 0).mean()), "m25": float(net[m25].mean()), "p25": float((first[m25] > 0).mean())}
        best = max(grid, key=lambda k: grid[k]["m24"])
        for k in sorted(grid, key=lambda k: -grid[k]["m24"])[:4]:
            g = grid[k]; print(f"{mkt} Lightning take ${k[0]} stop ${k[1]}: 2021-24 starts {g['m24']:+7,.0f} ({g['p24']:.0%}) | 2025 starts {g['m25']:+7,.0f} ({g['p25']:.0%})", flush=True)
        print(f"{mkt} chosen {best}: 2025 starts {grid[best]['m25']:+,.0f} (P(payout) {grid[best]['p25']:.0%})", flush=True)
        out[mkt] = {"grid": {f"{a}/{b}": v for (a, b), v in grid.items()}, "chosen": list(best)}
    (ROOT / "reports" / "a53_lightning.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
