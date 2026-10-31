"""What do the bots know when they hit us? (decisions.md §1199) (1) Do books move together (cross-book correlation of 10 s mid returns, and
whether the other books' average move over the last 5 s predicts this book's next 30 s)? (2) Before a bot hits our quote vs before a background
trader does: this book's own mid move in the 5 s before, and the other books' average move in the 5 s before, signed in the taker's direction."""
import bisect, json, statistics as st, sys
from collections import defaultdict
import numpy as np
me = int(sys.argv[2]); mids = defaultdict(dict); fills = []
for line in open(sys.argv[1]):
    r = json.loads(line)
    if "p" in r:
        if r["Ma"] == me: fills.append(r)
    elif r.get("bid") and r.get("ask"): mids[r["book"]][r["ts"] // 1_000_000_000] = (r["bid"] + r["ask"]) / 2
books = sorted(mids); secs = sorted(set.intersection(*[set(v) for v in mids.values()]))
M = np.array([[mids[b][s] for s in secs] for b in books])            # books x secs
R10 = (M[:, 10:] - M[:, :-10]) / M[:, :-10]
C = np.corrcoef(R10); off = C[~np.eye(len(books), dtype=bool)]
print(f"books {len(books)}, common seconds {len(secs)}; cross-book correlation of 10 s returns: median {np.median(off):+.3f}, mean {off.mean():+.3f}")
# does the average of the OTHER books' last-5 s move predict this book's next 30 s?
idx = {s: i for i, s in enumerate(secs)}; xs, ys = [], []
for i in range(5, len(secs) - 30, 3):
    r5 = (M[:, i] - M[:, i - 5]) / M[:, i - 5]; tot = r5.sum()
    for b in range(len(books)):
        xs.append((tot - r5[b]) / (len(books) - 1)); ys.append((M[b, i + 30] - M[b, i]) / M[b, i])
xs, ys = np.array(xs), np.array(ys)
print(f"other books' last-5 s move -> this book's next 30 s: rank IC {np.corrcoef(np.argsort(np.argsort(xs)), np.argsort(np.argsort(ys)))[0, 1]:+.3f}")
bi = {b: k for k, b in enumerate(books)}; out = defaultdict(lambda: ([], []))
for t in fills:
    s = t["ts"] // 1_000_000_000
    if s - 5 not in idx or s not in idx or t["book"] not in bi: continue
    i, k = idx[s], bi[t["book"]]
    taker_dir = 1 if t["s"] == 0 else -1                                  # side 0 = taker bought (lifted our offer)
    own = taker_dir * (M[k, i] - M[k, i - 5]) / 0.01
    r5 = (M[:, i] - M[:, i - 5]) / M[:, i - 5]; oth = taker_dir * ((r5.sum() - r5[k]) / (len(books) - 1)) * 1e4
    kind = "bot" if t["Ta"] is not None and t["Ta"] >= 0 else "background"
    out[kind][0].append(own); out[kind][1].append(oth)
for k, (o, x) in out.items():
    print(f"{k:10} fills {len(o):5}: own book's prior 5 s move in taker's direction mean {st.mean(o):+.2f} ticks (median {st.median(o):+.2f}); other books' prior 5 s move {st.mean(x):+.2f} bp")
