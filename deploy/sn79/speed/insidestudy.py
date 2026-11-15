"""$300 books (0-127): what are the fleet's 'inside' (d-1) fills, and how fast do WE join a new best price after the touch moves?
python insidestudy.py <tape> <lo sim s> <hi sim s> <our uid> <ref uids...>   (MEASURED from the live tape; book seen once per sim second)"""
import json, sys, bisect, collections, random
tape, LO, HI, OUR = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]); REFS = [int(u) for u in sys.argv[5:]]; US = set(REFS) | {OUR}
tops = collections.defaultdict(dict); fills = []; seen = set(); ourbest = collections.defaultdict(dict)   # ourbest[book][sec] = (our best bid px, our best ask px)
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 30 or s > HI + 30: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if bk >= 128: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): tops[bk][s] = (r["bid"], r["ask"])
    elif b'"queue"' in l[:90]:
        r = json.loads(l); bb = max((q[1] for q in r["queue"] if q[0] == 0), default=None); ba = min((q[1] for q in r["queue"] if q[0] == 1), default=None)
        ourbest[bk][s] = (bb, ba)
    elif b'"Ma"' in l:
        r = json.loads(l)
        if r.get("Ma") in US and LO <= s < HI:
            k = (bk, r.get("id"), ts)
            if k not in seen: seen.add(k); fills.append((s, bk, r["Ma"], r["p"], r["q"], r["s"]))
T = 0.01
# 1. spread distribution (book-seconds)
sp = collections.Counter()
for bk, d in tops.items():
    for s, (b, a) in d.items():
        if LO <= s < HI: sp[min(round((a - b) / T), 4)] += 1
n = sum(sp.values()); print("MEASURED 1. $300 spread (ticks) share of book-seconds:", {k if k < 4 else "4+": f"{v / n:.0%}" for k, v in sorted(sp.items())})
# 2. fills: depth vs the previous second's touch, spread then, and whether the touch moved toward the fill price in that second
R = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0]))
for s, bk, u, p, q, side in fills:
    t0 = tops[bk].get(s - 1); t1 = tops[bk].get(s + 20)
    if not t0 or not t1: continue
    buy = side == 1; sg = 1 if buy else -1; m0 = (t0[0] + t0[1]) / 2
    d = round(((t0[0] - p) if buy else (p - t0[1])) / T); d = max(-2, min(d, 3)); spr = round((t0[1] - t0[0]) / T)
    mo = sg * ((t1[0] + t1[1]) / 2 - m0) / m0 * 1e4; usd = p * q
    key = "inside (d<0)" if d < 0 else ("touch" if d == 0 else "behind")
    for k2 in (key, f"{key} | prev spread {'1' if spr <= 1 else '2+'}"):
        x = R[u][k2]; x[0] += usd; x[1] += usd * mo
    R[u]["ALL"][0] += usd; R[u]["ALL"][1] += usd * mo
print("MEASURED 2. $300 maker fills by depth vs the touch 1 s before: share of $, 20-s markout bp (+ = price moved the maker's way)")
for u in [OUR] + REFS:
    tot = R[u]["ALL"][0] or 1
    print(f"  {u}: " + " || ".join(f"{k}: {v[0] / tot:4.0%} mo {v[1] / v[0]:+5.2f}" for k, v in sorted(R[u].items()) if k != "ALL" and v[0]))
# 3. OUR re-peg: after the best bid rises (ask falls) by >= 1 tick between seconds, how many seconds until our best bid (ask) sits at the new touch?
lag = collections.Counter(); ev = 0
for bk, d in tops.items():
    ob = ourbest.get(bk, {})
    for s in sorted(d):
        if not (LO <= s < HI) or (s - 1) not in d: continue
        for side in (0, 1):
            old, new = d[s - 1][side], d[s][side]
            moved = (new > old + 1e-9) if side == 0 else (new < old - 1e-9)
            if not moved: continue
            ev += 1; k = None
            for w in range(0, 6):
                o = ob.get(s + w)
                if o and o[side] is not None and abs(o[side] - d.get(s + w, (None, None))[side] if d.get(s + w) else 9) < 1e-9: k = w; break
            lag[k if k is not None else "6+/never"] += 1
print(f"MEASURED 3. touch moves toward the inside ({ev}): seconds until OUR order sits at the new best price:", {k: f"{v / ev:.0%}" for k, v in sorted(lag.items(), key=lambda x: str(x[0]))})
