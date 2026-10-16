"""A67 - the launch's cash path: how much starting capital the plan needs (decisions.md 642). No trial."""

from __future__ import annotations

import datetime as dt
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a63_firms as f
import futuresres.reporting.a65_slip_fund as s65
from futuresres.reporting.a60_live import data

ROOT = Path(__file__).resolve().parents[3]
RT = {"NKD": 7.28, "FDXM": 3.56}


def launch_paths(P):
    P1 = s65.slipped(P, 1); out = {}
    for m, (h, l, c, cost, has) in P1.items():
        n = a23.MARKETS[m][0]; out[m] = (h, l, c, cost - n * a23.MARKETS[m][1] + n * RT.get(m, a23.MARKETS[m][1]), has)
    return out


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    cp, Pp = data("post"); F = dict(f.FIRMS["Tradeify Select Daily"], data_month=14.0)
    r = f.simulate(cp, launch_paths(Pp), 84, f.MIXES["5: 3NKD+2FDXM"], F)
    st = np.array(cp[: len(cp) - 84]); m25 = np.array([x >= dt.date(2025, 1, 1) for x in st])
    for lab, m in (("2025 starts", m25), ("2021-26", np.ones(len(st), bool))):
        mc = r["min_cash"][m]; fp = r["first_pay"][m]; net = r["net"][m] - 14.0 * 4
        row = {"runs": int(m.sum()), "capital_at_risk_median": float(-np.median(mc)), "p95": float(-np.percentile(mc, 5)), "p99": float(-np.percentile(mc, 1)),
               "worst": float(-mc.min()), "share_low_worse_than": {str(x): float((mc < -x).mean()) for x in (500, 1000, 1500, 2000, 3000)},
               "first_payout_day_median": float(np.median(fp[fp > 0])) if (fp > 0).any() else None, "first_payout_day_p90": float(np.percentile(fp[fp > 0], 90)),
               "no_payout_share": float((fp < 0).mean()), "cash_day84_mean": float(net.mean()), "cash_day84_median": float(np.median(net))}
        out[lab] = row
        print(f"{lab} ({row['runs']} starts): capital at risk median ${row['capital_at_risk_median']:,.0f}, 95% ${row['p95']:,.0f}, 99% ${row['p99']:,.0f}, worst ${row['worst']:,.0f} | "
              f"low worse than: " + ", ".join(f"-${k} {v:.0%}" for k, v in row["share_low_worse_than"].items()) + f" | first payout day median {row['first_payout_day_median']}, "
              f"90% by day {row['first_payout_day_p90']:.0f}, never {row['no_payout_share']:.0%} | cash at day 84 mean ${row['cash_day84_mean']:+,.0f} median ${row['cash_day84_median']:+,.0f}", flush=True)
    (ROOT / "reports" / "a67_cashpath.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
