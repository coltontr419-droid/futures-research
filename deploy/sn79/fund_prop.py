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
def run(theta, step, half, books, delay=0, sign=1.0, prop=0.0, band=0.2):
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
                if prop > 0:                                  # proportional: target = clip(u / prop, -1, 1); trade only beyond a band
                    tgt = max(-1.0, min(1.0, u / prop))
                    if abs(tgt - pos) < band: tgt = pos
                else:
                    tgt = 1.0 if u > theta else (-1.0 if u < -theta else pos)
                N += abs(tgt - pos) * m; pos = tgt
            isum += pos; n += 1; prev = m
        if N > 0 and n:
            alpha[b] = mtm - isum / n * (prev - first); notl[b] = N
    kept = [alpha[b] for b in alpha if abs(alpha[b]) >= 2.3e-4 * notl[b]]
    bp = sorted(1e4 * alpha[b] / notl[b] for b in alpha)
    return len(alpha), len(kept), sum(k > 0 for k in kept), kappa_floored(kept, 0.0, 4), (bp[len(bp)//2] if bp else 0)


sk = set(map(int, open(sys.argv[2]).read().split()))
sets = {"all": list(mid), "calm": [b for b in mid if b not in sk], "skipped": [b for b in mid if b in sk]}
for name, bs in sets.items():
    for label, kw in (("threshold 5bp", dict()), ("prop 10bp", dict(prop=10.0)), ("prop 20bp", dict(prop=20.0)), ("prop 50bp", dict(prop=50.0)),
                      ("prop 20bp REVERSED", dict(prop=20.0, sign=-1.0))):
        r1, r2 = run(5, 10, 1, bs, 2, kw.get("sign", 1.0), kw.get("prop", 0.0)), run(5, 10, 2, bs, 2, kw.get("sign", 1.0), kw.get("prop", 0.0))
        print(f"{name:7} {label:20} delay 2s | H1 kept {r1[1]:3d} (+{r1[2]:3d}) kappa {r1[3]:+.2f} med {r1[4]:+.2f}bp | H2 kept {r2[1]:3d} (+{r2[2]:3d}) kappa {r2[3]:+.2f} med {r2[4]:+.2f}bp", flush=True)
