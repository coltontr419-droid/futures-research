"""Do our losses come from piling inventory into trends? (decisions.md §1199) Rebuild our per-book position from our own maker fills
(cumulative signed size since tape start) and split 30 s markouts by the position held, in the fill's direction, when the fill happened."""
import bisect, json, statistics as st, sys
from collections import defaultdict
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
fills.sort(key=lambda t: t["ts"]); pos = defaultdict(float); rows = []
for t in fills:
    side = 1 if t["s"] == 1 else -1                       # +1 we bought
    held = pos[t["book"]] * side                           # >0: this fill adds to a position already on in the same direction
    later = mid_at(t["book"], t["ts"] / 1e9 + 30)
    if later is not None:
        rows.append((held, side * (later - t["p"]) / 0.01, t["q"]))
    pos[t["book"]] += side * t["q"]
tot = sum(mo * q for _, mo, q in rows)
for lo, hi, lab in ((-1e9, 0, "reducing / flat"), (0, 5, "adding, held 0-5"), (5, 15, "adding, held 5-15"), (15, 1e9, "adding, held 15+")):
    g = [(mo, q) for h, mo, q in rows if lo < h <= hi] if lo > -1e9 else [(mo, q) for h, mo, q in rows if h <= 0]
    if g:
        pnl = sum(mo * q for mo, q in g)
        print(f"{lab:20} fills {len(g):6}  mean markout {st.mean(m for m, _ in g):+6.2f} ticks  share of size-weighted loss {100 * pnl / tot:5.0f}%")
print("max |position| reached on any book:", round(max(abs(v) for v in pos.values()), 1), "| books ending with |position| > 15:", sum(1 for v in pos.values() if abs(v) > 15))
