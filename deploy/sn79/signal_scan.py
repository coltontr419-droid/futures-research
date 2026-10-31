"""MVTRX signal scan (decisions.md §1194): which book features predict the mid h seconds ahead in the simulator? Reads a QuoteAgent tape
(one depth line per book per second, plus trades), builds per-book per-second features, and reports each feature's rank correlation (IC)
with the forward mid change, pooled over books, plus the size of the move it predicts in ticks.

    python signal_scan.py /opt/mvtrx/tape_run4.jsonl
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np

HORIZONS = (5, 15, 30, 60)


def rank_ic(x: np.ndarray, y: np.ndarray) -> float:
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 50:
        return float("nan")
    rx = np.argsort(np.argsort(x[ok])); ry = np.argsort(np.argsort(y[ok]))
    return float(np.corrcoef(rx, ry)[0, 1])


def main(path: str) -> None:
    quotes, flow = defaultdict(dict), defaultdict(lambda: defaultdict(float))
    for line in open(path):
        r = json.loads(line)
        sec = r["ts"] // 1_000_000_000
        if "p" in r:
            flow[r["book"]][sec] += r["q"] * (1 if r["s"] == 0 else -1)      # side 0 = taker bought
        elif "bids" in r and r["bids"] and r["asks"]:
            quotes[r["book"]][sec] = r
    feats = defaultdict(list); fwd = {h: [] for h in HORIZONS}; spreads = []
    for book, q in quotes.items():
        secs = sorted(q)
        mid = np.array([(q[s]["bid"] + q[s]["ask"]) / 2 for s in secs])
        idx = {s: i for i, s in enumerate(secs)}
        for i, s in enumerate(secs):
            r = q[s]; b, a = r["bids"], r["asks"]
            bq1, aq1 = b[0][1], a[0][1]
            spread = a[0][0] - b[0][0]; spreads.append(spread)
            micro = (b[0][0] * aq1 + a[0][0] * bq1) / (bq1 + aq1) - mid[i]
            imb = lambda k: (sum(x[1] for x in b[:k]) - sum(x[1] for x in a[:k])) / (sum(x[1] for x in b[:k]) + sum(x[1] for x in a[:k]))
            fl = lambda w: sum(flow[book].get(s - j, 0.0) for j in range(w))
            ret = lambda w: mid[i] - mid[i - w] if i >= w else np.nan
            for name, v in (("microprice-mid", micro), ("imbalance L1", imb(1)), ("imbalance L3", imb(3)), ("imbalance L5", imb(5)),
                            ("taker flow 5s", fl(5)), ("taker flow 30s", fl(30)), ("return 5s", ret(5)), ("return 30s", ret(30)), ("return 120s", ret(120))):
                feats[name].append(v)
            for h in HORIZONS:
                j = idx.get(s + h)
                fwd[h].append(mid[j] - mid[i] if j is not None else np.nan)
    tick = 0.01
    print(f"books {len(quotes)}, book-seconds {len(fwd[5])}, median spread {np.median(spreads):.3f}")
    print(f"{'feature':16}" + "".join(f"  IC {h:>2}s" for h in HORIZONS) + "   top-decile vs bottom-decile fwd move at 30 s (ticks)")
    for name, v in feats.items():
        x = np.array(v, dtype=float)
        ics = [rank_ic(x, np.array(fwd[h], dtype=float)) for h in HORIZONS]
        y = np.array(fwd[30], dtype=float); ok = np.isfinite(x) & np.isfinite(y)
        lo, hi = np.quantile(x[ok], [0.1, 0.9])
        spread_move = (y[ok][x[ok] >= hi].mean() - y[ok][x[ok] <= lo].mean()) / tick if ok.sum() else float("nan")
        print(f"{name:16}" + "".join(f"  {ic:+7.3f}" for ic in ics) + f"   {spread_move:+8.2f}")


if __name__ == "__main__":
    main(sys.argv[1])
