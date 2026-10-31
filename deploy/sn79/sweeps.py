"""Which taker orders hit our quotes vs other miners' (decisions.md §1199): sweep size, levels, makers hit, and 30 s markout by taker size."""
import bisect, json, statistics as st, sys
from collections import defaultdict
sweeps = defaultdict(list); mids = defaultdict(list)
for line in open(sys.argv[1]):
    r = json.loads(line)
    if "p" in r: sweeps[(r["book"], r["ts"], r["Ta"], r["s"])].append(r)
    elif r.get("bid") and r.get("ask"): mids[r["book"]].append((r["ts"] / 1e9, (r["bid"] + r["ask"]) / 2))
for b in mids: mids[b].sort()
secs = {b: [t for t, _ in v] for b, v in mids.items()}
def mid_at(b, t):
    i = bisect.bisect_left(secs[b], t); return mids[b][i][1] if i < len(secs[b]) else None
grp = {"ours": [], "other miners": [], "background": []}
for key, trs in sweeps.items():
    total = sum(t["q"] for t in trs); levels = len({t["p"] for t in trs}); makers = len(trs)
    for t in trs:
        g = "ours" if t["Ma"] == int(sys.argv[2]) else ("other miners" if t["Ma"] is not None and t["Ma"] >= 0 else "background")
        side = 1 if t["s"] == 1 else -1; later = mid_at(t["book"], t["ts"] / 1e9 + 30)
        grp[g].append((total, levels, makers, t["q"], side * (later - t["p"]) / 0.01 if later is not None else None))
print(f"{'maker group':14} {'fills':>7} {'taker size med / mean':>22} {'levels med':>11} {'makers med':>11} {'30s markout':>12}")
for g, v in grp.items():
    if v:
        mo = [x[4] for x in v if x[4] is not None]
        print(f"{g:14} {len(v):7} {st.median(x[0] for x in v):10.2f} / {st.mean(x[0] for x in v):8.2f} {st.median(x[1] for x in v):11} {st.median(x[2] for x in v):11} {st.mean(mo):+12.2f}")
for lo, hi in ((0, 2), (2, 5), (5, 15), (15, float("inf"))):
    a = [x[4] for x in grp["ours"] if x[4] is not None and lo <= x[0] < hi]
    o = [x[4] for x in grp["other miners"] if x[4] is not None and lo <= x[0] < hi]
    if a and o:
        print(f"taker size {lo:>3} to {hi:>4}: ours {len(a):6} fills, markout {st.mean(a):+6.2f} | other miners {len(o):6} fills, markout {st.mean(o):+6.2f}")
