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
print(f"validator 0.6.7 making replica, last {last:.0f} sim min (sim {t0/1e9:.0f}-{tmax/1e9:.0f} s)")
for u in U:
    C = {c: 0.0 for c in range(3)}; R = {c: 0.0 for c in range(3)}; cred = {c: 0.0 for c in range(3)}; nb = {c: 0 for c in range(3)}
    for b in set(mcb.get(u, {})) | set(mcs.get(u, {})):
        c = cls(b); bb, ss = mcb.get(u, {}).get(b, 0.0), mcs.get(u, {}).get(b, 0.0)
        C[c] += bb + ss; R[c] += rb.get(u, {}).get(b, 0.0) + rs.get(u, {}).get(b, 0.0)
        cred[c] += 2.0 * min(bb, ss); nb[c] += 1
    print(f"uid {u:3d}: QUALITY (R/C over all books, clamp 0-1) {q.get(u, 0):.3f}")
    for c, n in enumerate(["$300", "$30", "4dec"]):
        print(f"   {n:4s}: books {nb[c]:3d} | captured C {C[c]:8.1f} | realized R {R[c]:+8.1f} (R/C {R[c]/C[c] if C[c] else 0:+.2f}) | two-sided {max(0, cred[c]):7.1f} → credit {max(0, cred[c]) * q.get(u, 0):6.1f}")
    tC, tR = sum(C.values()), sum(R.values())
    print(f"   all : C {tC:.1f} R {tR:+.1f} → quality {min(1, max(0, tR / tC)) if tC > 0 else 0:.3f}")
