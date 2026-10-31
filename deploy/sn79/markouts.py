"""MVTRX live markouts (decisions.md §1197): from a live QuoteAgent tape, the mid move h seconds after each maker fill, signed so that
positive = the move went our way (we bought and it rose / sold and it fell), in ticks, for one miner versus every other miner on the
same books. Negative means adverse selection: informed takers pick our quotes off.

    python markouts.py /opt/mvtrx/live_tape_x1.jsonl 93
"""

import bisect
import json
import statistics as st
import sys
from collections import defaultdict

HORIZONS = (5, 30, 60)
TICK = 0.01


def main(path: str, me: int) -> None:
    mids = defaultdict(list)                       # book -> [(sec, mid)]
    fills = []                                     # (book, sec, maker id, +1 maker bought / -1 maker sold, qty, price)
    for line in open(path):
        r = json.loads(line)
        if "p" in r:
            if r.get("Ma") is not None and r["Ma"] >= 0:
                fills.append((r["book"], r["ts"] / 1e9, r["Ma"], 1 if r["s"] == 1 else -1, r["q"], r["p"]))
        elif r.get("bid") and r.get("ask"):
            mids[r["book"]].append((r["ts"] / 1e9, (r["bid"] + r["ask"]) / 2))
    for b in mids:
        mids[b].sort()
    secs = {b: [t for t, _ in v] for b, v in mids.items()}

    def mid_at(book, t):
        i = bisect.bisect_left(secs[book], t)
        return mids[book][i][1] if i < len(secs[book]) else None

    res = {h: {"me": [], "field": []} for h in HORIZONS}
    per_book = defaultdict(list); sizes = []
    for book, t, maker, side, q, p in fills:
        if book not in mids:
            continue
        now = mid_at(book, t)
        if now is None:
            continue
        for h in HORIZONS:
            later = mid_at(book, t + h)
            if later is None:
                continue
            mo = side * (later - p) / TICK                # vs our own fill price: spread captured + subsequent move
            res[h]["me" if maker == me else "field"].append(mo)
            if maker == me and h == 30:
                per_book[book].append(mo); sizes.append(q)
    n_me = sum(1 for f in fills if f[2] == me)
    print(f"fills: ours {n_me}, other miners {sum(1 for f in fills if f[2] != me)}; tape span {(max(f[1] for f in fills) - min(f[1] for f in fills)) / 60:.0f} sim min")
    for h in HORIZONS:
        a, b = res[h]["me"], res[h]["field"]
        if a and b:
            print(f"markout {h:>2}s (ticks, + = our way): ours mean {st.mean(a):+.2f} median {st.median(a):+.2f} | other miners mean {st.mean(b):+.2f} median {st.median(b):+.2f}")
    if sizes:
        print(f"our fill size: median {st.median(sizes):.3f}, mean {st.mean(sizes):.3f}")
    worst = sorted(((st.mean(v), b, len(v)) for b, v in per_book.items() if len(v) >= 5))
    print("worst books at 30 s (mean ticks, book, fills):", [(round(m, 1), b, n) for m, b, n in worst[:8]])
    print("best books at 30 s:", [(round(m, 1), b, n) for m, b, n in worst[-5:]])


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
