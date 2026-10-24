"""E-family 3 (decisions.md 972): earnings-announcement premium, close d-2 -> close d+1, large caps vs the equal-weight universe.

    python -m futuresres.stocks.e3_eap [validate]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL, MINCAP = 0.002, 0.02, "2024-01", 10e9


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); sx = {s: i for i, s in enumerate(z["syms"])}
    A = z["A"].astype(np.float64); ci = {d: i for i, d in enumerate(cal)}; wk = collections.defaultdict(list); seen = set()
    for l in open(ROOT / "data" / "options" / "x1" / "calendar.jsonl"):
        x = json.loads(l); d = x["date"]
        if not ("2020-01-01" <= d <= "2026-10-16") or (d[:7] >= SEAL) != validate:
            continue
        i = ci.get(d)
        if i is None or i < 2 or i + 1 >= len(cal):
            continue
        for r in x["rows"]:
            s = (r.get("symbol") or "").strip(); j = sx.get(s)
            try:
                c = float((r.get("marketCap") or "").replace("$", "").replace(",", ""))
            except ValueError:
                c = 0.0
            if j is None or c < MINCAP or (s, d) in seen:
                continue
            seen.add((s, d)); a0, a1 = A[j, i - 2], A[j, i + 1]
            if not (np.isfinite(a0) and np.isfinite(a1)):
                continue
            u = A[:, i + 1] / A[:, i - 2] - 1
            y, w, _ = dt.date.fromisoformat(cal[i - 2]).isocalendar()
            wk[(y, w)].append(a1 / a0 - 1 - COST - float(np.nanmean(u)))
    x = np.array([np.mean(v) for _, v in sorted(wk.items())]); n = sum(map(len, wk.values()))
    m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    s = f"E3 {'sealed' if validate else 'discovery'}: events {n}, weeks {len(x)}, excess {m*100:+.3f}%/event, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(972); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        s += f", placebo {pct:.0f}th, posterior {post*100:+.3f}% -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        s += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(s)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
