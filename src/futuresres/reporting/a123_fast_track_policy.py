"""A123 (decisions.md 1097): Fast Track account-management policies on the A122 minute engine — payout size and a stop that respects the room.

A122 (§1095) found most failures come right after a payout: the maximum request drops the balance to the +$100 locked floor, leaving ~$1.4k of
room against a $2k stop. Policies: (a) keep a reserve R above the floor when requesting (amount = min(balance - 100 - R, cap), still ≥ $1,000);
(b) cap the stop at the room minus a margin M (stop = min(L, balance - floor - M), skip the day if the room is under $300); (c) the bracket
(W, L) itself. Chosen on one era, scored on the other (A23 MNQ RTH minute paths, drift removed, long), one slot, user-verified terms.

    python -m futuresres.reporting.a123_fast_track_policy
"""

from __future__ import annotations

import itertools
import json

import numpy as np

import futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS

RT = 2.32


def trade(h, l, c, bal, pk, T, W, L, n, M):
    """Minute replay (worst order in a bar). W/L in $ per contract; the stop is cut to the room minus M when M is set."""
    floor = lambda p: min(p - T["dd"], T["lock"])
    if M is not None:
        room = bal - floor(pk) - M
        if room < 300:
            return 0.0, False, pk, False
        L = min(L, room / n)
    cost = RT * n
    for j in range(len(c)):
        if h[j] >= W:
            if bal + n * l[j] <= floor(pk):
                return 0.0, True, pk, True
            if l[j] <= -L:
                return -n * L - cost, bal - n * L - cost <= floor(pk), pk, True
            return n * W - cost, False, max(pk, bal + n * W), True
        pk = max(pk, bal + n * h[j])
        if bal + n * l[j] <= floor(pk):
            return 0.0, True, pk, True
        if l[j] <= -L:
            return -n * L - cost, bal - n * L - cost <= floor(pk), pk, True
    x = n * float(c[-1]) - cost
    return x, bal + x <= floor(pk), pk, True


def simulate(h, l, c, Wd, Ld, R, M, T=TERMS):
    n = max(1, int(round(max(Wd, Ld) / 600.0))); W, L = Wd / n, Ld / n
    bal = pk = cyc = cbest = 0.0; npay = 0; bought = 1; paid = 0.0; payouts = 0
    for s in range(len(c)):
        x, blown, pk, traded = trade(h[s], l[s], c[s], bal, pk, T, W, L, n, M)
        if blown:
            bought += 1; bal = pk = cyc = cbest = 0.0; npay = 0
            continue
        if not traded:
            continue
        bal += x; pk = max(pk, bal); cyc += x; cbest = max(cbest, x)
        goal = T["goal1"] if npay == 0 else T["goalN"]
        cons = T["cons"][min(npay, len(T["cons"]) - 1)]
        amt = min(bal - T["lock"] - R, T["caps"][min(npay, len(T["caps"]) - 1)])
        if cyc >= goal and cyc > 0 and cbest <= cons * cyc and amt >= T["pmin"]:
            bal -= amt; npay += 1; payouts += 1; paid += amt * T["split"]; cyc = cbest = 0.0
    net = paid - bought * T["fee"]
    return net / len(c) * 84, bought / max(payouts, 1)


def main() -> int:
    E = {era: a8.era_paths(era, "MNQ", "rth_0930_1600")[:3] for era in ("pre", "post")}
    grid = list(itertools.product([450, 650, 900], [1500, 2000], [0, 500, 1000, 1500], [None, 50, 250]))
    res = {}
    for era in ("pre", "post"):
        h, l, c = E[era]
        res[era] = {str(k): simulate(h, l, c, *k) for k in grid}
        print(era, "done", flush=True)
    out = {}
    for sel, oth in (("pre", "post"), ("post", "pre")):
        best = max(grid, key=lambda k: res[sel][str(k)][0])
        base = (650, 2000, 0, None)
        out[f"chosen_on_{sel}"] = {"policy (W, L, reserve, stop margin)": best, f"{sel}": res[sel][str(best)], f"{oth}": res[oth][str(best)],
                                   "baseline A122": {sel: res[sel][str(base)], oth: res[oth][str(base)]}}
        print(f"chosen on {sel}: {best} -> {sel} {res[sel][str(best)][0]:+,.0f} | {oth} {res[oth][str(best)][0]:+,.0f} "
              f"(baseline {res[sel][str(base)][0]:+,.0f} | {res[oth][str(base)][0]:+,.0f})")
    top = sorted(grid, key=lambda k: -min(res["pre"][str(k)][0], res["post"][str(k)][0]))[:8]
    for k in top:
        print("  min-of-eras top:", k, f"pre {res['pre'][str(k)][0]:+,.0f} ({res['pre'][str(k)][1]:.1f}/payout) post {res['post'][str(k)][0]:+,.0f} ({res['post'][str(k)][1]:.1f})")
    (a8.ROOT / "reports" / "a123_fast_track_policy.json").write_text(json.dumps({"selection": out, "all": res}, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
