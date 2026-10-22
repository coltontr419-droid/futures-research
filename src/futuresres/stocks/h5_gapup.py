"""H-family 5 (decisions.md 858): large opening gap-ups — buy the open. Reuses H2's daily bars.

    python -m futuresres.stocks.h5_gapup            # discovery
    python -m futuresres.stocks.h5_gapup validate   # sealed, once
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys

import numpy as np

from futuresres.stocks.h2_ssr import DIR, END, PRIOR_SD, ROOT, SEAL, START

COST = 0.010
RULES = ("open->close", "open->next open")


def events() -> list[dict]:
    out = []
    for l in open(DIR / "daily.jsonl"):
        d = json.loads(l)
        if d.get("err"):
            continue
        days = [dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat() for t in d["t"]]
        o, c, v = d["o"], d["c"], d["v"]; last = -99
        for i in range(21, len(days) - 1):
            if None in (c[i - 1], o[i], c[i], o[i + 1]) or not START <= days[i] <= END or o[i] <= 0:
                continue
            dv = [c[j] * v[j] for j in range(i - 20, i) if c[j] is not None and v[j] is not None]
            if c[i - 1] < 1.0 or not dv or np.median(dv) < 1e6 or i - last < 10:
                continue
            if o[i] >= 1.20 * c[i - 1]:
                last = i
                out.append({"sym": d["sym"], "day": days[i], "r": {RULES[0]: c[i] / o[i] - 1 - COST, RULES[1]: o[i + 1] / o[i] - 1 - COST}})
    return out


def run(validate: bool) -> None:
    E = [e for e in events() if (e["day"] >= SEAL) == validate]; res = {}
    print(f"H5 {'sealed' if validate else 'discovery'}: gap-up events {len(E)}, days {len({e['day'] for e in E})}")
    for rule in RULES:
        for tag, sub in (("all", E), ("excl. last 60 days", [e for e in E if e["day"] < "2026-08-21"])):
            by = collections.defaultdict(list)
            for e in sub:
                by[e["day"]].append(e["r"][rule])
            xs = np.array([x for v in by.values() for x in v]); dm = np.array([np.mean(v) for v in by.values()])
            if len(dm) < 3:
                continue
            m = float(xs.mean()); t = float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))))
            line = f"  {rule:16} [{tag}]: n {len(xs)}, mean {m*100:+.2f}%, t(days) {t:+.2f}"
            if tag == "all":
                if validate:
                    rng = np.random.default_rng(858)
                    pct = float((np.array([(xs * rng.choice((-1.0, 1.0), len(xs))).mean() for _ in range(2000)]) < m).mean() * 100)
                    post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + xs.var(ddof=1) / len(xs))
                    res[rule] = "CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
                    line += f", placebo {pct:.0f}th -> {res[rule]}"
                else:
                    res[rule] = bool(m > 0 and t > 1.96); line += "  CARRIED" if res[rule] else ""
            print(line)
    (ROOT / "reports" / ("h5_validation.json" if validate else "h5_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    run(sys.argv[1:2] == ["validate"])
