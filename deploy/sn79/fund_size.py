"""Skill sleeve from the published fundamental (§1211 add. 20): per book per second, gap u = (fund − mid) / mid in bp; position +Q when
u > θ, −Q when u < −θ, else unchanged (hysteresis), checked every STEP s. Validator alpha per book = Σ pos × Δmid (at each second) − mean
pos × drift; notional = Σ |Δpos| × mid. Hurdle 2.3 bp, kappa_floored over kept books; halves of the tape separately.
    python fund_sleeve.py <tape> [skip_file]"""
import json, sys
from collections import defaultdict
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_floored
tape = sys.argv[1]
mid, fund = defaultdict(dict), defaultdict(dict)
for line in open(tape):
    if '"fund"' not in line: continue
    r = json.loads(line)
    if r.get("bid") and r.get("ask") and r.get("fund"):
        s = r["ts"] // 10**9; mid[r["book"]][s] = (r["bid"] + r["ask"]) / 2; fund[r["book"]][s] = r["fund"]
def run(theta, step, half, books, delay=0, sign=1.0):
    alpha, notl = {}, {}
    for b in books:
        secs = sorted(mid[b]); 
        if len(secs) < 100: continue
        lo, hi = secs[0], secs[-1]; mlo = lo + (hi - lo) / 2
        secs = [s for s in secs if (s < mlo) == (half == 1)]
        pos = 0.0; mtm = isum = 0.0; n = 0; N = 0.0; prev = None; first = None
        for s in secs:
            m = mid[b][s]
            if prev is not None: mtm += pos * (m - prev)
            if first is None: first = m
            if s % step == 0 and (s - delay) in fund[b]:
                u = sign * (fund[b][s - delay] - mid[b][s - delay]) / mid[b][s - delay] * 1e4
                tgt = 1.0 if u > theta else (-1.0 if u < -theta else pos)
                N += abs(tgt - pos) * m; pos = tgt
            isum += pos; n += 1; prev = m
        if N > 0 and n:
            alpha[b] = mtm - isum / n * (prev - first); notl[b] = N
    globals()["LAST"] = (alpha, notl)
    kept = [alpha[b] for b in alpha if abs(alpha[b]) >= 2.3e-4 * notl[b]]
    bp = sorted(1e4 * alpha[b] / notl[b] for b in alpha)
    return len(alpha), len(kept), sum(k > 0 for k in kept), kappa_floored(kept, 0.0, 4), (bp[len(bp)//2] if bp else 0)


import statistics as st
sk = set(map(int, open(sys.argv[2]).read().split())); calm = [b for b in mid if b not in sk]
for half in (1, 2):
    run(5, 10, half, calm, 2, 1.0); a, n = LAST
    v = sorted(a.values()); mids_ = [st.median(mid[b].values()) for b in a]
    print(f"half {half}: alpha per book per 1 unit of position over ≈ 140 sim min: median {v[len(v)//2]:+.3f} $, p25 {v[len(v)//4]:+.3f}, positive {sum(x > 0 for x in v)}/{len(v)} | book price median {st.median(mids_):.1f} | sleeve notional/book median {st.median(n.values()):.1f} $ per unit")
