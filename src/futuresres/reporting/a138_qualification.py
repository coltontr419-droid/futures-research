"""A138 (decisions.md 1112): Bulenox Qualification (Legacy) → Master on the A122/A123 minute engine — the cheap-evaluation route, every size.

Help-center terms (2026-10-29, Option 1): evaluation target / trailing drawdown (intraday, incl. open P&L) 25K $1,500 / $1,500, 50K $3,000 / $2,500, 100K $6,000 / $3,000, 150K
$9,000 / $4,500; access 30 days (≈ 21 sessions; an unpassed evaluation is re-bought); list $145 / $175 / $215 / $325, priced at 89% off (codes advertised for
Qualification), 45% off and list. Master: activation $143 / $148 / $248 / $498; same drawdown, locks at start + $100; payout needs ≥ 10 trading days in the cycle, ≥ $1,000,
balance ≥ start + reserve ($1,600 / $2,600 / $3,100 / $4,600) + the payout, best day ≤ 40% of the cycle's P&L (first cycle counts the whole Master P&L), caps $1,000 /
$1,500 / $1,750 / $2,000 for payouts 1-3; 90% split; each Master ends at its 3rd payout (transition rule, §1109; live account = $0). Separate brackets for the evaluation and
the Master, chosen on one era and scored on the other (MNQ RTH long).

    python -m futuresres.reporting.a138_qualification
"""

from __future__ import annotations

import itertools
import json

import futuresres.reporting.a08_gold as a8
from futuresres.reporting.a123_fast_track_policy import trade

SIZES = {
    "25K": dict(price=145, target=1500, dd=1500, act=143, reserve=1600, cap=1000),
    "50K": dict(price=175, target=3000, dd=2500, act=148, reserve=2600, cap=1500),
    "100K": dict(price=215, target=6000, dd=3000, act=248, reserve=3100, cap=1750),
    "150K": dict(price=325, target=9000, dd=4500, act=498, reserve=4600, cap=2000),
}


def simulate(h, l, c, S, We, Le, Wm, Lm, price):
    ne = max(1, int(round(max(We, Le) / 600.0))); nm = max(1, int(round(max(Wm, Lm) / 600.0)))
    Te = {"dd": float(S["dd"]), "lock": 1e12}; Tm = {"dd": float(S["dd"]), "lock": 100.0}
    stage = 0; bal = pk = cyc = cbest = 0.0; days = 0; age = 0; npay = 0; cost = price; paid = 0.0; pays = 0
    for s in range(len(c)):
        if stage == 0:
            x, blown, pk, _ = trade(h[s], l[s], c[s], bal, pk, Te, We / ne, Le / ne, ne, None); age += 1
            if blown or (age >= 21 and bal + x < S["target"]):
                cost += price; bal = pk = 0.0; age = 0; continue
            bal += x; pk = max(pk, bal)
            if bal >= S["target"]:
                stage = 1; cost += S["act"]; bal = pk = cyc = cbest = 0.0; days = 0; npay = 0
            continue
        x, blown, pk, _ = trade(h[s], l[s], c[s], bal, pk, Tm, Wm / nm, Lm / nm, nm, None)
        if blown:
            stage = 0; cost += price; bal = pk = 0.0; age = 0; continue
        bal += x; pk = max(pk, bal); cyc += x; cbest = max(cbest, x); days += 1
        base = bal if npay == 0 else cyc
        amt = min(S["cap"], bal - S["reserve"])
        if days >= 10 and amt >= 1000 and base > 0 and cbest <= 0.4 * base:
            bal -= amt; npay += 1; pays += 1; paid += 0.9 * amt; cyc = cbest = 0.0; days = 0
            if npay >= 3:
                stage = 0; cost += price; bal = pk = 0.0; age = 0
    return (paid - cost) / len(c) * 84, pays


def main() -> int:
    E = {era: a8.era_paths(era, "MNQ", "rth_0930_1600")[:3] for era in ("pre", "post")}
    out = {}
    for name, S in SIZES.items():
        dd = S["dd"]
        ge = [(w * dd, l * dd) for w, l in itertools.product([0.25, 0.5, 0.75], [0.5, 1.0])]
        gm = [(w * dd, l * dd) for w, l in itertools.product([0.1, 0.2, 0.35], [0.5, 1.0])]
        for label, frac in (("89% off", 0.11), ("45% off", 0.55), ("list", 1.0)):
            price = S["price"] * frac
            res = {e: {(a, b): simulate(*E[e], S, *a, *b, price) for a in ge for b in gm} for e in E}
            row = []
            for sel, oth in (("pre", "post"), ("post", "pre")):
                k = max(res[sel], key=lambda q: res[sel][q][0])
                row.append({"chosen_on": sel, "eval": k[0], "master": k[1], oth: res[oth][k]})
            out[f"{name} {label}"] = row
            print(f"Qualification {name:5} eval {label:8} (${price:,.0f}) + activation ${S['act']}: "
                  + " | ".join(f"chosen {r['chosen_on']} eval {r['eval']} master {r['master']} -> {r[[k for k in r if k in ('pre', 'post')][0]][0]:+7,.0f}" for r in row), flush=True)
    (a8.ROOT / "reports" / "a138_qualification.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
