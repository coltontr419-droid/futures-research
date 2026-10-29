# §1103 addendum: P(one Fast Track account reaches its first payout) by bracket (take, stop as fractions of the drawdown), MNQ RTH long. Run: python scripts/a130_first_payout_grid.py
import numpy as np, sys
import futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a124_fast_track_sizes import SIZES
from futuresres.reporting.a123_fast_track_policy import trade
def first_payout(h, l, c, s0, W, L, T, kmax):
    n = max(1, int(round(max(W, L) / 600.0))); w, lo = W / n, L / n
    bal = pk = cyc = cbest = 0.0; bought = 1
    for s in range(s0, len(c)):
        x, blown, pk, _ = trade(h[s], l[s], c[s], bal, pk, T, w, lo, n, None)
        if blown:
            if bought >= kmax:
                return None, bought, s - s0 + 1
            bought += 1; bal = pk = cyc = cbest = 0.0; continue
        bal += x; pk = max(pk, bal); cyc += x; cbest = max(cbest, x)
        amt = min(bal - T["lock"], T["caps"][0])
        if cyc >= T["goal1"] and cbest <= T["cons"][0] * cyc and amt >= T["pmin"]:
            return amt * T["split"], bought, s - s0 + 1
    return "end", bought, 0

eras={"2015-20":a8.era_paths("pre","MNQ","rth_0930_1600")[:3],"2021-26":a8.era_paths("post","MNQ","rth_0930_1600")[:3]}
for name,dd in (("50K",2000.),("100K",4000.)):
    T=dict(TERMS,**SIZES[name])
    for W in (0.1,0.15,0.2,0.325,0.45,0.6):
        for Lf in (0.6,0.8,1.0):
            r={}
            for era,(h,l,c) in eras.items():
                ok=[first_payout(h,l,c,s0,W*dd,Lf*dd,T,1)[0] for s0 in range(0,len(c)-250,3)]
                ok=[o for o in ok if o!="end"]; r[era]=np.mean([o is not None for o in ok])
            print(f"{name:5} take {W:.2f}dd stop {Lf:.1f}dd  P(1st payout, one account) 2015-20 {r['2015-20']:.0%}  2021-26 {r['2021-26']:.0%}",flush=True)
