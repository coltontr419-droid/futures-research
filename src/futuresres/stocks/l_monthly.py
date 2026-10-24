"""L-families 1-4 (decisions.md 942): monthly cross-sectional rules on liquid US stocks, 2015-2026, vs the equal-weight universe.

    python -m futuresres.stocks.l_monthly [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
LONG = ROOT / "data" / "stocks" / "long" / "daily.jsonl"
COST, PRIOR_SD, SEAL, K = 0.002, 0.02, "2023-01", 20


def load():
    S = {}
    for l in open(LONG):
        x = json.loads(l)
        d = [dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat() for t in x["t"]]
        a = [v if v else np.nan for v in x["a"]]
        S[x["sym"]] = (d, np.array(a, float))
    return S


def main(validate: bool) -> None:
    S = load()
    cal = sorted({d for d, _ in S.values() for d in d})
    month_ends = [cal[i] for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7]]
    idx = {s: {d: i for i, d in enumerate(v[0])} for s, v in S.items()}
    res = {k: [] for k in ("L1", "L2", "L3", "L4")}
    for m0, m1 in zip(month_ends[:-1], month_ends[1:]):
        if (m1[:7] >= SEAL) != validate:
            continue
        rows = []
        for s, (d, a) in S.items():
            i0, i1 = idx[s].get(m0), idx[s].get(m1)
            if i0 is None or i1 is None or i0 < 260 or not np.isfinite(a[i0]) or not np.isfinite(a[i1]) or a[i0] < 5:
                continue
            w = a[i0 - 252:i0 + 1]
            if np.isnan(w).mean() > 0.05:
                continue
            fwd = a[i1] / a[i0] - 1
            hi = np.nanmax(w); r = np.diff(np.log(a[i0 - 63:i0 + 1]))
            rows.append({"fwd": fwd, "L1": a[i0] / hi, "L2": a[i0 - 21] / a[i0 - 252] - 1, "L3": -(a[i0] / a[i0 - 21] - 1), "L4": -np.nanstd(r)})
        if len(rows) < 200:
            continue
        ew = float(np.mean([r["fwd"] for r in rows]))
        for k in res:
            top = sorted(rows, key=lambda r: r[k], reverse=True)[:K]
            res[k].append(float(np.mean([r["fwd"] for r in top])) - COST - ew)
    print(f"L monthly {'sealed' if validate else 'discovery'}")
    for k, v in res.items():
        x = np.array(v)
        if len(x) < 6:
            continue
        m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
        line = f"  {k}: months {len(x)}, excess {m*100:+.2f}%/month, t {t:+.2f}"
        if validate:
            rng = np.random.default_rng(942); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
            post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
            line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
        else:
            line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
