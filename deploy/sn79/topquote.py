"""§1382: HOW do the top makers quote? Reconstructed from their fills (resting orders are anonymous; fills carry Ma).
Per fill: depth = ticks behind the pre-trade touch on the maker's side (0 = at the touch, <0 = inside / price improvement), fill $ and qty,
and 'order' = all fills of one maker on one book/side/price within 2 sim s (≈ one resting order). Per book: share of sim minutes with a fill (presence).
Also the cap behaviour: per-book fill rate before vs after the book's cumulative tape notional passes $450k / $500k.   python3 topquote.py <tape>"""
import json, sys, collections, bisect, statistics as stt
TOP = {48, 178, 119, 117, 5, 146}; WHO = lambda u: "x3" if u == 64 else ("top" if u in TOP else ("216" if u == 216 else None))
grp = lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec")
snap = {}; tick = {}
D = collections.defaultdict(list); SZ = collections.defaultdict(list); ORD = collections.defaultdict(list)
cur = {}; mins = collections.defaultdict(set); span = [None, 0]; cum = collections.defaultdict(float); rate = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
first = {}
def fl(k):
    if k in cur:
        o = cur.pop(k); ORD[(grp(k[1]), WHO(k[0]))].append(o)
for l in open(sys.argv[1]):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t < 34000 or t >= 90000: continue
    if '"bids"' in l:
        r = json.loads(l); bb = r.get("bids") or []; aa = r.get("asks") or []
        if bb and aa:
            snap[r["book"]] = (bb[0][0], aa[0][0])
            px = [x[0] for x in bb[:5]] + [x[0] for x in aa[:5]]
            d = [round(abs(a - b), 8) for a, b in zip(px, px[1:]) if abs(a - b) > 1e-9]
            if d: tick[r["book"]] = min(d + ([tick[r["book"]]] if r["book"] in tick else []))
        continue
    if '"Ma"' not in l: continue
    r = json.loads(l); u = r["Ma"]; w = WHO(u)
    if not w: continue
    b = r["book"]; g = grp(b); x = r["p"] * r["q"]
    span[0] = t if span[0] is None else span[0]; span[1] = t
    mins[(u, b)].add(int(t // 60))
    s = snap.get(b); tk = tick.get(b)
    if s and tk:
        mside_bid = r["s"] == 1                          # taker sold into the maker's bid
        ref = s[0] if mside_bid else s[1]
        dep = (ref - r["p"]) / tk if mside_bid else (r["p"] - ref) / tk
        D[(g, w)].append(round(dep))
    SZ[(g, w)].append(x)
    k = (u, b, r["s"], r["p"])
    if k in cur and t - cur[k][1] <= 2: cur[k] = (cur[k][0] + x, t)
    else:
        fl(k); cur[k] = (x, t)
    c0 = cum[(u, b)]; cum[(u, b)] += x
    j = 0 if c0 < 450000 else (1 if c0 < 500000 else 2)
    rate[(w, g)][j] += x
    if c0 < 500000 <= cum[(u, b)]: first[(u, b)] = t
for k in list(cur): fl(k)
q = lambda a, p: sorted(a)[int(p * (len(a) - 1))] if a else float("nan")
print(f"tape fills sim {span[0]:.0f}-{span[1]:.0f}")
for g in ("$300", "calm", "4dec"):
    print(f"== {g}")
    for w in ("x3", "216", "top"):
        d = D[(g, w)]; n = len(d) or 1
        bins = [sum(1 for v in d if v < 0), sum(1 for v in d if v == 0), sum(1 for v in d if v == 1), sum(1 for v in d if 2 <= v <= 4), sum(1 for v in d if 5 <= v <= 9), sum(1 for v in d if 10 <= v <= 19), sum(1 for v in d if v >= 20)]
        o = [v[0] for v in ORD[(g, w)]]
        print(f"  {w:4s} fills {len(d):6d} | depth ticks: inside {100*bins[0]/n:3.0f}% | 0 {100*bins[1]/n:3.0f}% | 1 {100*bins[2]/n:3.0f}% | 2-4 {100*bins[3]/n:3.0f}% | 5-9 {100*bins[4]/n:3.0f}% | 10-19 {100*bins[5]/n:3.0f}% | 20+ {100*bins[6]/n:3.0f}%"
              f" | fill $ med {q(SZ[(g, w)], .5):,.0f} p90 {q(SZ[(g, w)], .9):,.0f} | order $ med {q(o, .5):,.0f} p90 {q(o, .9):,.0f} max {max(o) if o else 0:,.0f}")
mspan = (span[1] - span[0]) / 60
for w, U in (("x3", [64]), ("216", [216]), ("top", sorted(TOP))):
    pres = [len(mins[(u, b)]) / mspan for u in U for b in range(128)]
    print(f"presence {w}: share of sim minutes with ≥ 1 fill per book: median {q(pres, .5):.0%} p90 {q(pres, .9):.0%}")
for w in ("x3", "216", "top"):
    for g in ("$300", "calm", "4dec"):
        a = rate[(w, g)]
        print(f"cap check {w} {g}: notional while book cum < $450k ${a[0]/1e6:.1f}M | 450-500k ${a[1]/1e6:.2f}M | past $500k ${a[2]/1e6:.2f}M")
print("books passing $500k on the tape (top makers):", sum(1 for (u, b) in first if u in TOP), "| first passes at sim", sorted(int(v) for (u, b), v in first.items() if u in TOP)[:5])
