"""L-family 19 (decisions.md 992): buy a CEF the session after a CEF activist's original 13D, hold 60 sessions, vs the CEF universe.

    python -m futuresres.stocks.l19_cefact [validate]
"""

from __future__ import annotations

import bisect
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np

from futuresres.stocks.l18_cef import OUT as CEF, series, yahoo

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL, HOLD = 0.004, 0.02, "2022-01", 60
ACT = ["saba", "bulldog", "karpus", "almitas", "1607 capital", "city of london", "relative value partners", "western investment",
       "special opportunities fund", "sit investment"]


def main(validate: bool) -> None:
    funds = json.loads((CEF / "funds.json").read_text()); A = {s: series(yahoo(s), "adj") for s in funds}
    days = sorted({d for s in funds for d in A[s]}); last, res, n = {}, collections.defaultdict(list), 0
    rows = [r for l in open(ROOT / "data" / "stocks" / "l17" / "filings.jsonl") for r in json.loads(l)["rows"] if r["form"] in ("SC 13D", "SCHEDULE 13D")]
    for r in sorted(rows, key=lambda r: r["date"]):
        tk = None
        for nm in r["names"]:
            m = re.search(r"\(([A-Z]{2,5})(?:,|\))", nm)
            if m and m.group(1) in A:
                tk, subj = m.group(1), nm
        if tk is None:
            continue
        filers = " ".join(x.lower() for x in r["names"] if x is not subj)
        if not any(a in filers for a in ACT):
            continue
        if tk in last and (dt.date.fromisoformat(r["date"]) - dt.date.fromisoformat(last[tk])).days < 365:
            continue
        last[tk] = r["date"]
        if (r["date"][:7] >= SEAL) != validate or r["date"] > "2026-07-31":
            continue
        i = bisect.bisect_right(days, r["date"])
        if i + HOLD >= len(days):
            continue
        d0, d1 = days[i], days[i + HOLD]
        if d0 not in A[tk] or d1 not in A[tk]:
            continue
        u = [A[s][d1] / A[s][d0] - 1 for s in funds if d0 in A[s] and d1 in A[s]]
        res[d0[:7]].append(A[tk][d1] / A[tk][d0] - 1 - COST - float(np.mean(u))); n += 1
    x = np.array([np.mean(v) for _, v in sorted(res.items())])
    if len(x) < 6:
        print(f"L19: events {n}, months {len(x)} — too few"); return
    m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    s = f"L19 {'sealed' if validate else 'discovery'}: events {n}, months {len(x)}, excess {m*100:+.2f}%/event (60 sessions), t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(992); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        s += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        s += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(s)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
