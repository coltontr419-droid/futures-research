"""§1382: UID 46's quoting in detail: depth in ticks AND in spreads (pre-trade), order $ (fills on one book/side/price within 2 s), per book group; x3 alongside."""
import json, sys, collections
grp = lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec")
snap = {}; tick = {}; R = collections.defaultdict(list); cur = {}; O = collections.defaultdict(list)
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
    r = json.loads(l); u = r["Ma"]
    if u not in (46, 64): continue
    b = r["book"]; s = snap.get(b); tk = tick.get(b)
    if not (s and tk): continue
    bid = r["s"] == 1; ref = s[0] if bid else s[1]; sp = s[1] - s[0]
    dt = ((ref - r["p"]) if bid else (r["p"] - ref)) / tk; ds = dt * tk / sp if sp > 0 else 0
    R[(grp(b), u)].append((dt, ds, r["p"] * r["q"], sp / tk))
    k = (u, b, r["s"], r["p"])
    if k in cur and t - cur[k][1] <= 2: cur[k] = (cur[k][0] + r["p"] * r["q"], t, cur[k][2])
    else:
        if k in cur: O[(grp(b), u, cur[k][2])].append(cur[k][0])
        cur[k] = (r["p"] * r["q"], t, "deep" if dt >= 20 else ("touch/in" if dt <= 0 else "1-19"))
q = lambda a, p: sorted(a)[int(p * (len(a) - 1))] if a else float("nan")
for g in ("$300", "calm", "4dec"):
    for u in (46, 64):
        v = R[(g, u)]
        if not v: continue
        sp = [x[3] for x in v]; deep = [x for x in v if x[0] >= 20]
        print(f"{g} UID {u}: fills {len(v)} | book spread in ticks median {q(sp, .5):.0f} | depth in SPREADS p25 {q([x[1] for x in v], .25):.2f} median {q([x[1] for x in v], .5):.2f} p75 {q([x[1] for x in v], .75):.2f} p90 {q([x[1] for x in v], .9):.2f}"
              f" | 20+-tick fills: {len(deep)} ({100 * len(deep) / len(v):.0f}%), their depth ticks median {q([x[0] for x in deep], .5):.0f} / spreads {q([x[1] for x in deep], .5):.2f}")
        for kind in ("touch/in", "1-19", "deep"):
            o = O[(g, u, kind)]
            if o: print(f"     order $ at {kind:8s}: n {len(o):5d} median {q(o, .5):,.0f} p90 {q(o, .9):,.0f}")
