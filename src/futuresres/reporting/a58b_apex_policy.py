"""A58b - Apex 50K with its own solved bracket policy (an upper bound), against Tradeify 50K Daily (decisions.md 622). No trial."""
import datetime as dt, json, warnings, numpy as np, sys
sys.path.insert(0, "/home/coltontr419/futures-research/src")
import futuresres.reporting.a23_account_sizes as a23, futuresres.reporting.a27_standalone as a27, futuresres.reporting.a43_scale as a43
import futuresres.reporting.d24_shock as sh, futuresres.reporting.d10_universe as d10
warnings.filterwarnings("ignore")
apex = a23.Spec("Apex 50K", 50_000, 25.0, 30, 20, 1.0, 21, 15, None, flex_thr=250, cap_usd=1500.0)
tdy = a23.specs()["50K Daily"]; R = a43.masks()
zs = sh.shocks(d10.series(), "ZN"); nxt = lambda d: d + dt.timedelta(days=1 if d.weekday() < 4 else 3)
zn_short = {nxt(d) for d, q in zs.items() if q[1] and q[0] < 0}
rule = {"MNQ": lambda v: v in zn_short, "NKD": R["NKD"], "FDXM": R["FDXM"], "MGC": None, "MCL": None}
book = {}
for mkt in ("MNQ", "MGC", "MCL", "NKD", "FDXM"):
    n, rt = a23.MARKETS[mkt]
    for era in ("pre", "post"):
        (h, l, c), d = a23.market_paths(mkt, era); dd = [x.astype(object) for x in d]
        if rule[mkt] is not None:
            h, l, c = a27.flip(h, l, c, np.array([rule[mkt](v) for v in dd]))
        ra = a23.replay(apex, (h, l, c), n, rt); rt_ = a23.replay(tdy, (h, l, c), n, rt)
        a_net = ra["paid"] / 0.9 - ra["fees"] - 120.0 * ra["passes"]          # 100% split; activation per pass
        book.setdefault(era, {})[mkt] = ({dd[i]: float(x) for i, x in zip(ra["start"], a_net)}, {dd[i]: float(x) for i, x in zip(rt_["start"], rt_["net"])},
                                         {dd[i]: bool(x > 0) for i, x in zip(ra["start"], ra["first"])})
for per, era, lo, hi in (("2010-20", "pre", dt.date(2010, 1, 1), dt.date(2020, 12, 31)), ("2021-26", "post", dt.date(2021, 1, 1), dt.date(2026, 12, 31)),
                         ("2025 starts", "post", dt.date(2025, 1, 1), dt.date(2026, 12, 31))):
    B = book[era]; ds = sorted(d for d in set.intersection(*(set(B[m][0]) for m in B)) if lo <= d <= hi)
    for j, lab in ((0, "Apex 50K (solved policy, upper bound)"), (1, "Tradeify 50K Daily (solved policy)")):
        tot = np.array([sum(B[m][j][d] for m in B) for d in ds])
        print(f"{per} {lab:38}: {tot.mean():+8,.0f}  P(net>0) {(tot > 0).mean():.0%}  p10 {np.percentile(tot, 10):+8,.0f} | " +
              ", ".join(f"{m} {np.mean([B[m][j][d] for d in ds]):+,.0f}" for m in B), flush=True)
    print(f"{per} Apex P(any payout): " + ", ".join(f"{m} {np.mean([B[m][2][d] for d in ds]):.0%}" for m in B), flush=True)
