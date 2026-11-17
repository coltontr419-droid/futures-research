"""$300 books, maker uid(s): what shrinks positions — each fill that REDUCES |inventory| is classified by depth vs pre-trade touch (inside/touch/behind) and by our model lean at the time
(fill side agrees with the lean = we stepped in on the opposite lean; no lean; against = filled against the lean). Also position lifetime (flat→flat) and max |position| ($)."""
import json, sys, collections, statistics as st
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
ml = json.load(open("/opt/mvtrx/agents/model_lean.json"))
S = collections.defaultdict(dict); FUN = collections.defaultdict(dict); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 310 or s > HI + 5: continue
    j = l.find(b'"book": ')
    if j < 0: continue
    bk = int(l[j + 8:l.index(b",", j)])
    if bk >= 128: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"):
            S[bk][s] = (r["bid"], r["ask"])
            if r.get("fund"): FUN[bk][s] = r["fund"]
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k)
        if r.get("Ma") in US and LO <= s < HI: F.append((ts, s, bk, r["Ma"], 1 if r["s"] == 1 else -1, r["p"], r["p"] * r["q"]))
def at(d, s):
    for x in range(s, s + 3):
        if x in d: return d[x]
def pred(bk, s, mid):
    m10, m50, m300 = (at(S[bk], s - k) for k in (10, 50, 300)); fv = at(FUN[bk], s); f30, f60, f300 = (at(FUN[bk], s - k) for k in (30, 60, 300))
    if None in (m10, m50, m300, fv, f30, f60, f300): return 0.0
    mm = lambda x: (x[0] + x[1]) / 2
    x = {"gap": (fv - mid) / mid * 1e4, "dF30": (fv - f30) / mid * 1e4, "dF60": (fv - f60) / mid * 1e4, "dF300": (fv - f300) / mid * 1e4,
         "r10": (mid - mm(m10)) / mid * 1e4, "r50": (mid - mm(m50)) / mid * 1e4, "r300": (mid - mm(m300)) / mid * 1e4}
    return sum(w * (x[n] - mu) / sd for n, w, mu, sd in zip(ml["names"], ml["w"], ml["mu"], ml["sd"]) if sd > 0) / ml["thr"]
for u in U:
    inv = collections.defaultdict(float); opened = {}; life = []; mx = collections.defaultdict(float); C = collections.Counter(); V = collections.Counter()
    for ts, s, bk, uu, sg, p, v in sorted(F):
        if uu != u: continue
        before = inv[bk]; inv[bk] += sg * v; mx[bk] = max(mx[bk], abs(inv[bk]))
        if before == 0 or (before > 0) != (inv[bk] > 0): opened[bk] = s
        if abs(inv[bk]) < abs(before):
            a = S[bk].get(s - 1)
            if a:
                mid = (a[0] + a[1]) / 2; d = round(((a[0] - p) if sg > 0 else (p - a[1])) / 0.01); kind = "inside" if d < 0 else ("touch" if d == 0 else ("behind 1-4" if d <= 4 else "deep 5+"))
                P = pred(bk, s - 1, mid); ag = "lean agrees" if P * sg >= 1.0 else ("lean against" if P * sg <= -1.0 else "no lean")
                C[(kind, ag)] += 1; V[(kind, ag)] += v
            if abs(inv[bk]) < 1 and bk in opened: life.append(s - opened.pop(bk))
    tot = sum(V.values()) or 1
    print(f"  {u}: position lifetime flat→flat median {st.median(life) if life else 0:.0f} s (n {len(life)}) | max |position| per book median ${st.median(mx.values()):,.0f}")
    for k, n in sorted(C.items(), key=lambda x: -V[x[0]])[:8]:
        print(f"      reduced by {k[0]:10s} | {k[1]:12s}: n {n:4d} ({V[k]/tot:4.0%} of reducing $)")
