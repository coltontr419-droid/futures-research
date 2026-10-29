"""A127 (decisions.md 1101): Bulenox Momentum (evaluation, then a free Momentum Master) on the A122/A123 minute engine, every size.

Terms from Bulenox's help center (2026-10-29, Option 1, trailing incl. open P&L, locks at start + $100): evaluation target / drawdown 25K $1,500 / $1,000, 50K $3,000 /
$2,000, 100K $6,000 / $3,000, 150K $9,000 / $4,500, fee $94 / $143 / $248 / $358 (priced at the user's 45% discount, and at list); no consistency, no minimum days.
Momentum Master (free, same drawdown, fresh balance): each cycle needs ≥ 5 qualifying days (net ≥ $100 / $150 / $200 / $250), best day ≤ 35% of the cycle's net
profit, balance ≥ the minimum payout balance ($1,500 / $3,000 / $4,500 / $6,500 profit), the request leaves ≥ the reserve ($1,000 / $2,000 / $3,000 / $4,500) and is
≤ the cycle's net profit, ≥ $500 / $1,000; caps by payout number (25K $1,000; 50K $1.5k/2k/2.5k/3k; 100K $2k/2.5k/3k/4k; 150K $2.5k/3k/4k/5k); later cycles need new
profit ≥ $1,000 / $2,000 / $3,500 / $5,000; 90% split. Separate brackets for the evaluation and the Master, chosen on one era and scored on the other.

    python -m futuresres.reporting.a127_momentum
"""

from __future__ import annotations

import itertools
import json

import futuresres.reporting.a08_gold as a8
from futuresres.reporting.a123_fast_track_policy import trade

DISC = 268.40 / 488.0
SIZES = {
    "25K": dict(fee=94, dd=1000, target=1500, qday=100, minbal=1500, reserve=1000, pmin=500, caps=(1000, 1000, 1000, 1000), goalN=1000),
    "50K": dict(fee=143, dd=2000, target=3000, qday=150, minbal=3000, reserve=2000, pmin=1000, caps=(1500, 2000, 2500, 3000), goalN=2000),
    "100K": dict(fee=248, dd=3000, target=6000, qday=200, minbal=4500, reserve=3000, pmin=1000, caps=(2000, 2500, 3000, 4000), goalN=3500),
    "150K": dict(fee=358, dd=4500, target=9000, qday=250, minbal=6500, reserve=4500, pmin=1000, caps=(2500, 3000, 4000, 5000), goalN=5000),
}


def simulate(h, l, c, S, We, Le, Wm, Lm, fee):
    T = {"dd": float(S["dd"]), "lock": 100.0}
    ne = max(1, int(round(max(We, Le) / 600.0))); nm = max(1, int(round(max(Wm, Lm) / 600.0)))
    stage = 0; bal = pk = cyc = cbest = 0.0; qd = 0; npay = 0; bought = 1; paid = 0.0; pays = 0
    for s in range(len(c)):
        if stage == 0:
            x, blown, pk, _ = trade(h[s], l[s], c[s], bal, pk, T, We / ne, Le / ne, ne, None)
        else:
            x, blown, pk, _ = trade(h[s], l[s], c[s], bal, pk, T, Wm / nm, Lm / nm, nm, None)
        if blown:
            bought += 1; stage = 0; bal = pk = cyc = cbest = 0.0; qd = 0; npay = 0
            continue
        bal += x; pk = max(pk, bal)
        if stage == 0:
            if bal >= S["target"]:
                stage = 1; bal = pk = cyc = cbest = 0.0; qd = 0; npay = 0
            continue
        cyc += x; cbest = max(cbest, x); qd += x >= S["qday"]
        goal_ok = npay == 0 or cyc >= S["goalN"]
        amt = min(S["caps"][min(npay, 3)], bal - S["reserve"], cyc)
        if qd >= 5 and goal_ok and cyc > 0 and cbest <= 0.35 * cyc and bal >= S["minbal"] and amt >= S["pmin"]:
            bal -= amt; npay += 1; pays += 1; paid += 0.9 * amt; cyc = cbest = 0.0; qd = 0
    return (paid - bought * fee) / len(c) * 84, bought / max(pays, 1)


def main() -> int:
    E = {era: a8.era_paths(era, "MNQ", "rth_0930_1600")[:3] for era in ("pre", "post")}
    out = {}
    for name, S in SIZES.items():
        dd = S["dd"]; fee = S["fee"] * DISC
        ge = [(w * dd, l * dd) for w, l in itertools.product([0.25, 0.5, 0.75], [0.5, 1.0])]
        gm = [(w * dd, l * dd) for w, l in itertools.product([0.15, 0.25, 0.4], [0.5, 1.0])]
        res = {e: {(a, b): simulate(*E[e], S, *a, *b, fee) for a in ge for b in gm} for e in E}
        out[name] = {}
        for sel, oth in (("pre", "post"), ("post", "pre")):
            k = max(res[sel], key=lambda q: res[sel][q][0])
            out[name][sel] = {"eval": k[0], "master": k[1], sel: res[sel][k], oth: res[oth][k],
                              "list_price_other_era": simulate(*E[oth], S, *k[0], *k[1], S["fee"])[0]}
            print(f"Momentum {name:5} fee ${fee:,.0f}: chosen on {sel} eval {k[0]} master {k[1]} -> {sel} {res[sel][k][0]:+7,.0f} | {oth} {res[oth][k][0]:+7,.0f} "
                  f"({res[oth][k][1]:.1f} evals/payout; at list {out[name][sel]['list_price_other_era']:+,.0f})", flush=True)
    (a8.ROOT / "reports" / "a127_momentum.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
