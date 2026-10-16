"""A59 - what a four-month run looks like on Tradeify's 50K Daily, account by account (decisions.md 623). No trial.

    python -m futuresres.reporting.a59_detail
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
import futuresres.reporting.a43_scale as a43
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d24_shock as sh

ROOT = Path(__file__).resolve().parents[3]
PER = (("2025 starts", "post", dt.date(2025, 1, 1), dt.date(2026, 12, 31)), ("2021-26", "post", dt.date(2021, 1, 1), dt.date(2026, 12, 31)),
       ("2010-20", "pre", dt.date(2010, 1, 1), dt.date(2020, 12, 31)))


def runs() -> dict:
    s = a23.specs()["50K Daily"]; R = a43.masks()
    zs = sh.shocks(d10.series(), "ZN"); nxt = lambda d: d + dt.timedelta(days=1 if d.weekday() < 4 else 3)
    zn_short = {nxt(d) for d, q in zs.items() if q[1] and q[0] < 0}
    rule = {"MNQ": lambda v: v in zn_short, "NKD": R["NKD"], "FDXM": R["FDXM"], "MGC": None, "MCL": None}
    out = {}
    for mkt in ("MNQ", "MGC", "MCL", "NKD", "FDXM"):
        n, rt = a23.MARKETS[mkt]
        for era in ("pre", "post"):
            (h, l, c), d = a23.market_paths(mkt, era); dd = [x.astype(object) for x in d]
            if rule[mkt] is not None:
                h, l, c = a27.flip(h, l, c, np.array([rule[mkt](v) for v in dd]))
            r = a23.replay(s, (h, l, c), n, rt)
            out.setdefault(era, {})[mkt] = {dd[i]: {k: (float(r[k][j]) if k in ("net", "fees", "paid") else int(r[k][j]))
                                                   for k in ("net", "fees", "paid", "first", "passes", "payouts", "eval_fails", "funded_fails", "pass_day")}
                                            for j, i in enumerate(r["start"])}
    return out


def dist(x, edges):
    return {lab: float(np.mean([lo <= v <= hi for v in x])) for lab, (lo, hi) in edges.items()}


def summarise(rows: list) -> dict:
    ev = np.array([r["fees"] / 80.0 for r in rows]); pay = np.array([r["payouts"] for r in rows]); first = np.array([r["first"] for r in rows])
    pdays = np.array([r["pass_day"] for r in rows]); net = np.array([r["net"] for r in rows]); paid = np.array([r["paid"] for r in rows])
    return {"runs": len(rows), "evals_bought_mean": float(ev.mean()), "evals_bought": dist(ev, {"1": (1, 1), "2": (2, 2), "3": (3, 3), "4+": (4, 99)}),
            "p_pass": float((np.array([r["passes"] for r in rows]) > 0).mean()), "pass_day_median": float(np.median(pdays[pdays > 0])) if (pdays > 0).any() else None,
            "eval_fails_mean": float(np.mean([r["eval_fails"] for r in rows])), "p_funded_lost": float(np.mean([r["funded_fails"] > 0 for r in rows])),
            "payouts_mean": float(pay.mean()), "payouts": dist(pay, {"0": (0, 0), "1": (1, 1), "2": (2, 2), "3": (3, 3), "4+": (4, 999)}),
            "first_payout_day_median": float(np.median(first[first > 0])) if (first > 0).any() else None,
            "paid_mean": float(paid.mean()), "fees_mean": float(np.mean([r["fees"] for r in rows])), "net_mean": float(net.mean()),
            "net_median": float(np.median(net)), "p_net_pos": float((net > 0).mean()), "net_p10": float(np.percentile(net, 10)), "net_worst": float(net.min()),
            "net_best": float(net.max())}


def main() -> int:
    warnings.filterwarnings("ignore"); R = runs(); res = {}
    for per, era, lo, hi in PER:
        B = R[era]; ds = sorted(d for d in set.intersection(*(set(B[m]) for m in B)) if lo <= d <= hi)
        res[per] = {m: summarise([B[m][d] for d in ds]) for m in B}
        tot_ev = np.array([sum(B[m][d]["fees"] / 80 for m in B) for d in ds]); tot_pay = np.array([sum(B[m][d]["payouts"] for m in B) for d in ds])
        tot_paid = np.array([sum(B[m][d]["paid"] for m in B) for d in ds]); tot_net = np.array([sum(B[m][d]["net"] for m in B) for d in ds])
        res[per]["BOOK"] = {"runs": len(ds), "evals_bought_mean": float(tot_ev.mean()), "evals_bought_p10_p90": [float(np.percentile(tot_ev, 10)), float(np.percentile(tot_ev, 90))],
                            "payouts_mean": float(tot_pay.mean()), "payouts_p10_p90": [float(np.percentile(tot_pay, 10)), float(np.percentile(tot_pay, 90))],
                            "paid_mean": float(tot_paid.mean()), "net_mean": float(tot_net.mean()), "net_median": float(np.median(tot_net)),
                            "p_net_pos": float((tot_net > 0).mean()), "net_p10": float(np.percentile(tot_net, 10)), "net_worst": float(tot_net.min()), "net_best": float(tot_net.max()),
                            "p_any_account_paid": float(np.mean([any(B[m][d]["payouts"] > 0 for m in B) for d in ds]))}
    (ROOT / "reports" / "a59_detail.json").write_text(json.dumps(res, indent=1) + "\n")
    for per in res:
        print(f"\n=== {per} ===")
        for m, x in res[per].items():
            if m == "BOOK":
                print(f"BOOK ({x['runs']} runs): evals bought {x['evals_bought_mean']:.1f} (p10-p90 {x['evals_bought_p10_p90']}), payouts {x['payouts_mean']:.1f} "
                      f"(p10-p90 {x['payouts_p10_p90']}), paid ${x['paid_mean']:,.0f}, net mean ${x['net_mean']:+,.0f} median ${x['net_median']:+,.0f}, "
                      f"P>0 {x['p_net_pos']:.0%}, p10 ${x['net_p10']:+,.0f}, worst ${x['net_worst']:+,.0f}, best ${x['net_best']:+,.0f}, any account paid {x['p_any_account_paid']:.0%}")
            else:
                print(f"{m}: evals {x['evals_bought_mean']:.2f} {x['evals_bought']} | pass {x['p_pass']:.0%} (median day {x['pass_day_median']}), eval fails {x['eval_fails_mean']:.2f}, "
                      f"funded lost {x['p_funded_lost']:.0%} | payouts {x['payouts_mean']:.2f} {x['payouts']} first-payout day {x['first_payout_day_median']} | "
                      f"paid ${x['paid_mean']:,.0f} fees ${x['fees_mean']:,.0f} net ${x['net_mean']:+,.0f} (median {x['net_median']:+,.0f}, P>0 {x['p_net_pos']:.0%}, "
                      f"p10 {x['net_p10']:+,.0f}, worst {x['net_worst']:+,.0f}, best {x['net_best']:+,.0f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
