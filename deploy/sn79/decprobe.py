"""§1313: the long-lived fleet's 4-decimal-book (102-127) quoting, from its fills. python3 decprobe.py <tape> <T0> <T1> <fleet uids>"""
import json, sys, collections, statistics as stt
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); FL = {int(u) for u in sys.argv[4].split(",")}
SN = collections.defaultdict(dict); F = []; SPR = []
for l in open(tape, "rb"):
    if b'"book": 1' not in l: continue
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < T0 - 30 or t > T1 + 30: continue
    r = json.loads(l)
    if r.get("book", 0) < 102: continue
    if "Mi" in r:
        if r["Ma"] in FL and r["Ma"] != r["Ta"] and T0 <= t < T1: F.append((t, r["book"], r["p"], r["q"], r["s"], r["Ma"], r["Mi"]))
    elif "bids" in r and r["bids"] and r["asks"]:
        SN[r["book"]][int(t)] = (r["bid"], r["ask"]); SPR.append(round((r["ask"] - r["bid"]) / 0.0001))
SPR.sort(); print(f"4-dec spread in ticks: p10 {SPR[len(SPR)//10]} median {SPR[len(SPR)//2]} p90 {SPR[9*len(SPR)//10]} | price e.g. {next(iter(SN[110].values()))}")
dep = collections.Counter(); usd = collections.Counter(); per_o = collections.defaultdict(float); o_dep = {}; spr_at = collections.defaultdict(list); kept = collections.defaultdict(float)
for t, b, p, q, s, u, mi in F:
    sn = SN[b].get(int(t) - 1); later = SN[b].get(int(t) + 20)
    if not sn or not later: continue
    buy = s == 1; d = round(((sn[0] - p) if buy else (p - sn[1])) / 0.0001); sp = round((sn[1] - sn[0]) / 0.0001)
    k = "in-%d" % -d if d < 0 else ("touch" if d == 0 else ("1-4" if d < 5 else ("5-9" if d < 10 else ("10-19" if d < 20 else "20+"))))
    if d < -3: k = "in-4+"
    dep[k] += 1; usd[k] += p * q; per_o[(u, b, mi)] += p * q; o_dep[(u, b, mi)] = k; spr_at[k].append(sp)
    mid2 = (later[0] + later[1]) / 2; kept[k] += (1 if buy else -1) * (mid2 - p) / ((sn[0] + sn[1]) / 2) * 1e4 * p * q
D = sum(usd.values())
for k in ("in-4+", "in-3", "in-2", "in-1", "touch", "1-4", "5-9", "10-19", "20+"):
    if not usd[k]: continue
    osz = sorted(v for kk, v in per_o.items() if o_dep[kk] == k)
    print(f"{k:6s} {usd[k] / D:5.1%} of $ | fills {dep[k]:5d} | filled $/order median {stt.median(osz):6,.0f} | spread at fill median {stt.median(spr_at[k])} ticks | kept {kept[k] / usd[k]:+.2f} bp")
fr_in, fr_deep = [], []
for t, b, p, q, s, u, mi in F:
    sn = SN[b].get(int(t) - 1)
    if not sn: continue
    buy = s == 1; d = ((sn[0] - p) if buy else (p - sn[1])); sp = sn[1] - sn[0]
    if sp <= 0: continue
    if d < -3 * 0.0001: fr_in.append((-d / sp, p * q))
    elif d >= 20 * 0.0001: fr_deep.append((d / sp, p * q))
def q_(v, x):
    v = sorted(v); tot = sum(w for _, w in v); c = 0
    for f, w in v:
        c += w
        if c >= x * tot: return f
print("further-inside fills: distance inside, as a share of the spread  p25 %.2f median %.2f p75 %.2f" % (q_(fr_in, .25), q_(fr_in, .5), q_(fr_in, .75)))
print("deep fills: distance behind the touch, in spreads             p25 %.2f median %.2f p75 %.2f p90 %.2f" % (q_(fr_deep, .25), q_(fr_deep, .5), q_(fr_deep, .75), q_(fr_deep, .9)))
