import numpy as np
rng = np.random.default_rng(11)
def sim(A, frac_bets, funded, days, edge=0.0, n=4000, cost=0.02, split=0.9):
    """PolyFundr (as reported): target 30%, trailing max DD 20% from peak equity, daily DD 10% of the day's start, max risk 5% of start
    per bet. Each day: up to `frac_bets` bets of 5% risk (stop for the day at the daily limit). Funded: withdraw profit above start weekly."""
    T, DD, DAY, R = 0.30 * A, 0.20 * A, 0.10 * A, 0.05 * A; pw = 0.5 * (1 + edge)
    paid = np.zeros(n); passed = np.zeros(n, bool)
    for i in range(n):
        b = peak = tot = 0.0; dead = False
        for d in range(days):
            day0 = b
            for k in range(frac_bets):
                s = min(R, b - (peak - DD), b - (day0 - DAY))
                if s <= 0: break
                b += (s if rng.random() < pw else -s) - cost * s
                if b <= peak - DD: dead = True; break
                if b <= day0 - DAY: break
            if dead: break
            peak = max(peak, b)
            if not funded and b >= T: passed[i] = True; break
            if funded and d % 5 == 4 and b > 0: tot += b * split; peak -= b; b = 0.0   # withdrawal lowers equity and the peak with it
        paid[i] = tot
    return passed.mean(), paid.mean()
for A, fee in ((10000, 125), (25000, 300), (50000, 500)):
    for edge in (0.0, 0.03):
        best = None
        for nb in (1, 2, 3):
            pp, _ = sim(A, nb, False, 60, edge); _, fv = sim(A, nb, True, 130, edge)
            ev = pp * fv - fee
            if best is None or ev > best[0]: best = (ev, nb, pp, fv)
        ev, nb, pp, fv = best
        print(f"PolyFundr {A//1000}K fee ${fee} edge {edge:+.0%}: best {nb} bet(s)/day | P(pass) {pp:5.1%} | funded EV ${fv:7,.0f} (26 wks) | EV/attempt ${ev:+7,.0f} ({ev/fee:+.1f}x fee)")
