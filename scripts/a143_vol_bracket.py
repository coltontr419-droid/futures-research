# A143 (decisions.md 1151): Fast Track 100K with a volatility-scaled bracket — the stop in points = k x the median session range of the previous 20 sessions,
# contracts = round($4,000 / stop $ per contract) (1-20 micros), take = $800 / contracts — against the fixed 7-contract plan. A135 engine with the 3-payout cap.
# k chosen on one era, scored on the other. Run: PYTHONPATH=src python scripts/a143_vol_bracket.py
import numpy as np
import futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import trade
from futuresres.reporting.a124_fast_track_sizes import SIZES
T = dict(TERMS, **SIZES["100K"])

def sim(h, l, c, k):
    rng = np.array([float(np.max(h[s]) - np.min(l[s])) for s in range(len(c))])
    bal = pk = cyc = cb = 0.0; npay = 0; bought = 1; paid = 0.0
    for s in range(20, len(c)):
        if k is None:
            n = 7
        else:
            stop = k * float(np.median(rng[s - 20:s])); n = int(min(20, max(1, round(4000.0 / max(stop, 1e-6)))))
        x, blown, pk, _ = trade(h[s], l[s], c[s], bal, pk, T, 800.0 / n, 4000.0 / n, n, None)
        if blown:
            bought += 1; bal = pk = cyc = cb = 0.0; npay = 0; continue
        bal += x; pk = max(pk, bal); cyc += x; cb = max(cb, x)
        goal = T["goal1"] if npay == 0 else T["goalN"]; cons = T["cons"][min(npay, 2)]; amt = min(bal - T["lock"] - 0.01, T["caps"][min(npay, 3)])
        if cyc >= goal and cb <= cons * cyc and amt >= T["pmin"]:
            bal -= amt; npay += 1; paid += amt * T["split"]; cyc = cb = 0.0
            if npay >= 3:
                bought += 1; bal = pk = cyc = cb = 0.0; npay = 0
    return (paid - bought * T["fee"]) / (len(c) - 20) * 84

K = [None, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
for nm, (p, w) in {"MNQ day": ("MNQ", "rth_0930_1600"), "MNQ full": ("MNQ", "full_1800_1655"), "MGC full": ("MGC", "full_1800_1655")}.items():
    R = {}
    for e in ("pre", "post"):
        h, l, c = a8.era_paths(e, p, w)[:3]
        R[e] = {k: sim(h, l, c, k) for k in K}
    line = " | ".join(f"k={k}: {R['pre'][k]:+6,.0f}/{R['post'][k]:+6,.0f}" for k in K)
    pick = {e: max(K[1:], key=lambda k: R[e][k]) for e in R}
    print(f"{nm:8} {line}", flush=True)
    print(f"{nm:8} chosen on pre k={pick['pre']} -> post {R['post'][pick['pre']]:+,.0f} (fixed {R['post'][None]:+,.0f}); chosen on post k={pick['post']} -> pre {R['pre'][pick['post']]:+,.0f} (fixed {R['pre'][None]:+,.0f})", flush=True)
