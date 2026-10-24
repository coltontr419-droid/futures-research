"""R-family 3 (overnight SPY) and 4 (weekly low-volatility 20) — decisions.md 930.

    python -m futuresres.stocks.r3r4 [validate]
"""

from __future__ import annotations

import datetime as dt
import sys

import numpy as np

from futuresres.stocks.i1_insider import bars

SEAL, PRIOR_SD = "2026-01-01", 0.02


def verdict(a: np.ndarray, validate: bool, seed: int) -> str:
    m, t = float(a.mean()), float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a))))
    s = f"n {len(a)}, mean {m*100:+.3f}%, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(seed); pct = float((np.array([(a * rng.choice((-1.0, 1.0), len(a))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + a.var(ddof=1) / len(a))
        return s + f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    return s + ("  CARRIED" if m > 0 and t > 1.96 else "  not carried")


def main(validate: bool) -> None:
    B = bars(); sd, so, sc, _ = B.pop("__SPY")
    on, intra = [], []
    for i in range(1, len(sd)):
        if sd[i] < "2025-06-02" or (sd[i] >= SEAL) != validate or None in (sc[i - 1], so[i], sc[i]):
            continue
        on.append(so[i] / sc[i - 1] - 1 - 0.0002); intra.append(sc[i] / so[i] - 1)
    print("R3 overnight SPY:", verdict(np.array(on), validate, 930), "| intraday mean %+.3f%%" % (np.mean(intra) * 100))
    si = {d: i for i, d in enumerate(sd)}; idx = {s: {d: i for i, d in enumerate(v[0])} for s, v in B.items()}; ex = []
    for f in [d for d in sd if dt.date.fromisoformat(d).weekday() == 4 and d >= "2025-06-06"]:
        if (f >= SEAL) != validate:
            continue
        fi = si[f]; nf = next((sd[j] for j in range(fi + 1, min(fi + 7, len(sd))) if dt.date.fromisoformat(sd[j]).weekday() == 4), None)
        if fi + 1 >= len(sd) or not nf:
            continue
        mon = sd[fi + 1]; cand = []
        for s, (ds, o, c, v) in B.items():
            ix = idx[s]; i = ix.get(f)
            if i is None or i < 21 or not c[i] or c[i] < 5:
                continue
            rr = [c[j] / c[j - 1] - 1 for j in range(i - 19, i + 1) if c[j] and c[j - 1]]
            dv = [c[j] * v[j] for j in range(i - 20, i) if c[j] and v[j]]
            a, b = ix.get(mon), ix.get(nf)
            if len(rr) < 15 or not dv or float(np.median(dv)) < 5e6 or a is None or b is None or not o[a] or not c[b]:
                continue
            cand.append((float(np.std(rr)), c[b] / o[a] - 1))
        if len(cand) >= 20:
            cand.sort(); r = float(np.mean([x[1] for x in cand[:20]])) - 0.002
            ex.append(r - (sc[si[nf]] / so[si[mon]] - 1))
    print("R4 low-vol 20 vs SPY (weekly):", verdict(np.array(ex), validate, 931))


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])
