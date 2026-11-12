"""§1403: the new sim day has 256 books. Profile every book in the new sim: mid, tick, spread (ticks, bp), 1-min |mid move| bp, trades $, and maker $ of x3 / x1 / 46 / 216.
Groups books by (price band, tick decimals) so new groups can be named."""
import json, sys, collections, statistics as st
U = {64: "x3", 27: "x1", 46: "46", 216: "216"}
mids = collections.defaultdict(list); tk = {}; sp = collections.defaultdict(list); trades = collections.defaultdict(float); mk = collections.defaultdict(lambda: collections.defaultdict(float))
for l in open(sys.argv[1]):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t > 30000: continue                       # new sim only
    if '"bids"' in l:
        r = json.loads(l); bb = r.get("bids") or []; aa = r.get("asks") or []
        if not (bb and aa): continue
        b = r["book"]; m = (bb[0][0] + aa[0][0]) / 2
        if len(mids[b]) < 4000: mids[b].append((t, m))
        px = [x[0] for x in bb[:5]] + [x[0] for x in aa[:5]]
        d = [round(abs(a - c), 8) for a, c in zip(px, px[1:]) if abs(a - c) > 1e-9]
        if d: tk[b] = min(d + ([tk[b]] if b in tk else []))
        sp[b].append((aa[0][0] - bb[0][0]))
    elif '"Ma"' in l:
        r = json.loads(l); v = r["p"] * r["q"]; trades[r["book"]] += v
        if r["Ma"] in U: mk[r["book"]][U[r["Ma"]]] += v
rows = []
for b in sorted(mids):
    ms = mids[b]; m = st.median(x[1] for x in ms); t_ = tk.get(b, 0) or 0; s = st.median(sp[b]) if sp[b] else 0
    mv = [abs(ms[j][1] - ms[j - 1][1]) / ms[j - 1][1] * 1e4 for j in range(1, len(ms)) if ms[j][0] - ms[j - 1][0] >= 50]
    dec = max(0, -int(round(__import__("math").log10(t_)))) if t_ > 0 else -1
    rows.append((b, m, t_, dec, s / t_ if t_ else 0, s / m * 1e4, st.median(mv) if mv else 0, trades[b], mk[b]))
band = lambda m: "$25-50" if m < 50 else ("$50-150" if m < 150 else ("$150-250" if m < 250 else "$250+"))
G = collections.defaultdict(list)
for r in rows: G[("old " if r[0] < 128 else "NEW ") + band(r[1]) + f" {r[3]}dec"].append(r)
print("group: books | mid | spread ticks / bp | 1-min move bp | trades $ (all makers) | maker $ x3 / x1 / 46 / 216")
for g, rs in sorted(G.items()):
    f = lambda k: st.median([x[k] for x in rs])
    tot = lambda w: sum(x[8].get(w, 0) for x in rs) / 1e3
    print(f"{g:22s}: {len(rs):3d} | {f(1):8.2f} | {f(4):5.1f} / {f(5):5.1f} | {f(6):5.1f} | ${sum(x[7] for x in rs)/1e6:6.1f}M | ${tot('x3'):6.0f}k / ${tot('x1'):6.0f}k / ${tot('46'):6.0f}k / ${tot('216'):6.0f}k  ids {rs[0][0]}-{rs[-1][0]}")
