# A142 (decisions.md 1146): the five-slot Fast Track 100K portfolio (A137 slots) simulated jointly by date with Bulenox's transition rule as the help centre states it:
# when an account reaches its 3rd payout it transitions (valued $0); with SWEEP, every other active account holding >= 1 payout transitions with it; while the
# Funded Account(s) are active (FREEZE sessions), accounts bought later stay pending (not tradable), active 0-payout accounts keep trading. Monthly flows.
# Run: PYTHONPATH=src python scripts/a142_transition_sweep.py
import collections, numpy as np
import futuresres.reporting.a08_gold as a8, futuresres.reporting.a21_more_accounts as a21
import futuresres.reporting.a123_fast_track_policy as m
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a124_fast_track_sizes import SIZES
T = dict(TERMS, **SIZES["100K"])

def load(e):
    out = []
    for p, wdw, starts in (("MNQ", "rth_0930_1600", (0, 40)), ("MNQ", "full_1800_1655", (0,)), ("MGC", "full_1800_1655", (0,))):
        h, l, c, d = a8.era_paths(e, p, wdw)
        for st in starts:
            out.append(dict(h=h, l=l, c=c, d=[str(x)[:10] for x in d], n=7, rt=1.22 if p == "MNQ" else 1.52, start=st))
    h, l, c, d = a21.paths("NKD", e)
    out.append(dict(h=h, l=l, c=c, d=[str(x)[:10] for x in d], n=2, rt=4.72, start=0))
    return out

def run(S, sweep, freeze):
    idx = [{dd: i for i, dd in enumerate(s["d"])} for s in S]
    first = max(s["d"][s["start"]] for s in S)
    dates = sorted(set().union(*[set(s["d"]) for s in S]))
    dates = [x for x in dates if x >= first]
    st = [dict(bal=0.0, pk=0.0, cyc=0.0, cb=0.0, np=0, live=True) for _ in S]
    flow = collections.Counter(); flow[dates[0][:7]] -= T["fee"] * len(S); frozen = 0; trans = 0
    def reset(k): st[k].update(bal=0.0, pk=0.0, cyc=0.0, cb=0.0, np=0)
    for di, day in enumerate(dates):
        mo = day[:7]
        if frozen:
            frozen -= 1
            if frozen == 0:
                for k in range(len(S)):
                    if not st[k]["live"]:
                        st[k]["live"] = True; reset(k); flow[mo] -= T["fee"]
        for k, s in enumerate(S):
            i = idx[k].get(day)
            if i is None or not st[k]["live"]:
                continue
            a = st[k]; m.RT = s["rt"]; w, lo = 800.0 / s["n"], 4000.0 / s["n"]
            x, blown, a["pk"], _ = m.trade(s["h"][i], s["l"][i], s["c"][i], a["bal"], a["pk"], T, w, lo, s["n"], None)
            if blown:
                reset(k)
                if frozen: a["live"] = False            # the replacement stays pending until the freeze ends
                else: flow[mo] -= T["fee"]
                continue
            a["bal"] += x; a["pk"] = max(a["pk"], a["bal"]); a["cyc"] += x; a["cb"] = max(a["cb"], x)
            goal = T["goal1"] if a["np"] == 0 else T["goalN"]; cons = T["cons"][min(a["np"], 2)]
            amt = min(a["bal"] - T["lock"] - 0.01, T["caps"][min(a["np"], 3)])
            if a["cyc"] >= goal and a["cb"] <= cons * a["cyc"] and amt >= T["pmin"]:
                flow[mo] += amt * T["split"]; a["bal"] -= amt; a["np"] += 1; a["cyc"] = a["cb"] = 0.0
                if a["np"] >= 3:
                    trans += 1; ended = [k] + ([j for j in range(len(S)) if j != k and st[j]["live"] and st[j]["np"] >= 1] if sweep else [])
                    for j in ended:
                        reset(j)
                        if freeze: st[j]["live"] = False
                        else: flow[mo] -= T["fee"]
                    if freeze: frozen = max(frozen, freeze)
    v = np.array(list(flow.values())); months = sorted(flow)
    tot = np.array([flow[x] for x in months])
    return tot.mean(), np.mean(tot < 0), trans / len(months) * 12

for e in ("pre", "post"):
    S = load(e)
    for sweep in (False, True):
        row = []
        for fz in (0, 20, 60, 120):
            mu, neg, tpy = run(S, sweep, fz); row.append(f"freeze {fz:3}: {mu:+7,.0f}/mo ({neg:.0%} neg)")
        print(f"{e:4} {'sweep' if sweep else 'own  '} | " + " | ".join(row) + f" | transitions/yr {tpy:.1f}", flush=True)
