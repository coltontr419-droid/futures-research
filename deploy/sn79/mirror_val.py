"""§1282: would a DELAYED copy of a taker's exact trades keep its skill? Validator math as skill_val.py (per book α = Σ inv × Δmid at prints − mean
inv × drift, notional = Σ |our trade| × price, 2.3 bp hurdle, kappa floored). The copy: every source trade (Ta == SRC) repeated DELAY sim s later at
K × its size, |position| capped at MAXUSD per book, new exposure through our pace bucket (450k / 86,400 s, burst 900 s; exits always go).
Current sim only (ts < 90000 s), last LAST sim min.   python mirror_val.py <tape> <src uid> <last sim min> <delays e.g. 0,2,5,10> [K] [MAXUSD]"""
import json, sys, collections, heapq
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_floored, hurdle_filter
tape, SRC, LAST = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]); DL = [float(x) for x in sys.argv[4].split(",")]
K = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0; MAXUSD = float(sys.argv[6]) if len(sys.argv) > 6 else 1e12
ev = collections.defaultdict(list); seen = set(); tmax = 0
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)])
    if t >= 90000 * 10 ** 9: continue
    if b'"bid": ' in l[:80]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r.get("bid") and r.get("ask"): ev[r["book"]].append((t, 0, (r["bid"] + r["ask"]) / 2))
    elif b'"Ta": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"), t)
        if k in seen: continue
        seen.add(k); ev[r["book"]].append((t, 1, r)); tmax = max(tmax, t)
t0 = tmax - LAST * 6e10
RATE, BURST = 450000 / 86400, 450000 / 86400 * 900
def run(delay, k, maxusd, pace):
    alpha, notional = {}, {}
    for b, es in ev.items():
        es.sort(key=lambda e: (e[0], e[1])); mid = None; inv = 0.0; mtm = isum = drift = 0.0; n = 0; notl = 0.0; prev = None
        pend = []; tok = BURST; tlast = None
        for ts, kind, x in es:
            if kind == 0:
                mid = x
                if ts < t0: continue
            else:
                r = x
                if r.get("Ta") == SRC and ts >= t0:
                    heapq.heappush(pend, (ts + delay * 1e9, (1 if r["s"] == 0 else -1) * r["q"] * k))
                if ts < t0: continue
                p = mid if mid is not None else r["p"]
                if prev is not None and p != prev:
                    mtm += inv * (p - prev); drift += p - prev
                while pend and pend[0][0] <= ts:          # our copied trades that are due by this print
                    _, d = heapq.heappop(pend)
                    if pace:
                        if tlast is not None: tok = min(BURST, tok + (ts - tlast) / 1e9 * RATE) if tok < BURST else tok
                        tlast = ts
                    new = inv + d
                    if abs(new) * p > maxusd: new = (1 if new > 0 else -1) * maxusd / p
                    if pace and abs(new) > abs(inv) and tok <= 0: new = inv     # paced out: no new exposure (exits still go)
                    dd = new - inv
                    if dd:
                        notl += abs(dd) * p; inv = new
                        if pace: tok -= abs(dd) * p
                isum += inv; n += 1; prev = p
        if notl > 0 and n:
            alpha[b] = mtm - isum / n * drift; notional[b] = notl
    kept = hurdle_filter({0: alpha}, {0: notional}, 2.3)[0]
    bp = sorted(1e4 * alpha[b] / notional[b] for b in alpha)
    return len(alpha), len(kept), sum(v > 0 for v in kept.values()), bp[len(bp) // 2] if bp else 0.0, kappa_floored(list(kept.values()), 0.0, 4)
print(f"source uid {SRC}, last {LAST:.0f} sim min of the current sim | copy K {K}, max ${MAXUSD:,.0f} per book")
RUNS = [("source itself (delay 0, own size, no limits)", 0, 1.0, 1e12, False)] + [(f"copy, delay {d:g} s, paced, capped", d, K, MAXUSD, True) for d in DL]
if "--raw" in sys.argv: RUNS = [("source itself (delay 0, own size, no limits)", 0, 1.0, 1e12, False)] + [(f"copy, delay {d:g} s, NO pace, NO cap, full size", d, 1.0, 1e12, False) for d in DL]
for name, d, k, mx, pc in RUNS:
    nb, nk, npos, med, kap = run(d, k, mx, pc)
    print(f"  {name:45} books {nb:3d} kept {nk:3d} pos {npos:3d} | median α {med:+.2f} bp | kappa {kap:+.3f}")
