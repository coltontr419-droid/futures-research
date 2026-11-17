"""$300 books: how the successful takers trade. Per uid: taker trades (aggregated per book/sec/side): $/trade, spread at entry (ticks), cost = price vs mid (bp, + = paid),
our model's lean at entry (agree / none / against), entries vs exits (does the trade raise or cut |inventory| incl. its maker fills), hold time, de-drifted mid move after entry 60/120/300 s,
alpha proxy per $ = move − cost, trades per book per sim min, taker fee per $ (− = rebate)."""
import json, sys, collections, statistics as st, numpy as np
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
ml = json.load(open("/opt/mvtrx/agents/model_lean.json"))
S = collections.defaultdict(dict); FUN = collections.defaultdict(dict); T = collections.defaultdict(lambda: [0.0, 0.0, 0.0]); MK = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 310 or s > HI + 310: continue
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
        if not (LO <= s < HI): continue
        v = r["p"] * r["q"]
        if r.get("Ta") in US:
            x = T[(r["Ta"], bk, s, r["s"])]; x[0] += v; x[1] += r["q"]; x[2] += r.get("Tf") or 0.0   # s 0 = taker BUY
        if r.get("Ma") in US: MK.append((s, bk, r["Ma"], 1 if r["s"] == 1 else -1, r["q"]))
def at(d, s):
    for x in range(s, s + 3):
        if x in d: return d[x]
DR = {}
for bk, m in S.items():
    ks = sorted(m); a = sum(m[ks[0]]) / 2; z = sum(m[ks[-1]]) / 2; DR[bk] = (z - a) / a * 1e4 / max(1, ks[-1] - ks[0])
def lean(bk, s, mid):
    m10, m50, m300 = (at(S[bk], s - k) for k in (10, 50, 300)); fv = at(FUN[bk], s); f30, f60, f300 = (at(FUN[bk], s - k) for k in (30, 60, 300))
    if None in (m10, m50, m300, fv, f30, f60, f300): return 0.0
    mm = lambda x: (x[0] + x[1]) / 2
    x = {"gap": (fv - mid) / mid * 1e4, "dF30": (fv - f30) / mid * 1e4, "dF60": (fv - f60) / mid * 1e4, "dF300": (fv - f300) / mid * 1e4,
         "r10": (mid - mm(m10)) / mid * 1e4, "r50": (mid - mm(m50)) / mid * 1e4, "r300": (mid - mm(m300)) / mid * 1e4}
    return sum(w * (x[n] - mu) / sd for n, w, mu, sd in zip(ml["names"], ml["w"], ml["mu"], ml["sd"]) if sd > 0) / ml["thr"]
mins = (HI - LO) / 60
for u in U:
    ev = sorted([(s, bk, 1 if side == 0 else -1, q, v, tf, "T") for (uu, bk, s, side), (v, q, tf) in T.items() if uu == u] + [(s, bk, sg, q, None, 0, "M") for s, bk, uu, sg, q in MK if uu == u])
    inv = collections.defaultdict(float); open_t = {}; holds = []; rows = []
    for s, bk, sg, q, v, tf, kind in ev:
        before = inv[bk]; inv[bk] += sg * q
        if kind == "T":
            a = S[bk].get(s - 1); f = [at(S[bk], s + h) for h in (60, 120, 300)]
            if a and None not in f:
                mid = (a[0] + a[1]) / 2; p = v / q; cost = sg * (p - mid) / mid * 1e4; spr = round((a[1] - a[0]) / 0.01)
                mv = [sg * ((x[0] + x[1]) / 2 - mid) / mid * 1e4 - sg * DR[bk] * h for x, h in zip(f, (60, 120, 300))]
                L = lean(bk, s - 1, mid); ag = "agree" if L * sg >= 1.0 else ("against" if L * sg <= -1.0 else "weak/none")
                rows.append((v, cost, spr, mv, ag, abs(inv[bk]) > abs(before), tf / v * 1e4 if v else 0))
        if before == 0 and inv[bk] != 0: open_t[bk] = s
        elif inv[bk] == 0 or (before > 0) != (inv[bk] > 0):
            if bk in open_t: holds.append(s - open_t.pop(bk))
            if inv[bk] != 0: open_t[bk] = s
    if not rows: print(f"  {u}: no $300 taker trades"); continue
    V = np.array([r[0] for r in rows]); W = V / V.sum(); cost = np.array([r[1] for r in rows]); mv = np.array([r[3] for r in rows])
    ent = np.array([r[5] for r in rows]); ag = collections.Counter(r[4] for r in rows); spr = collections.Counter(min(r[2], 4) for r in rows)
    print(f"  {u}: taker trades {len(rows)} ({len(rows)/mins:.1f}/sim min) ${V.sum()/1e3:.0f}k, $/trade med ${np.median(V):,.0f} | spread at entry {dict(sorted(spr.items()))} | cost {np.dot(W, cost):+.2f} bp"
          f" | model {dict(ag)} | entries (|inv| up) {ent.mean():.0%} | hold med {st.median(holds) if holds else 0:.0f} s | de-drifted move +60/+120/+300 {np.dot(W, mv[:, 0]):+.2f} / {np.dot(W, mv[:, 1]):+.2f} / {np.dot(W, mv[:, 2]):+.2f}"
          f" | move−cost @120 s {np.dot(W, mv[:, 1] - cost):+.2f} bp | taker fee {np.dot(W, [r[6] for r in rows]):+.1f} bp")
    for g in ("agree", "weak/none", "against"):
        m = np.array([r[4] == g for r in rows])
        if m.sum(): print(f"      model {g:9s}: n {m.sum():4d} | cost {np.average(cost[m], weights=V[m]):+.2f} | move +120 {np.average(mv[m, 1], weights=V[m]):+.2f} | move−cost {np.average(mv[m, 1] - cost[m], weights=V[m]):+.2f} bp")
