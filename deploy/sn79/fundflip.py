"""§1379: how often does sign(fundamental − mid) flip per book (deadband ±0.5 spread)? If it flips often within the validator's 3-sim-h window, a
fund lean's inventory reverses and the per-book buy/sell balance over 3 sim h survives; if it stays one-sided for hours, it doesn't.
Also: share of time each book sits on its majority side within 3-sim-h blocks.   python3 fundflip.py <tape>"""
import json, sys, collections
grp = lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec")
last = {}; flips = collections.Counter(); span = {}; occ = collections.defaultdict(lambda: collections.Counter())
for l in open(sys.argv[1]):
    if '"fund"' not in l or '"bids"' not in l: continue
    i = l.find('"ts": '); t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t < 52500 or t >= 90000: continue
    r = json.loads(l); f, b, a = r.get("fund"), r.get("bid"), r.get("ask")
    if not (f and b and a and a > b): continue
    m = (a + b) / 2; x = (f - m) / (a - b); k = r["book"]
    s = 1 if x > 0.5 else (-1 if x < -0.5 else 0)
    if s == 0: continue
    blk = int(t // 10800); occ[(k, blk)][s] += 1
    if k in last and last[k] != s: flips[k] += 1
    last[k] = s; span.setdefault(k, [t, t]); span[k][1] = t
by = collections.defaultdict(list); maj = collections.defaultdict(list)
for k, (t0, t1) in span.items():
    by[grp(k)].append(flips[k] / max((t1 - t0) / 3600, 1e-9))
for (k, blk), c in occ.items():
    n = sum(c.values())
    if n >= 50: maj[grp(k)].append(max(c.values()) / n)
for g in by:
    v = sorted(by[g]); w = sorted(maj[g]); q = lambda z, p: z[int(p * (len(z) - 1))]
    print(f"{g}: side flips per sim hour median {q(v, .5):.1f} (p25 {q(v, .25):.1f}, p75 {q(v, .75):.1f}) | share of a 3-sim-h block on the majority side: median {q(w, .5):.0%}, p75 {q(w, .75):.0%}")
