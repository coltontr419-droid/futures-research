"""§1382: per-UID depth profile (ticks behind the pre-trade touch) and order size by depth, $300 / calm / 4-dec, for each top maker + x3.
Also: multi-level sweeps (one taker trade id filling the maker at > 1 price) vs single-level fills."""
import json, sys, collections
U = [64, 216, 48, 178, 119, 117, 5, 146]
grp = lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec")
snap = {}; tick = {}
dep = collections.defaultdict(lambda: collections.Counter()); szd = collections.defaultdict(list)
BIN = lambda d: "in" if d < 0 else ("0" if d == 0 else ("1" if d == 1 else ("2-4" if d <= 4 else ("5-9" if d <= 9 else ("10-19" if d <= 19 else "20+")))))
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
    if u not in U: continue
    b = r["book"]; s = snap.get(b); tk = tick.get(b)
    if not (s and tk): continue
    bid = r["s"] == 1; ref = s[0] if bid else s[1]
    d = round(((ref - r["p"]) if bid else (r["p"] - ref)) / tk)
    k = (grp(b), u); dep[k][BIN(d)] += 1; szd[(grp(b), "top" if u not in (64, 216) else u, BIN(d))].append(r["p"] * r["q"])
cols = ["in", "0", "1", "2-4", "5-9", "10-19", "20+"]
for g in ("$300", "calm", "4dec"):
    print(f"== {g} depth share per UID (ticks behind the touch)")
    print("        " + " ".join(f"{c:>6s}" for c in cols) + "   fills")
    for u in U:
        c = dep[(g, u)]; n = sum(c.values()) or 1
        print(f"  {u:4d}  " + " ".join(f"{100 * c[x] / n:5.0f}%" for x in cols) + f"   {n}")
    for w in ("top", 64):
        row = []
        for x in cols:
            v = sorted(szd[(g, w, x)]); row.append(f"{v[len(v) // 2]:6,.0f}" if v else "     -")
        print(f"  median fill $ by depth, {w}: " + " ".join(row))
