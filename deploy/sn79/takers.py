"""Who takes our quotes (decisions.md §1199): our maker fills split by taker type (other miner vs background agent), with 30 s markouts."""
import bisect, json, statistics as st, sys
from collections import defaultdict, Counter
me = int(sys.argv[2]); mids = defaultdict(list); fills = []
for line in open(sys.argv[1]):
    r = json.loads(line)
    if "p" in r:
        if r["Ma"] == me: fills.append(r)
    elif r.get("bid") and r.get("ask"): mids[r["book"]].append((r["ts"] / 1e9, (r["bid"] + r["ask"]) / 2))
for b in mids: mids[b].sort()
secs = {b: [t for t, _ in v] for b, v in mids.items()}
def mid_at(b, t):
    i = bisect.bisect_left(secs[b], t); return mids[b][i][1] if i < len(secs[b]) else None
by = defaultdict(list); takers = Counter()
for t in fills:
    later = mid_at(t["book"], t["ts"] / 1e9 + 30)
    if later is None: continue
    mo = (1 if t["s"] == 1 else -1) * (later - t["p"]) / 0.01
    kind = "other miner" if t["Ta"] is not None and t["Ta"] >= 0 else "background"
    by[kind].append(mo)
    if kind == "other miner": takers[t["Ta"]] += 1
for k, v in by.items():
    print(f"taker = {k:12} our fills {len(v):6} ({100 * len(v) / sum(len(x) for x in by.values()):.0f}%)  30 s markout mean {st.mean(v):+.2f}  median {st.median(v):+.2f}")
print("top miner takers of our quotes (uid, fills):", takers.most_common(8))
