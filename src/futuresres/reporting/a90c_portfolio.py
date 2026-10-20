"""A90c (decisions.md 765): Tradeify + LucidPro (2026 terms) + TradeDay Quick Pay EOD at zero edge, run on the SAME randomised sides
(the firms move together, as they would trading one rule set): joint net and joint cash low per 84-session run.

    python -m futuresres.reporting.a90c_portfolio
"""

from __future__ import annotations

import sys
import warnings

import numpy as np

import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data
from futuresres.reporting.a73_100k_live import SEEDS, randomised

BASE = dict(cons=1.0, min_days=1, fdd="eod", lock=f.START, max_acc=5, live=("never", 0), live_split=0.9, cool=20, live_room_bonus=False)
BOOK = {"Tradeify Select Daily": (dict(f.FIRMS["Tradeify Select Daily"], fee=116.0), "5: 3NKD+2FDXM"),
        "LucidPro 2026": (dict(f.FIRMS["Lucid Daily"], fee=129.5, fdd="eod", cons=1.0, payout=("above", 2_100.0, 500.0, 2_000.0)), "5: NKD×5"),
        "TradeDay QP EOD": (dict(BASE, fee=79.0, payout=("above", 0.0, 250.0, None), split=0.5), "5: NKD×5")}


def main() -> int:
    warnings.filterwarnings("ignore")
    for lab, (c, P) in (("2021-26", data("post")), ("2010-20", data("pre"))):
        net = {k: [] for k in BOOK}; low = {k: [] for k in BOOK}
        for s in SEEDS[:3]:
            R = randomised(P, s)
            for k, (F, mix) in BOOK.items():
                r = f.simulate(c, R, 84, f.MIXES[mix], F); net[k].append(r["net"]); low[k].append(r["min_cash"])
        N = {k: np.concatenate(v) for k, v in net.items()}; L = {k: np.concatenate(v) for k, v in low.items()}
        tot = sum(N.values()); lo = sum(L.values())
        print(f"{lab}: " + " | ".join(f"{k} {N[k].mean():+,.0f}" for k in BOOK))
        print(f"   all three: net mean {tot.mean():+,.0f}, median {np.median(tot):+,.0f}, P(net>0) {(tot>0).mean():.0%}, p10 {np.percentile(tot,10):+,.0f}, "
              f"p90 {np.percentile(tot,90):+,.0f} | cash low (sum, conservative) median {np.median(lo):+,.0f}, 5% {np.percentile(lo,5):+,.0f}, worst {lo.min():+,.0f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
