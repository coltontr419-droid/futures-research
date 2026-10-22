"""H-family 5s (decisions.md 865): short >= 20% gap-ups — sealed half only (2026-03-01 -> 10-20), once.

    python -m futuresres.stocks.h5s_short
"""

from __future__ import annotations

import collections

import numpy as np

from futuresres.stocks.h2_ssr import PRIOR_SD, ROOT, SEAL
from futuresres.stocks.h5_gapup import events

COST = {"open->close": 0.010 + 0.005, "open->next open": 0.010 + 0.010}


def main() -> None:
    E = [e for e in events() if e["day"] >= SEAL]; out = {}
    print(f"H5s sealed: gap-up events {len(E)}, days {len({e['day'] for e in E})}")
    for rule, c in COST.items():
        by = collections.defaultdict(list)
        for e in E:
            gross_long = e["r"][rule] + 0.010                       # H5 stored long returns net of its 1% cost
            by[e["day"]].append(-gross_long - c)
        xs = np.array([x for v in by.values() for x in v]); dm = np.array([np.mean(v) for v in by.values()])
        m = float(xs.mean()); t = float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))))
        rng = np.random.default_rng(865)
        pct = float((np.array([(xs * rng.choice((-1.0, 1.0), len(xs))).mean() for _ in range(2000)]) < m).mean() * 100)
        post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + xs.var(ddof=1) / len(xs))
        dec = "CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
        out[rule] = {"n": len(xs), "mean": m, "median": float(np.median(xs)), "t": t, "placebo": pct, "posterior": post0, "decision": dec}
        print(f"  short {rule:16}: n {len(xs)}, mean {m*100:+.2f}%, median {np.median(xs)*100:+.2f}%, t(days) {t:+.2f}, placebo {pct:.0f}th, "
              f"posterior {post0*100:+.2f}% -> {dec}")
    import json
    (ROOT / "reports" / "h5s_validation.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
