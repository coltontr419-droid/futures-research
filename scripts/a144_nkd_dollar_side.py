# A144 (decisions.md 1161): the Fast Track 100K NKD slot (Tokyo 09:00-15:00 = 7 PM-1 AM CT, 2 contracts, take $800 / stop $4,000) with the bot's dollar-week side
# (D227: follow the euro's open -> close sum over the 5 US sessions through the alert day; long if the euro rose) vs fixed long / short. A135 engine, 3-payout cap.
# Run: PYTHONPATH=src python scripts/a144_nkd_dollar_side.py
import datetime as dt
import numpy as np
import futuresres.reporting.a21_more_accounts as a21
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.a123_fast_track_policy as m
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a124_fast_track_sizes import SIZES
T = dict(TERMS, **SIZES["100K"]); m.RT = 4.72
E = d10.series()["6E"]; ed = sorted(E)

def side_for(tokyo_day):
    alert = tokyo_day - dt.timedelta(days=1)
    while alert.weekday() >= 5:
        alert -= dt.timedelta(days=1)
    prior = [d for d in ed if d <= alert][-5:]
    if len(prior) < 5 or prior[-1] != alert:
        return 1.0
    s = sum(E[d] for d in prior)
    return 1.0 if s >= 0 else -1.0

def sim(h, l, c, sides):
    bal = pk = cyc = cb = 0.0; npay = 0; bought = 1; paid = 0.0; n = 2
    for s in range(len(c)):
        if sides[s] > 0: hh, ll, cc = h[s], l[s], c[s]
        else: hh, ll, cc = -l[s], -h[s], -c[s]
        x, blown, pk, _ = m.trade(hh, ll, cc, bal, pk, T, 400.0, 2000.0, n, None)
        if blown:
            bought += 1; bal = pk = cyc = cb = 0.0; npay = 0; continue
        bal += x; pk = max(pk, bal); cyc += x; cb = max(cb, x)
        goal = T["goal1"] if npay == 0 else T["goalN"]; cons = T["cons"][min(npay, 2)]; amt = min(bal - T["lock"] - 0.01, T["caps"][min(npay, 3)])
        if cyc >= goal and cb <= cons * cyc and amt >= T["pmin"]:
            bal -= amt; npay += 1; paid += amt * T["split"]; cyc = cb = 0.0
            if npay >= 3:
                bought += 1; bal = pk = cyc = cb = 0.0; npay = 0
    return (paid - bought * T["fee"]) / len(c) * 84

for e in ("pre", "post"):
    h, l, c, d = a21.paths("NKD", e)
    days = [dt.date.fromisoformat(str(x)[:10]) for x in d]
    rule = np.array([side_for(x) for x in days])
    print(f"{e}: sessions {len(c)}, rule long {np.mean(rule > 0):.0%} | fixed long {sim(h, l, c, np.ones(len(c))):+,.0f} | fixed short {sim(h, l, c, -np.ones(len(c))):+,.0f} | "
          f"dollar-week side {sim(h, l, c, rule):+,.0f} per 84 (3-payout cap)", flush=True)
# the rule's own sealed window (D227 validated 2025-01 -> 2026-08) and its discovery years, separately
h, l, c, d = a21.paths("NKD", "post")
days = [dt.date.fromisoformat(str(x)[:10]) for x in d]
for lo, hi, nm in ((dt.date(2021, 1, 1), dt.date(2024, 12, 31), "2021-24 (D227 discovery)"), (dt.date(2025, 1, 1), dt.date(2026, 9, 30), "2025-26 (D227 sealed + forward)")):
    k = [i for i, x in enumerate(days) if lo <= x <= hi]
    H, L, C = h[k], l[k], c[k]; rule = np.array([side_for(days[i]) for i in k])
    print(f"{nm}: sessions {len(k)} | long {sim(H, L, C, np.ones(len(k))):+,.0f} | short {sim(H, L, C, -np.ones(len(k))):+,.0f} | dollar-week {sim(H, L, C, rule):+,.0f} per 84", flush=True)
