"""§1285: x1's ACTUAL entries with a different exit. Every x1 taker fill that grows |inventory| on a book is an entry; under rule H it is closed
H sim s later (synthetic exit at the then mid). Fills that shrink |inventory| are dropped (the rule replaces x1's own exits). Scored with the validator
math of skill_val.py over the last LAST sim min of the CURRENT sim (ts < 60000 s); 'actual' = x1's real inventory path.
    python holdval.py <tape> <uid> <last sim min> <holds s, e.g. 300,600,900,1800>"""
import json, sys, collections, heapq
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_floored, hurdle_filter
tape, ME, LAST = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]); HOLDS = [int(x) for x in sys.argv[4].split(",")]
ev = collections.defaultdict(list); seen = set(); tmax = 0
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)])
    if t >= 60000 * 10 ** 9: continue
    if b'"bid": ' in l[:80]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r.get("bid") and r.get("ask"): ev[r["book"]].append((t, 0, (r["bid"] + r["ask"]) / 2))
    elif b'"Ta": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"), t)
        if k in seen: continue
        seen.add(k); ev[r["book"]].append((t, 1, r)); tmax = max(tmax, t)
t0 = tmax - LAST * 6e10
def run(H):
    alpha, notional = {}, {}
    for b, es in ev.items():
        es.sort(key=lambda e: (e[0], e[1])); mid = None; inv = 0.0; real = 0.0; mtm = isum = drift = 0.0; n = 0; notl = 0.0; prev = None; pend = []
        for ts, kind, x in es:
            if kind == 0:
                mid = x; continue
            r = x; d = (r["q"] if r["s"] == 0 else -r["q"]) if r.get("Ta") == ME else 0.0
            if r.get("Ma") == ME: d += r["q"] if r["s"] == 1 else -r["q"]
            grows = d and abs(real + d) > abs(real); real += d
            if ts < t0: continue
            p = mid if mid is not None else r["p"]
            if prev is not None and p != prev:
                mtm += inv * (p - prev); drift += p - prev
            if H is None:
                if d: notl += abs(d) * p; inv += d
            else:
                while pend and pend[0][0] <= ts:
                    _, dd = heapq.heappop(pend); inv -= dd; notl += abs(dd) * p
                if grows:
                    inv += d; notl += abs(d) * p; heapq.heappush(pend, (ts + H * 1e9, d))
            isum += inv; n += 1; prev = p
        if notl > 0 and n:
            alpha[b] = mtm - isum / n * drift; notional[b] = notl
    kept = hurdle_filter({0: alpha}, {0: notional}, 2.3)[0]
    bp = sorted(1e4 * alpha[b] / notional[b] for b in alpha)
    return len(alpha), len(kept), sum(v > 0 for v in kept.values()), bp[len(bp) // 2] if bp else 0.0, kappa_floored(list(kept.values()), 0.0, 4), sum(alpha.values())
print(f"uid {ME}, last {LAST:.0f} sim min of the current sim")
for H in [None] + HOLDS:
    nb, nk, npos, med, kap, tot = run(H)
    print(f"  {'actual (x1 as it traded)' if H is None else f'same entries, exit after {H} s':32} books {nb:3d} kept {nk:3d} pos {npos:3d} | median α {med:+.2f} bp | kappa {kap:+.3f} | Σα {tot:+8.1f}")
