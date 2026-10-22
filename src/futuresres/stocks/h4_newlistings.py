"""H-family 4 (decisions.md 856): new listings' first trading days. Reuses H2's daily bars.

    python -m futuresres.stocks.h4_newlistings            # discovery
    python -m futuresres.stocks.h4_newlistings validate   # sealed, once
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys

import numpy as np

from futuresres.stocks.h2_ssr import DIR, PRIOR_SD, ROOT, SEAL

COST = 0.010
RULES = ("day1 open->close", "day2 open->close", "day1 close->day5 close")


def events() -> list[dict]:
    out = []
    for l in open(DIR / "daily.jsonl"):
        d = json.loads(l)
        if d.get("err") or not d["t"]:
            continue
        days = [dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat() for t in d["t"]]
        o, c, v = d["o"], d["c"], d["v"]
        idx = [i for i in range(len(days)) if v[i] and o[i] and c[i]]
        if not idx or days[idx[0]] < "2025-07-01" or len(idx) < 6 or o[idx[0]] < 1.0:
            continue
        i0, i1, i4 = idx[0], idx[1], idx[4]
        out.append({"sym": d["sym"], "day": days[i0], "r": {RULES[0]: c[i0] / o[i0] - 1 - COST, RULES[1]: c[i1] / o[i1] - 1 - COST,
                                                            RULES[2]: c[i4] / c[i0] - 1 - COST}})
    return out


def run(validate: bool) -> None:
    E = [e for e in events() if (e["day"] >= SEAL) == validate]; res = {}
    print(f"H4 {'sealed' if validate else 'discovery'}: new listings {len(E)}")
    for rule in RULES:
        by = collections.defaultdict(list)
        for e in E:
            by[e["day"][:7]].append(e["r"][rule])                      # cluster by listing month
        xs = np.array([x for v in by.values() for x in v]); dm = np.array([np.mean(v) for v in by.values()])
        if len(dm) < 3:
            continue
        m = float(xs.mean()); t = float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm)))); med = float(np.median(xs))
        line = f"  {rule:22}: n {len(xs)}, mean {m*100:+.2f}%, median {med*100:+.2f}%, t(months) {t:+.2f}"
        if validate:
            rng = np.random.default_rng(856)
            pct = float((np.array([(xs * rng.choice((-1.0, 1.0), len(xs))).mean() for _ in range(2000)]) < m).mean() * 100)
            post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + xs.var(ddof=1) / len(xs))
            res[rule] = "CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
            line += f", placebo {pct:.0f}th -> {res[rule]}"
        else:
            res[rule] = bool(m > 0 and t > 1.96); line += "  CARRIED" if res[rule] else ""
        print(line)
    (ROOT / "reports" / ("h4_validation.json" if validate else "h4_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    run(sys.argv[1:2] == ["validate"])
