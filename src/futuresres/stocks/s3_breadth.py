"""S-family 3 (decisions.md §1115): share of liquid stocks above their 50-session mean, against its 250-session mean, as a contrarian next-session sign for MNQ.

    python -m futuresres.stocks.s3_breadth [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SEAL, COST = "2023-01", 0.25 / 20000 * 2


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = [str(c) for c in z["cal"]]; A = z["A"].astype(np.float64)
    q = json.loads((ROOT / "data" / "stocks" / "y_QQQ.json").read_text())["chart"]["result"][0]
    qd = {dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"): c for t, c in zip(q["timestamp"], q["indicators"]["adjclose"][0]["adjclose"]) if c}
    B = np.full(len(cal), np.nan)
    for i in range(50, len(cal)):
        W = A[:, i - 49:i + 1]; ok = np.isfinite(W).all(axis=1)
        if ok.sum() >= 300:
            B[i] = float((A[ok, i] > W[ok].mean(axis=1)).mean())
    x, r, sd, prev = [], [], [], None
    for i in range(300, len(cal) - 1):
        d0, d1 = cal[i], cal[i + 1]
        if (d0[:7] >= SEAL) != validate or d0 < "2016-01" or d0 not in qd or d1 not in qd or not np.isfinite(B[i]):
            continue
        zz = B[i] - np.nanmean(B[i - 250:i])
        side = 1.0 if zz < 0 else -1.0; ret = qd[d1] / qd[d0] - 1
        x.append((side - 1.0) * ret - (COST if prev is not None and side != prev else 0.0)); r.append(ret); sd.append(side); prev = side
    x = np.array(x); m, t = x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    line = f"S3 {'sealed' if validate else 'discovery'}: sessions {len(x)}, long share {np.mean(np.array(sd) > 0):.0%}, mean x {m*1e4:+.2f} bp/session, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(1115); sig = np.array(sd) < 0; R = np.array(r); sh = []
        for _ in range(2000):
            s2 = np.roll(sig, rng.integers(1, len(x))); sh.append((np.where(s2, -2.0, 0.0) * R).mean())
        pct = float((np.array(sh) < m).mean() * 100)
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    print(line)


if __name__ == "__main__":
    main(sys.argv[1:] == ["validate"])
