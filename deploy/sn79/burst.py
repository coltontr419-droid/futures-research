"""§1381: WHEN do the top makers trade? For each maker fill: the book's spread (bp) and |mid move| over the previous 60 s (bp) at fill time, and whether
the fundamental moved > 0.5 spread in the last 10 s. Notional share by bucket, x3 vs the top makers (48,178,119,117,5,146) vs 216. Book groups separately."""
import json, sys, collections, bisect
TOP = {48, 178, 119, 117, 5, 146}; WHO = lambda u: "x3" if u == 64 else ("top" if u in TOP else ("216" if u == 216 else None))
grp = lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec")
bk = collections.defaultdict(list)   # book -> [(t, mid, spread_bp, fund)]
fills = []
for l in open(sys.argv[1]):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t < 52000 or t >= 90000: continue
    if '"bids"' in l:
        r = json.loads(l); b, a = r.get("bid"), r.get("ask")
        if b and a and a > b: m = (a + b) / 2; bk[r["book"]].append((t, m, (a - b) / m * 1e4, r.get("fund") or 0.0, a - b))
    elif '"Ma"' in l:
        r = json.loads(l); w = WHO(r["Ma"])
        if w: fills.append((t, r["book"], w, r["p"] * r["q"]))
T = {k: [x[0] for x in v] for k, v in bk.items()}
agg = collections.defaultdict(lambda: collections.defaultdict(float)); tot = collections.defaultdict(float)
for t, b, w, x in fills:
    v = bk.get(b); 
    if not v: continue
    j = bisect.bisect_right(T[b], t) - 1; j0 = bisect.bisect_left(T[b], t - 60); jf = bisect.bisect_left(T[b], t - 10)
    if j < 0 or j0 >= j: continue
    _, m, sp, f, spa = v[j]; mv = abs(m - v[j0][1]) / m * 1e4; df = abs(f - v[jf][3]) / spa if spa else 0
    g = grp(b); k = (g, w)
    sb = "spread ≤2bp" if sp <= 2 else ("2-5bp" if sp <= 5 else ("5-10bp" if sp <= 10 else ">10bp"))
    vb = "move60 <5bp" if mv < 5 else ("5-20bp" if mv < 20 else ">20bp")
    agg[k][sb] += x; agg[k][vb] += x; agg[k]["Δf>0.5spr" if df > 0.5 else "Δf quiet"] += x; tot[k] += x
for g in ("$300", "calm", "4dec"):
    print(f"== {g}: share of maker notional by state at fill time")
    keys = ["spread ≤2bp", "2-5bp", "5-10bp", ">10bp", "move60 <5bp", "5-20bp", ">20bp", "Δf>0.5spr"]
    print("        " + " | ".join(f"{k:>11s}" for k in keys))
    for w in ("x3", "216", "top"):
        k = (g, w)
        if tot[k]: print(f"  {w:4s}  " + " | ".join(f"{100 * agg[k][kk] / tot[k]:10.0f}%" for kk in keys) + f"   (${tot[k]/1e6:.1f}M)")
