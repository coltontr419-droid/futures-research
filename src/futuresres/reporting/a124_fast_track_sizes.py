"""A124 (decisions.md 1098): Bulenox Fast Track at every size on the A122/A123 minute engine — which size pays most per account slot and per dollar.

Sizes from bulenox.com's pricing bundle (2026-10-29, list): 25K $338 / $1,000 trailing / first goal $1,500; 50K $488 / $2,000 / $3,000; 100K $648 / $4,000 /
$6,000; 150K $788 / $5,500 / $9,000 (Option 1, intraday trailing locking at +$100, no DLL). Payout caps and later goals from third-party reviews: 25K $1,000
(payouts 1-3) / $1,250, later goal $1,000; 50K $2,000 / $2,500 (user-verified); 100K $2,500 / $3,000, later goal $3,000; 150K $3,000 / $3,500, later goal $4,500;
$1,000 minimum, 20/25/30% consistency, 90% split, price at the user's 45% discount. Bracket (take, stop) as fractions of the drawdown, chosen on one era
and scored on the other; long, drift removed, one slot.

    python -m futuresres.reporting.a124_fast_track_sizes
"""

from __future__ import annotations

import itertools
import json

import futuresres.reporting.a08_gold as a8
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a123_fast_track_policy import simulate

DISC = 268.40 / 488.0
SIZES = {
    "25K": dict(fee=338 * DISC, dd=1000.0, goal1=1500.0, goalN=1000.0, caps=(1000.0, 1000.0, 1000.0, 1250.0)),
    "50K": dict(fee=488 * DISC, dd=2000.0, goal1=3000.0, goalN=2000.0, caps=(2000.0, 2000.0, 2000.0, 2500.0)),
    "100K": dict(fee=648 * DISC, dd=4000.0, goal1=6000.0, goalN=3000.0, caps=(2500.0, 2500.0, 2500.0, 3000.0)),
    "150K": dict(fee=788 * DISC, dd=5500.0, goal1=9000.0, goalN=4500.0, caps=(3000.0, 3000.0, 3000.0, 3500.0)),
}
WF = [0.2, 0.325, 0.45]
LF = [0.75, 1.0]


def main() -> int:
    E = {era: a8.era_paths(era, "MNQ", "rth_0930_1600")[:3] for era in ("pre", "post")}
    out = {}
    for name, s in SIZES.items():
        T = dict(TERMS, **s)
        res = {era: {(w, l): simulate(*E[era], w * s["dd"], l * s["dd"], 0, None, T) for w, l in itertools.product(WF, LF)} for era in E}
        out[name] = {"fee": round(T["fee"], 2)}
        for sel, oth in (("pre", "post"), ("post", "pre")):
            b = max(res[sel], key=lambda k: res[sel][k][0])
            v, vo = res[sel][b][0], res[oth][b][0]
            out[name][f"chosen_on_{sel}"] = {"take/stop of dd": b, sel: res[sel][b], oth: res[oth][b]}
            print(f"{name:5} fee ${T['fee']:,.0f}  chosen on {sel}: take {b[0]:.3f}·dd stop {b[1]:.2f}·dd  {sel} {v:+7,.0f} | {oth} {vo:+7,.0f} per 84 "
                  f"({res[oth][b][1]:.1f} accts/payout)  per $ of one account: {vo / T['fee']:.1f}", flush=True)
    (a8.ROOT / "reports" / "a124_fast_track_sizes.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
