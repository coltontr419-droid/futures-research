# A129 (decisions.md 1103): with a fixed budget of k accounts bought one at a time, how often is the budget gone before the first payout, and how long until it
# arrives? Replays the minute engine from every 3rd session as a start date (MNQ RTH long; 2010-15 / 2015-20 / 2021-26), Fast Track 50K and 100K plans.
# Run: python scripts/a129_budget_ruin.py
import numpy as np, importlib.util, sys
from pathlib import Path
import futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import trade
from futuresres.reporting.a124_fast_track_sizes import SIZES
spec = importlib.util.spec_from_file_location("a128", Path(__file__).with_name("a128_mnq_2010_15.py"))

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

eras = {"2015-20": a8.era_paths("pre", "MNQ", "rth_0930_1600")[:3], "2021-26": a8.era_paths("post", "MNQ", "rth_0930_1600")[:3]}
for name, W, L in (("50K", 650.0, 2000.0), ("100K", 800.0, 4000.0)):
    T = dict(TERMS, **SIZES[name])
    for k in (1, 2, 3, 4, 5):
        fails = []; days = []; spent = []
        for era, (h, l, c) in eras.items():
            for s0 in range(0, len(c) - 250, 3):
                p, b, d = first_payout(h, l, c, s0, W, L, T, k)
                if p == "end":
                    continue
                fails.append(p is None); spent.append(b * T["fee"])
                if p is not None:
                    days.append(d)
        f = np.mean(fails)
        print(f"{name:5} budget {k} account(s) = ${k * T['fee']:,.0f}: P(budget gone before 1st payout) {f:.0%}; days to 1st payout median {np.median(days):.0f} (p90 {np.percentile(days, 90):.0f}); mean spent ${np.mean(spent):,.0f}", flush=True)
