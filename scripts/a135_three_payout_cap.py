# A135 (decisions.md 1109): Bulenox may move a Master-level account to a live Funded Account after its 3rd payout (discretionary; refusing closes it), Master
# balances do not transfer, and pending Master-level accounts cannot be activated while a Funded Account is active. Conservative re-runs: each account ends at its
# 3rd payout (live account valued at $0), then the slot either re-buys next session or sits idle for G sessions. MNQ day / MNQ full / MGC full, 100K, era-split.
# Run: python scripts/a135_three_payout_cap.py
import numpy as np
import futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import trade
from futuresres.reporting.a124_fast_track_sizes import SIZES
T = dict(TERMS, **SIZES["100K"])
def sim(h, l, c, maxpay, gap, W=800.0, L=4000.0, size=None):
    S = T if size is None else dict(TERMS, **SIZES[size])
    n = max(1, int(round(max(W, L) / 600.0))); w, lo = W / n, L / n
    bal = pk = cyc = cbest = 0.0; npay = 0; bought = 1; paid = 0.0; pays = 0; idle = 0
    for s in range(len(c)):
        if idle:
            idle -= 1
            if idle == 0:
                bought += 1
            continue
        x, blown, pk, _ = trade(h[s], l[s], c[s], bal, pk, S, w, lo, n, None)
        if blown:
            bought += 1; bal = pk = cyc = cbest = 0.0; npay = 0; continue
        bal += x; pk = max(pk, bal); cyc += x; cbest = max(cbest, x)
        goal = S["goal1"] if npay == 0 else S["goalN"]; cons = S["cons"][min(npay, 2)]
        amt = min(bal - S["lock"] - 0.01, S["caps"][min(npay, 3)])
        if cyc >= goal and cbest <= cons * cyc and amt >= S["pmin"]:
            bal -= amt; npay += 1; pays += 1; paid += amt * S["split"]; cyc = cbest = 0.0
            if npay >= maxpay:                       # transition: the Master account ends here
                bal = pk = cyc = cbest = 0.0; npay = 0
                if gap: idle = gap
                else: bought += 1
    return (paid - bought * S["fee"]) / len(c) * 84, bought / max(pays, 1)
cases = {"MNQ day": ("MNQ", "rth_0930_1600"), "MNQ full": ("MNQ", "full_1800_1655"), "MGC full": ("MGC", "full_1800_1655")}
for nm, (p, wdw) in cases.items():
    for e in ("pre", "post"):
        h, l, c = a8.era_paths(e, p, wdw)[:3]
        r = [sim(h, l, c, 99, 0), sim(h, l, c, 3, 0), sim(h, l, c, 3, 20), sim(h, l, c, 3, 60), sim(h, l, c, 3, 0, 650, 2000, "50K")]
        print(f"{nm:9} {e:4} | no cap {r[0][0]:+7,.0f} | ends at 3rd payout, re-buy {r[1][0]:+7,.0f} | +20 idle {r[2][0]:+7,.0f} | +60 idle {r[3][0]:+7,.0f} | 50K ends at 3rd {r[4][0]:+7,.0f}", flush=True)
