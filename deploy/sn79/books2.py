"""§1403: per-book spread (bp, ticks), mid and decimals in the NEW sim, summarised per id range of 8 books, + our makers' $ per range."""
import json, sys, collections, statistics as st, math
sp = collections.defaultdict(list); tk = {}; mid = {}; mk = collections.defaultdict(lambda: collections.defaultdict(float))
for l in open(sys.argv[1]):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t > 30000: continue
    if '"bids"' in l:
        r = json.loads(l); bb = r.get("bids") or []; aa = r.get("asks") or []
        if not (bb and aa): continue
        b = r["book"]; m = (bb[0][0] + aa[0][0]) / 2; mid[b] = m
        if len(sp[b]) < 3000: sp[b].append((aa[0][0] - bb[0][0]) / m * 1e4)
        px = [x[0] for x in bb[:5]] + [x[0] for x in aa[:5]]
        d = [round(abs(a - c), 8) for a, c in zip(px, px[1:]) if abs(a - c) > 1e-9]
        if d: tk[b] = min(d + ([tk[b]] if b in tk else []))
    elif '"Ma": 64,' in l or '"Ma": 27,' in l:
        r = json.loads(l); mk[r["book"] // 8]["x3" if r["Ma"] == 64 else "x1"] += r["p"] * r["q"]
for k in range(32):
    bs = [b for b in range(k * 8, k * 8 + 8) if sp.get(b)]
    if not bs: continue
    s = st.median([st.median(sp[b]) for b in bs]); m = st.median([mid[b] for b in bs]); d = st.median([max(0, -round(math.log10(tk[b]))) for b in bs if tk.get(b)])
    print(f"books {k*8:3d}-{k*8+7:3d}: mid {m:8.2f} | dec {d} | spread median {s:5.2f} bp | x3 ${mk[k]['x3']/1e3:5.0f}k x1 ${mk[k]['x1']/1e3:5.0f}k")
