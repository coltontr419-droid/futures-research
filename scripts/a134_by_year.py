# A134 (decisions.md 1108): the 100K Fast Track plans by calendar year (one slot, continuous timeline, re-buy next session), minute engine, drift removed.
# Run: python scripts/a134_by_year.py
import numpy as np, collections
import futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import trade
from futuresres.reporting.a124_fast_track_sizes import SIZES
T = dict(TERMS, **SIZES["100K"])
def yearly(h, l, c, d, W=800.0, L=4000.0):
    n = 7; w, lo = W / n, L / n
    bal = pk = cyc = cbest = 0.0; npay = 0
    net = collections.Counter(); pays = collections.Counter(); bought = collections.Counter()
    bought[str(d[0])[:4]] += 1
    for s in range(len(c)):
        y = str(d[s])[:4]
        x, blown, pk, _ = trade(h[s], l[s], c[s], bal, pk, T, w, lo, n, None)
        if blown:
            net[y] -= T["fee"]; bought[y] += 1; bal = pk = cyc = cbest = 0.0; npay = 0; continue
        bal += x; pk = max(pk, bal); cyc += x; cbest = max(cbest, x)
        goal = T["goal1"] if npay == 0 else T["goalN"]; cons = T["cons"][min(npay, 2)]
        amt = min(bal - T["lock"], T["caps"][min(npay, 3)])
        if cyc >= goal and cbest <= cons * cyc and amt >= T["pmin"]:
            bal -= amt; npay += 1; pays[y] += 1; net[y] += amt * T["split"]; cyc = cbest = 0.0
    net[str(d[0])[:4]] -= T["fee"]
    return net, pays, bought
rows = collections.defaultdict(dict)
for nm, (p, w) in {"MNQ day": ("MNQ", "rth_0930_1600"), "MNQ full": ("MNQ", "full_1800_1655"), "MGC full": ("MGC", "full_1800_1655")}.items():
    for e in ("pre", "post"):
        h, l, c, d = a8.era_paths(e, p, w)
        net, pays, bought = yearly(h, l, c, d)
        for y in net:
            rows[y][nm] = (net[y], pays[y], bought[y])
print(f"{'year':6}" + "".join(f"{k:>26}" for k in ("MNQ day", "MNQ full", "MGC full")) + f"{'3 slots':>10}")
for y in sorted(rows):
    cells = [rows[y].get(k) for k in ("MNQ day", "MNQ full", "MGC full")]
    tot = sum(x[0] for x in cells if x)
    print(f"{y:6}" + "".join(f"{(f'{x[0]:+8,.0f} ({x[1]} pay/{x[2]} acct)') if x else '—':>26}" for x in cells) + f"{tot:+10,.0f}")
