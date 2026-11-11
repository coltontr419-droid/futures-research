"""§1378: size of the fund lean 0.3·|fundamental − mid| in units of the book's spread, by book group, last ≈ 2 wall h of the tape."""
import json, sys, collections, statistics
grp = lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec")
d = collections.defaultdict(list); n = 0
for l in open(sys.argv[1]):
    if '"fund"' not in l or '"bids"' not in l: continue
    i = l.find('"ts": '); t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t < 63300 or t >= 90000: continue
    r = json.loads(l)
    f, b, a = r.get("fund"), r.get("bid"), r.get("ask")
    if not (f and b and a and a > b): continue
    m = (a + b) / 2; d[grp(r["book"])].append(0.3 * abs(f - m) / (a - b))
for g, v in d.items():
    v.sort(); q = lambda p: v[int(p * (len(v) - 1))]
    print(f"{g}: n {len(v)} | 0.3·|f−mid| / spread: median {q(.5):.2f}, p75 {q(.75):.2f}, p90 {q(.9):.2f} | share > 0.5 spread {sum(x > 0.5 for x in v) / len(v):.0%}")
