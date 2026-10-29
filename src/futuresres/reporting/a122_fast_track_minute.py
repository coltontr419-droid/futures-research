"""A122 (decisions.md 1095): Bulenox Fast Track replayed minute by minute — the intraday trailing drawdown checked on every 1-minute bar.

A121 (§1092) raised the trailing peak by each trade's best open profit but tested the floor only on the end-of-day balance, so a trade that
ran up, dipped through the raised floor and recovered counted as surviving. Here every minute of the trade does, in the worst order: raise
the peak by the bar's high (open profit), then test the bar's low against the floor (blown), then the stop, then the take. One account slot,
re-bought the next session after a failure, user-verified terms (§1092 addendum). Same trade as the Pine script: 3 MNQ at the 09:30 ET open,
take 108.25 pts, stop 333.25 pts, flat at 16:00.

    python -m futuresres.reporting.a122_fast_track_minute            # history (A23 MNQ RTH minute paths, drift removed)
"""

from __future__ import annotations

import json
import sys

import numpy as np

QTY = 3
W = 108.25 * 2.0                 # take, $ per contract (MNQ $2 a point)
L = 333.25 * 2.0                 # stop, $ per contract
COST = 2.32 * QTY                # round trip
TERMS = dict(fee=268.40, dd=2000.0, lock=100.0, goal1=3000.0, goalN=0.0, cons=(0.20, 0.25, 0.30), pmin=1000.0, caps=(2000.0, 2000.0, 2000.0, 2500.0),
             split=0.90, bot_month=0.0)


def trade(h, l, c, bal, pk, T, exact=True, side=1):
    """One session's trade on 1-contract $ paths relative to the entry. Returns (pnl, blown, peak)."""
    if side < 0:
        h, l, c = -l, -h, -c
    floor = lambda p: min(p - T["dd"], T["lock"])
    for j in range(len(c)):
        hi, lo = QTY * h[j], QTY * l[j]
        if h[j] >= W:                                    # take touched: anything adverse in the same bar counts first
            if exact and bal + lo <= floor(pk):
                return 0.0, True, pk
            if l[j] <= -L:
                return -QTY * L - COST, bal - QTY * L - COST <= floor(pk), pk
            pk = max(pk, bal + QTY * W)
            return QTY * W - COST, False, pk
        if exact:
            pk = max(pk, bal + hi)
            if bal + lo <= floor(pk):
                return 0.0, True, pk
        if l[j] <= -L:
            return -QTY * L - COST, bal - QTY * L - COST <= floor(pk), pk
    x = QTY * float(c[-1]) - COST
    if not exact:                                        # A121's shortcut: the peak sees the best open profit, the floor only the close
        k = len(c) - 1
        pk = max(pk, bal + QTY * min(float(np.max(h[: k + 1])), W))
    return x, bal + x <= floor(pk), pk


def simulate(H, Lo, C, dates, T=TERMS, exact=True, side=1):
    """One slot through every session in order. Returns totals and a log of (date, event, $, balance after)."""
    bal = pk = cyc = cbest = 0.0; npay = 0; bought = 1; payouts = 0; paid = 0.0; log = []
    for s in range(len(C)):
        x, blown, pk = trade(H[s], Lo[s], C[s], bal, pk, T, exact, side)
        if blown:
            log.append((str(dates[s]), "blown (new account bought)", None, None))
            bought += 1; bal = pk = cyc = cbest = 0.0; npay = 0
            continue
        bal += x; pk = max(pk, bal); cyc += x; cbest = max(cbest, x)
        log.append((str(dates[s]), "trade", round(x, 2), round(bal, 2)))
        goal = T["goal1"] if npay == 0 else T["goalN"]
        cons = T["cons"][min(npay, len(T["cons"]) - 1)]
        amt = min(bal - T["lock"], T["caps"][min(npay, len(T["caps"]) - 1)])
        if cyc >= goal and cyc > 0 and cbest <= cons * cyc and amt >= T["pmin"]:
            bal -= amt; npay += 1; payouts += 1; paid += amt * T["split"]; cyc = cbest = 0.0
            log.append((str(dates[s]), "payout", round(amt, 2), round(bal, 2)))
    n = len(C)
    fees = bought * T["fee"] + T["bot_month"] * n / 21.0
    return {"sessions": n, "bought": bought, "payouts": payouts, "paid": round(paid, 2), "fees": round(fees, 2), "net": round(paid - fees, 2),
            "net_per_84": round((paid - fees) / n * 84, 2), "per_payout": round(bought / payouts, 2) if payouts else None,
            "open_balance": round(bal, 2), "log": log}


def main(argv=None) -> int:
    import futuresres.reporting.a08_gold as a8
    out = {}
    for era in ("pre", "post"):
        h, l, c, d = a8.era_paths(era, "MNQ", "rth_0930_1600")
        for side, sname in ((1, "long"), (-1, "short")):
            for exact in (True, False):
                for gN in (0.0, 2000.0):
                    T = dict(TERMS, goalN=gN)
                    r = simulate(h, l, c, d, T, exact, side)
                    key = f"{era} {sname} {'minute' if exact else 'A121-shortcut'} laterGoal={int(gN)}"
                    out[key] = {k: v for k, v in r.items() if k != "log"}
                    print(f"{key:44} sessions {r['sessions']:5} bought {r['bought']:4} payouts {r['payouts']:4} per payout {r['per_payout']} "
                          f"net {r['net']:+10,.0f}  per 84 {r['net_per_84']:+7,.0f}", flush=True)
    p = a8.ROOT / "reports" / "a122_fast_track_minute.json"
    p.write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
