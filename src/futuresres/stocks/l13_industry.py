"""L-family 13 (decisions.md 950): industry momentum — members of the top 3 industries by 126-session return, monthly.

    python -m futuresres.stocks.l13_industry [validate]
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL = 0.002, 0.02, "2023-01"


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); syms = list(z["syms"]); A = z["A"].astype(np.float64)
    ind = {x["symbol"].strip(): x.get("industry") for x in json.loads((ROOT / "data" / "stocks" / "screener.json").read_text())["data"]["rows"]}
    lab = np.array([ind.get(s) or "" for s in syms])
    me = [i for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7]]; res = []
    for i0, i1 in zip(me[:-1], me[1:]):
        if i0 < 260 or (cal[i1][:7] >= SEAL) != validate:
            continue
        past = A[:, i0] / A[:, i0 - 126] - 1; fwd = A[:, i1] / A[:, i0] - 1
        ok = np.isfinite(past) & np.isfinite(fwd) & (A[:, i0] >= 5) & (lab != "")
        if ok.sum() < 200:
            continue
        g = collections.defaultdict(list)
        for j in np.where(ok)[0]:
            g[lab[j]].append(j)
        rk = sorted(((float(np.mean(past[m])), k) for k, m in g.items() if len(m) >= 5), reverse=True)[:3]
        mem = [j for _, k in rk for j in g[k]]
        res.append(float(np.mean(fwd[mem])) - COST - float(np.mean(fwd[ok])))
    x = np.array(res); mu, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    line = f"L13 {'sealed' if validate else 'discovery'}: months {len(x)}, excess {mu*100:+.2f}%/month, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(950); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < mu).mean() * 100)
        post = mu * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and mu > 0 and post > 0 else ("WATCHLIST" if mu > 0 else "REJECT"))
    else:
        line += "  CARRIED" if mu > 0 and t > 1.96 else "  not carried"
    print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
