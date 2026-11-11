"""§1380: maker notional per book over the last 3 sim h (and scaled to 24 sim h) for x3 vs the top makers; the validator caps 500k per book per 24 sim h."""
import json, sys, collections
U = [64, 48, 178, 119, 117, 5, 146, 91, 216]; E = None
rows = []
for l in open(sys.argv[1]):
    if '"Ma"' not in l: continue
    r = json.loads(l); t = r["ts"] / 1e9
    if t >= 90000: continue
    rows.append((t, r["Ma"], r["Ta"], r["book"], r["p"] * r["q"]))
E = max(x[0] for x in rows); S = E - 10800
v = collections.defaultdict(lambda: collections.defaultdict(float)); n = collections.Counter(); tk = collections.defaultdict(lambda: collections.defaultdict(float))
for t, ma, ta, b, x in rows:
    if t < S: continue
    if ma in U: v[ma][b] += x; n[ma] += 1
    if ta in U: tk[ta][b] += x
grp = lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec")
print(f"window sim {S:.0f}-{E:.0f}")
for u in U:
    per = sorted(v[u].values(), reverse=True); tot = sum(per)
    g = collections.defaultdict(float)
    for b, x in v[u].items(): g[grp(b)] += x
    tkt = sum(tk[u].values())
    print(f"UID {u:3d}: maker fills {n[u]:5d} | maker ${tot/1e3:7.0f}k over {len(per):3d} books | per book median ${per[len(per)//2]/1e3 if per else 0:5.1f}k max ${per[0]/1e3 if per else 0:5.1f}k "
          f"(×8 = 24 sim h: median ${8*per[len(per)//2]/1e3 if per else 0:4.0f}k) | $300 {g['$300']/1e3:5.0f}k calm {g['calm']/1e3:5.0f}k 4dec {g['4dec']/1e3:5.0f}k | taker ${tkt/1e3:.0f}k | avg fill ${tot/max(n[u],1):,.0f}")
