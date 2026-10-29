# A136 (decisions.md 1110): the 100K Fast Track on other Bulenox-listed CME markets we have minute paths for (A21 HistData windows): NKD (Tokyo 09:00-15:00 JST,
# 1 full contract), and currency futures 6E / 6A / 6B / 6J (A21 windows, full contracts). Take/stop as
# fractions of the $4,000 drawdown (FX in full contracts: $4.72 round trip beats ten micros at $1.00 each), contracts fixed per market, chosen on one era and scored on the other. Run: python scripts/a136_more_markets.py
import itertools, numpy as np
import futuresres.reporting.a21_more_accounts as a21
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import trade
from futuresres.reporting.a124_fast_track_sizes import SIZES
T = dict(TERMS, **SIZES["100K"])
RT = {"NKD": 4.72, "6E": 4.72, "6A": 4.72, "6B": 4.72, "6J": 4.72}   # Bulenox rate sheet: full FX $2.36/side (micros $0.50/side cost more per notional); NKD assumed the same
def sim(h, l, c, W, L, n, rt):
    w, lo = W / n, L / n
    bal = pk = cyc = cbest = 0.0; npay = 0; bought = 1; paid = 0.0; pays = 0
    import futuresres.reporting.a123_fast_track_policy as m
    m.RT = rt
    for s in range(len(c)):
        x, blown, pk, _ = trade(h[s], l[s], c[s], bal, pk, T, w, lo, n, None)
        if blown:
            bought += 1; bal = pk = cyc = cbest = 0.0; npay = 0; continue
        bal += x; pk = max(pk, bal); cyc += x; cbest = max(cbest, x)
        goal = T["goal1"] if npay == 0 else T["goalN"]; cons = T["cons"][min(npay, 2)]
        amt = min(bal - T["lock"] - 0.01, T["caps"][min(npay, 3)])
        if cyc >= goal and cbest <= cons * cyc and amt >= T["pmin"]:
            bal -= amt; npay += 1; pays += 1; paid += amt * T["split"]; cyc = cbest = 0.0
    return (paid - bought * T["fee"]) / len(c) * 84, bought / max(pays, 1)
for mk, scale, ns in (("NKD", 1.0, (1, 2)), ("6E", 1.0, None), ("6A", 1.0, None), ("6B", 1.0, None), ("6J", 1.0, (1, 2))):
    E = {}
    for e in ("pre", "post"):
        h, l, c, d = a21.paths(mk, e)
        E[e] = (h * scale, l * scale, c * scale)
    daily = float(np.median(np.max(E["post"][0], 1) - np.min(E["post"][1], 1)))
    for side in (1, -1):
        res = {}
        for e, (h, l, c) in E.items():
            H, L_, C = (h, l, c) if side > 0 else (-l, -h, -c)
            grid = {}
            for wf, lf in itertools.product([0.1, 0.2, 0.325], [0.75, 1.0]):
                W, Ls = wf * 4000, lf * 4000
                for n in (ns or (max(1, int(round(Ls / max(daily * 1.5, 1.0)))),)):
                    grid[(wf, lf, n)] = sim(H, L_, C, W, Ls, n, RT[mk])
            res[e] = grid
        out = []
        for sel, oth in (("pre", "post"), ("post", "pre")):
            b = max(res[sel], key=lambda k: res[sel][k][0]); out.append(f"chosen {sel} {b} -> {oth} {res[oth][b][0]:+7,.0f} ({res[oth][b][1]:.1f}/payout)")
        print(f"{mk:4} {'long' if side > 0 else 'short':5} (median daily range/contract ${daily:,.0f}) | " + " | ".join(out), flush=True)
