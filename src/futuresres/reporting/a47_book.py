"""A47 - the five-account book with more accounts on the dollar rules (decisions.md 575). No trial.

    python -m futuresres.reporting.a47_book
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.a35_nkddollar as a35
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d111_screen as d111
import futuresres.reporting.d24_shock as d24
import futuresres.reporting.d3_relay as d3

ROOT = Path(__file__).resolve().parents[3]
BOOKS = {"A deployed (MNQ, MGC, MCL, NKD, FDXM)": {"MNQ": 1, "MGC": 1, "MCL": 1, "NKD": 1, "FDXM": 1},
         "B 2xNKD + 2xFDXM + MNQ": {"MNQ": 1, "NKD": 2, "FDXM": 2},
         "C 3xNKD + 2xFDXM": {"NKD": 3, "FDXM": 2}}


def masks():
    sh = d24.shocks(d10.series(), "ZN"); nxt = lambda d: d + dt.timedelta(days=1 if d.weekday() < 4 else 3)
    zn_short = {nxt(d) for d, q in sh.items() if q[1] and q[0] < 0}
    W = a35.weak_dollar_week("6E=F"); X = d111.predictor("DX-Y.NYB")
    return {"MNQ": lambda v: v in zn_short, "NKD": lambda v: W.get(d3.prev_weekday(v), 0.0) < 0,
            "FDXM": lambda v: X.get(d3.prev_weekday(v), 0.0) < 0, "MGC": None, "MCL": None}


def per_start(era: str) -> dict:
    s = a23.specs()["50K Daily"]; M = masks(); out = {}
    for mkt in ("MNQ", "MGC", "MCL", "NKD", "FDXM"):
        (h, l, c), d = a23.market_paths(mkt, era); dd = [x.astype(object) for x in d]; n, rt = a23.MARKETS[mkt]
        pp = (h, l, c) if M[mkt] is None else a27.flip(h, l, c, np.array([M[mkt](v) for v in dd]))
        r = a23.replay(s, pp, n, rt)
        out[mkt] = {dd[i]: float(x) for i, x in zip(r["start"], r["net"])}
    return out


def main(argv=None) -> int:
    warnings.filterwarnings("ignore"); res = {}
    for era in ("pre", "post"):
        P = per_start(era); common = sorted(set.intersection(*(set(v) for v in P.values())))
        periods = {"2010-20": [d for d in common if d < dt.date(2021, 1, 1)]} if era == "pre" else \
                  {"2021-26": common, "2025 starts": [d for d in common if d >= dt.date(2025, 1, 1)]}
        for per, ds in periods.items():
            if not ds:
                continue
            row = {"starts": len(ds), "account_p_negative": {m: float(np.mean([P[m][d] < 0 for d in ds])) for m in P},
                   "account_mean": {m: float(np.mean([P[m][d] for d in ds])) for m in P}}
            print(f"\n{per} ({len(ds)} common starts) — per account: " + ", ".join(f"{m} {row['account_mean'][m]:+,.0f} (neg {row['account_p_negative'][m]:.0%})" for m in P), flush=True)
            for bn, B in BOOKS.items():
                tot = np.array([sum(k * P[m][d] for m, k in B.items()) for d in ds])
                b = {"mean": float(tot.mean()), "p_pos": float((tot > 0).mean()), "p10": float(np.percentile(tot, 10)), "p5": float(np.percentile(tot, 5)),
                     "worst": float(tot.min())}
                row[bn] = b
                print(f"  {bn:38}: mean {b['mean']:+8,.0f}  P(net>0) {b['p_pos']:.0%}  p10 {b['p10']:+8,.0f}  p5 {b['p5']:+8,.0f}  worst {b['worst']:+8,.0f}", flush=True)
            res[per] = row
    (ROOT / "reports" / "a47_book.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
