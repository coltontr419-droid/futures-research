"""L-family 11 (decisions.md 947): dividend-month premium — stocks predicted (ex-div in month m-12) to go ex-dividend next month.

    python -m futuresres.stocks.l11_divmonth [validate]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COST, PRIOR_SD, SEAL = 0.002, 0.02, "2023-01"


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); syms = list(z["syms"]); A = z["A"].astype(np.float64)
    ex = {json.loads(l)["sym"]: {d[:7] for d in json.loads(l)["ex"]} for l in open(ROOT / "data" / "stocks" / "long" / "divs.jsonl")}
    me = [i for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7]]; res = []; npred = []
    for i0, i1 in zip(me[:-1], me[1:]):
        hold = cal[i1][:7]
        if i0 < 260 or (hold >= SEAL) != validate:
            continue
        y, m = int(hold[:4]), int(hold[5:]); prior = f"{y - 1}-{m:02d}"
        a0, a1 = A[:, i0], A[:, i1]; ok = np.isfinite(a0) & np.isfinite(a1) & (a0 >= 5)
        fwd = a1 / a0 - 1
        pred = np.array([prior in ex.get(s, ()) for s in syms]) & ok
        if pred.sum() < 20 or ok.sum() < 200:
            continue
        res.append(float(np.nanmean(fwd[pred])) - COST - float(np.nanmean(fwd[ok]))); npred.append(int(pred.sum()))
    x = np.array(res); m_, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    line = f"L11 {'sealed' if validate else 'discovery'}: months {len(x)}, median predicted payers {int(np.median(npred))}, excess {m_*100:+.2f}%/month, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(947); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m_).mean() * 100)
        post = m_ * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m_ > 0 and post > 0 else ("WATCHLIST" if m_ > 0 else "REJECT"))
    else:
        line += "  CARRIED" if m_ > 0 and t > 1.96 else "  not carried"
    print(line)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
