"""SN79: do miners that TAKE liquidity make money? (§1211 addendum 5). Every trade with a miner taker (Ta >= 0) on a tape, 30 s markout
from the taker's side (ticks, vs the quoted mid), per taker uid and in total, split by whose order was taken (ours vs others).

    python taker_profile.py <tape.jsonl> <our uid>
"""
import bisect
import json
import sys
from collections import defaultdict

import numpy as np

tape, me = sys.argv[1], int(sys.argv[2])
mids, trades = defaultdict(list), []
for line in open(tape):
    r = json.loads(line)
    if "p" in r and r.get("Ta") is not None and r["Ta"] >= 0:
        trades.append(r)
    elif r.get("bid") and r.get("ask"):
        mids[r["book"]].append((r["ts"] / 1e9, (r["bid"] + r["ask"]) / 2))
by, vs = defaultdict(list), defaultdict(list)
for t in trades:
    ms = mids[t["book"]]; i = bisect.bisect_left(ms, (t["ts"] / 1e9 + 30,))
    if i >= len(ms):
        continue
    taker = -1 if t["s"] == 1 else 1                      # s = maker side (field_split: maker = +1 when s == 1), taker is the other side
    mo = taker * (ms[i][1] - t["p"]) / 0.01
    by[t["Ta"]].append((mo, t["q"])); vs["ours" if t.get("Ma") == me else "others' orders"].append(mo)
allm = np.array([m for v in by.values() for m, _ in v])
print(f"miner-taker trades {len(allm)} by {len(by)} takers | taker markout mean {allm.mean():+.2f} ticks, median {np.median(allm):+.2f}")
for k, v in vs.items():
    print(f"   taking {k:15}: {len(v):6d} trades, taker markout {np.mean(v):+.2f}")
rows = sorted(((u, len(v), np.mean([m for m, _ in v]), sum(m * q for m, q in v)) for u, v in by.items() if len(v) >= 30), key=lambda r: -r[3])
pos = [r for r in rows if r[2] > 0]
print(f"takers with >= 30 trades: {len(rows)}, of which positive on average: {len(pos)}")
print("best takers by size-weighted total: uid, trades, mean markout, total (ticks·units)")
for r in rows[:6]:
    print(f"   {r[0]:4d} {r[1]:6d} {r[2]:+6.2f} {r[3]:+10.0f}")
