"""§1447: the validator's OWN 0.6.7 making credit, offline, from our tape (read-only). accumulate_book_capture (captured + realized at the 20-s horizon,
fee netting 0.005 × Mf, centred window 15, taker legs booked apart) → maker captured = captured − taker legs → markout_quality (ONE factor per uid over
ALL books) → per class Σ_book 2·min(buy, sell) × quality.   python making067.py <tape1,tape2> <last sim min> uid ...  (offline batch mode: mid_state=None)"""
import json, sys
from collections import defaultdict
sys.path.insert(0, "/opt/mvtrx/repo067")
from taos.im.validator.debeta import accumulate_book_capture, markout_quality
try:
    from taos.im.validator.trade import fee_complete_sides
except Exception:
    fee_complete_sides = lambda t: t
tapes, last = sys.argv[1].split(","), float(sys.argv[2]); U = [int(u) for u in sys.argv[3:]]
books = defaultdict(list); seen = set()
f = open(tapes[-1], "rb"); f.seek(-200000, 2); tail = f.read().split(b"\n")[1:-1]
tmax = max(json.loads(l).get("ts", 0) for l in tail if l.strip())
t0 = tmax - last * 6e10; KEEP = ("p", "q", "s", "Ma", "Ta", "Mf", "Tf", "ts", "id")
for path in tapes:
    for line in open(path):
        if '"Ma"' not in line: continue
        i = line.find('"ts": '); ts = int(line[i + 6:line.index(",", i)])
        if ts < t0: continue
        r = json.loads(line); k = (r["book"], r.get("id"), ts)
        if k in seen: continue
        seen.add(k); books[r["book"]].append(tuple(r.get(x) for x in KEEP))
cb, cs, rb, rs, tb, tsell = (defaultdict(dict) for _ in range(6))
seen = None
for b in list(books):
    tr = [{x: v for x, v in zip(KEEP, row) if v is not None} for row in books.pop(b)]
    tr.sort(key=lambda x: (x["ts"], x.get("id", 0)))
    tr = [x for x in map(fee_complete_sides, tr) if x is not None]
    if not tr: continue
    accumulate_book_capture(cb, cs, b, tr, 15, real_buy_sums=rb, real_sell_sums=rs, horizon_ns=20_000_000_000,
                            min_size=0.0, fee_weight=0.005, market_votes=False, taker=(tb, tsell, None, None))
def less(pair, legs):
    return {u: {b: v - (legs.get(u) or {}).get(b, 0.0) for b, v in bk.items()} for u, bk in pair.items()}
mcb, mcs = less(cb, tb), less(cs, tsell)
q = markout_quality(mcb, mcs, rb, rs, U)
cls = lambda b: 0 if b < 128 else (1 if b < 192 else 2)
U = sorted(set(mcb) | set(mcs)); q = markout_quality(mcb, mcs, rb, rs, U)
tot = {c: 0.0 for c in range(3)}; per = {c: {} for c in range(3)}
for u in U:
    for b in set(mcb.get(u, {})) | set(mcs.get(u, {})):
        c = cls(b); bb, ss = mcb.get(u, {}).get(b, 0.0), mcs.get(u, {}).get(b, 0.0)
        cr = max(0.0, 2.0 * min(bb, ss)) * q.get(u, 0)
        tot[c] += cr; per[c][u] = per[c].get(u, 0.0) + cr
print(f"FIELD making credit by class, last {last:.0f} sim min:")
for c, n in enumerate(["$300", "$30", "4dec"]):
    top = sorted(per[c].items(), key=lambda x: -x[1])[:8]
    print(f"  {n}: total {tot[c]:8.1f} | uids with credit {sum(1 for v in per[c].values() if v > 0)} | top {[(u, round(v, 1)) for u, v in top]}")
