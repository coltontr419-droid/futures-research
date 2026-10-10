"""A16 - the strategy portfolio as it stands: three Tradeify accounts (4 MNQ 09:30-16:00 long; 8 MGC 03:00-11:30 with
the weekly COT direction, Z08; 10 MCL session long), with gold's edge planted at Z08's posterior Sharpe 0.36 (as A11),
against the same portfolio at zero edge. Real order, stops at the stop price, 84 trading days. A COMPUTATION; no
trial. decisions.md 118.

    python -m futuresres.reporting.a16_portfolio
"""

import contextlib
import io
import math
import sys
import warnings

import numpy as np

import futuresres.reporting.a01_game as g, futuresres.reporting.a02_real as a2, futuresres.reporting.a08_gold as a8
import futuresres.reporting.a12_joint as j, futuresres.reporting.a15_crude as c15

def gold(era, S):
    h, l, c, d = a8.era_paths(era, "MGC", "london_0300_1130")
    ramp = (np.arange(1, c.shape[1] + 1, dtype=np.float32) / c.shape[1])[None, :]
    dr = np.float32(S / math.sqrt(252) * float(c[:, -1].std())) * ramp
    h, l, c = h + dr, l + dr, c + dr; n = 8; tot = np.float32(n * 3.32)
    a2._PATHS["p"] = ((h * n - (tot - a8.RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32))
    r = a2.sequential(1, "replay", per_trader=True); a2._PATHS.clear(); e = r["each"]
    return {"date": np.asarray(d)[e["start"]].astype("datetime64[D]"), "net": e["net"], "first": e["first_payout_day"], "fees": e["fees"], "paid": e["paid"]}
def crude(era):
    h, l, c, d = c15.mcl_paths(era); orig = a2._bracket_day
    a2._PATHS["p"], o = c15._engine(h, l, c, 10); a2._bracket_day = c15.one_bar_rule(o)
    r = a2.sequential(1, "replay", per_trader=True); a2._bracket_day = orig; a2._PATHS.clear(); e = r["each"]
    return {"date": d[e["start"]], "net": e["net"], "first": e["first_payout_day"], "fees": e["fees"], "paid": e["paid"]}

def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    a2.STOP_FILL = "level"
    for era in ("post", "pre"):
        mnq, cl = j.per_start(era, "MNQ"), crude(era)
        for S, lab in ((0.0, "gold always long, zero edge (before)"), (0.36, "gold with COT direction, posterior 0.36 (now)")):
            gd = gold(era, S)
            common = np.intersect1d(np.intersect1d(mnq["date"], gd["date"]), cl["date"])
            sel = lambda x: {k: v[np.searchsorted(x["date"], common)] for k, v in x.items()}
            A, B, C = sel(mnq), sel(gd), sel(cl)
            net = A["net"] + B["net"] + C["net"]; paid = A["paid"] + B["paid"] + C["paid"]; fees = A["fees"] + B["fees"] + C["fees"]
            pays = (A["first"] > 0).astype(int) + (B["first"] > 0) + (C["first"] > 0)
            print(f"{era} | {lab:47} | gold P(pay) {np.mean(B['first']>0):.0%} gold net {B['net'].mean():+5.0f} | 3-acct: P(any) {np.mean(pays>0):.1%} "
                  f"streams paying {pays.mean():.2f} | paid ${paid.mean():,.0f} fees ${fees.mean():,.0f} | net mean {net.mean():+,.0f} median {np.median(net):+,.0f} "
                  f"| P(net>0) {np.mean(net>0):.0%} | p10 {np.quantile(net,.1):+,.0f} worst {net.min():+,.0f}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
