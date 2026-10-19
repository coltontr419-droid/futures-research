"""Rough zero-edge EV of prediction-market prop evaluations (Funding Predicts terms): fair 50c binary bets, 1c spread per contract,
one bet a day of a fixed $ stake, daily loss limit respected by sizing (stake <= daily limit). Eval: pass at +target before the
drawdown floor (trailing EOD or static). Funded: same floor rules, withdraw all profit above the start weekly (80% split), until breach
or 26 weeks. Payout-day consistency and the $100k cap ignored (approximation)."""
import numpy as np
rng = np.random.default_rng(1)
FIRMS = {"FP 50K trailing": (209, 50000, 3000, 2000, 1000, "trail"), "FP 100K trailing": (359, 100000, 6000, 3750, 2000, "trail"),
         "FP 50K static": (375, 50000, 6000, 2500, 1500, "static"), "FP 100K static": (700, 100000, 12000, 5000, 3000, "static")}

def run(stake, start, target, dd, mode, funded, days, n=20000, cost=0.02, split=0.8):
    paid = np.zeros(n); passed = np.zeros(n, bool)
    for i in range(n):
        b = 0.0; peak = 0.0; tot = 0.0
        for d in range(days):
            floor = (min(peak, dd) - dd if mode == "trail" else -dd)   # trailing EOD floor locks at the start balance once peak >= dd
            s = min(stake, b - floor)                                  # never risk past the floor
            b += (s if rng.random() < 0.5 else -s) - cost * s
            if b <= floor:
                break
            peak = max(peak, b)
            if not funded and b >= target:
                passed[i] = True; break
            if funded and d % 5 == 4 and b > 0:
                tot += b * split; b = 0.0                              # weekly: withdraw profit above the start
        paid[i] = tot
    return passed.mean(), paid.mean()

for name, (fee, start, target, dd, dl, mode) in FIRMS.items():
    best = None
    for stake in (dl * 0.25, dl * 0.5, dl * 0.75, dl):
        pp, _ = run(stake, start, target, dd, mode, False, 45, n=6000)
        _, fv = run(stake, start, target, dd, mode, True, 130, n=6000)
        ev = pp * fv - fee
        if best is None or ev > best[0]:
            best = (ev, stake, pp, fv)
    ev, stake, pp, fv = best
    print(f"{name:18} fee ${fee:4} | best daily stake ${stake:6,.0f}: P(pass) {pp:5.1%}, funded EV ${fv:7,.0f} (26 wks) -> EV per attempt ${ev:+7,.0f} ({ev/fee:+.1f}x fee)")
