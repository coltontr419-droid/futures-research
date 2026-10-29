# A137 (decisions.md 1111): five Fast Track 100K slots (MNQ day x2 with staggered starts, MNQ full, MGC full, NKD Tokyo) as monthly cash flows (payouts x 90% minus
# account purchases), each account ending at its 3rd payout (transition rule, live account = $0) and re-bought next session; drift removed. Run: python scripts/a137_portfolio_months.py
import collections, numpy as np
import futuresres.reporting.a08_gold as a8, futuresres.reporting.a21_more_accounts as a21
import futuresres.reporting.a123_fast_track_policy as m
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a124_fast_track_sizes import SIZES
T = dict(TERMS, **SIZES["100K"])
def flows(h, l, c, d, W, L, n, rt, start=0):
    m.RT = rt; w, lo = W / n, L / n
    bal = pk = cyc = cbest = 0.0; npay = 0; out = collections.Counter()
    out[str(d[start])[:7]] -= T["fee"]
    for s in range(start, len(c)):
        mo = str(d[s])[:7]
        x, blown, pk, _ = m.trade(h[s], l[s], c[s], bal, pk, T, w, lo, n, None)
        if blown:
            out[mo] -= T["fee"]; bal = pk = cyc = cbest = 0.0; npay = 0; continue
        bal += x; pk = max(pk, bal); cyc += x; cbest = max(cbest, x)
        goal = T["goal1"] if npay == 0 else T["goalN"]; cons = T["cons"][min(npay, 2)]
        amt = min(bal - T["lock"] - 0.01, T["caps"][min(npay, 3)])
        if cyc >= goal and cbest <= cons * cyc and amt >= T["pmin"]:
            out[mo] += amt * T["split"]; bal -= amt; npay += 1; cyc = cbest = 0.0
            if npay >= 3:
                out[mo] -= T["fee"]; bal = pk = cyc = cbest = 0.0; npay = 0
    return out
slots = []
for e in ("pre", "post"):
    for p, wdw, starts in (("MNQ", "rth_0930_1600", (0, 40)), ("MNQ", "full_1800_1655", (0,)), ("MGC", "full_1800_1655", (0,))):
        h, l, c, d = a8.era_paths(e, p, wdw)
        for st in starts:
            slots.append((e, f"{p} {wdw} +{st}", flows(h, l, c, d, 800.0, 4000.0, 7, 1.22 if p == "MNQ" else 1.52, st)))
    h, l, c, d = a21.paths("NKD", e)
    slots.append((e, "NKD", flows(h, l, c, d, 800.0, 4000.0, 2, 4.72)))
for e in ("pre", "post"):
    S = [s[2] for s in slots if s[0] == e]
    months = sorted(set().union(*[set(x) for x in S]))
    mnq = [mm for mm in months if mm >= "2015-12"] if e == "pre" else months     # all five slots live
    tot = np.array([sum(x.get(mm, 0.0) for x in S) for mm in mnq])
    r3 = np.convolve(tot, np.ones(3), "valid")
    print(f"{e}: {mnq[0]}..{mnq[-1]} ({len(mnq)} months) 5 slots: mean {tot.mean():+,.0f}/month, median {np.median(tot):+,.0f}, months negative {np.mean(tot < 0):.0%}, "
          f"worst month {tot.min():+,.0f}, worst 3 months {r3.min():+,.0f}, best month {tot.max():+,.0f}", flush=True)
