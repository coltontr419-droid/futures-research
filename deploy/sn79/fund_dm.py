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
def run(theta, step, half, books, delay=0, sign=1.0, prop=0.0, band=0.2, dm=0.0):
    alpha, notl = {}, {}
    for b in books:
        secs = sorted(mid[b]); 
        if len(secs) < 100: continue
        lo, hi = secs[0], secs[-1]; mlo = lo + (hi - lo) / 2
        secs = [s for s in secs if (s < mlo) == (half == 1)]
        pos = 0.0; mtm = isum = 0.0; n = 0; N = 0.0; prev = None; first = None; ema = None
        for s in secs:
            m = mid[b][s]
            if prev is not None: mtm += pos * (m - prev)
            if first is None: first = m
            if s % step == 0 and (s - delay) in fund[b]:
                u = sign * (fund[b][s - delay] - mid[b][s - delay]) / mid[b][s - delay] * 1e4
                if dm > 0:                                     # de-meaned gap: deviation from its own EMA (half-life dm sim seconds)
                    ema = u if ema is None else ema + (1 - 0.5 ** (step / dm)) * (u - ema); u = u - ema
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



sk = set(map(int, open(sys.argv[2]).read().split())); x1s = set(map(int, open("/opt/mvtrx/sleeve_books_x1.txt").read().split()))
sets = {"all": list(mid), "volatile": [b for b in mid if b in sk], "x1 sleeve": [b for b in mid if b in x1s]}
for name, bs in sets.items():
    for label, kw in (("prop20", dict(prop=20.0)), ("demean 30min prop5", dict(prop=5.0, dm=1800.0)), ("demean 30min prop10", dict(prop=10.0, dm=1800.0)),
                      ("demean 2h prop10", dict(prop=10.0, dm=7200.0)), ("demean 30min p10 REV", dict(prop=10.0, dm=1800.0, sign=-1.0))):
        r1 = run(5, 10, 1, bs, 2, kw.get("sign", 1.0), kw.get("prop", 0.0), 0.2, kw.get("dm", 0.0)); r2 = run(5, 10, 2, bs, 2, kw.get("sign", 1.0), kw.get("prop", 0.0), 0.2, kw.get("dm", 0.0))
        print(f"{name:9} {label:22} | H1 kept {r1[1]:3d} (+{r1[2]:3d}) kappa {r1[3]:+.2f} | H2 kept {r2[1]:3d} (+{r2[2]:3d}) kappa {r2[3]:+.2f}", flush=True)
