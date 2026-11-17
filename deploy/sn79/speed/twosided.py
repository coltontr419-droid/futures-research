"""$300 maker fills of given uids split by depth (inside / touch / behind) × OUR model at the fill (fill side agrees with the lean ≥ 1.0 thr / no lean / against): n, $ share, $/fill,
de-drifted mid move in the fill's favour at 60 / 120 s (vs the pre-fill mid). Shows whether a two-sided quoter's edge comes from leaning its inside quotes with the signal."""
import json, sys, collections, statistics as st, numpy as np
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
ml = json.load(open("/opt/mvtrx/agents/model_lean.json"))
S = collections.defaultdict(dict); FUN = collections.defaultdict(dict); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 310 or s > HI + 125: continue
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
        if r.get("Ma") in US and LO <= s < HI: F.append((s, bk, r["Ma"], 1 if r["s"] == 1 else -1, r["p"], r["p"] * r["q"]))
def at(d, s):
    for x in range(s, s + 3):
        if x in d: return d[x]
DR = {}
for bk, m in S.items():
    ks = sorted(m); a = sum(m[ks[0]]) / 2; z = sum(m[ks[-1]]) / 2; DR[bk] = (z - a) / a * 1e4 / max(1, ks[-1] - ks[0])
def pred(bk, s, mid):
    m10, m50, m300 = (at(S[bk], s - k) for k in (10, 50, 300)); fv = at(FUN[bk], s); f30, f60, f300 = (at(FUN[bk], s - k) for k in (30, 60, 300))
    if None in (m10, m50, m300, fv, f30, f60, f300): return None
    mm = lambda x: (x[0] + x[1]) / 2
    x = {"gap": (fv - mid) / mid * 1e4, "dF30": (fv - f30) / mid * 1e4, "dF60": (fv - f60) / mid * 1e4, "dF300": (fv - f300) / mid * 1e4,
         "r10": (mid - mm(m10)) / mid * 1e4, "r50": (mid - mm(m50)) / mid * 1e4, "r300": (mid - mm(m300)) / mid * 1e4}
    return sum(w * (x[n] - mu) / sd for n, w, mu, sd in zip(ml["names"], ml["w"], ml["mu"], ml["sd"]) if sd > 0) / ml["thr"]
for u in U:
    R = collections.defaultdict(list)
    for s, bk, uu, sg, p, v in F:
        if uu != u: continue
        a = S[bk].get(s - 1); f60, f120 = at(S[bk], s + 60), at(S[bk], s + 120)
        if not a or not f60 or not f120: continue
        mid = (a[0] + a[1]) / 2; P = pred(bk, s - 1, mid)
        if P is None: continue
        d = round(((a[0] - p) if sg > 0 else (p - a[1])) / 0.01); kind = "inside" if d < 0 else ("touch" if d == 0 else "behind")
        ag = "agree" if P * sg >= 1.0 else ("against" if P * sg <= -1.0 else "no lean")
        mv = [sg * ((x[0] + x[1]) / 2 - mid) / mid * 1e4 - sg * DR[bk] * h for x, h in ((f60, 60), (f120, 120))]
        R[(kind, ag)].append((v, mv[0], mv[1]))
    tot = sum(x[0] for L in R.values() for x in L)
    print(f"  {u}: $300 maker $ {tot/1e3:.0f}k")
    for kind in ("inside", "touch", "behind"):
        cells = []
        for ag in ("agree", "no lean", "against"):
            L = R[(kind, ag)]
            if L:
                V = sum(x[0] for x in L); cells.append(f"{ag} {V/tot:4.0%} n{len(L)} ${st.median(x[0] for x in L):,.0f} {sum(x[0]*x[1] for x in L)/V:+.2f}/{sum(x[0]*x[2] for x in L)/V:+.2f}")
        print(f"     {kind:6s}: " + " | ".join(cells))
