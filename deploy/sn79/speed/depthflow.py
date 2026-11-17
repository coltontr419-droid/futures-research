"""$300 books: ALL makers' fills by depth behind the pre-trade touch (0 = touch, 1..4 behind) — $ per sim min (the flow a resting order there could share), markout of the mid at +20 / +60 / +120 s
in the maker's favour, raw and with each book's whole-window drift removed. Also split by whether OUR live model leans the same way as the resting side (lean agrees) — needs model_lean.json."""
import json, sys, collections, numpy as np
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); OURS = {85, 47}
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
        if LO <= s < HI and r.get("Ma") not in OURS: F.append((s, bk, r["p"], r["q"], r["s"]))
def at(d, s):
    for x in range(s, s + 3):
        if x in d: return d[x]
DR = {}
for bk, m in S.items():
    ks = sorted(m); a = sum(m[ks[0]]) / 2; z = sum(m[ks[-1]]) / 2; DR[bk] = (z - a) / a * 1e4 / max(1, ks[-1] - ks[0])
def lean(bk, s, mid):
    m10, m50, m300 = (at(S[bk], s - k) for k in (10, 50, 300)); fv = at(FUN[bk], s)
    f30, f60, f300 = (at(FUN[bk], s - k) for k in (30, 60, 300))
    if None in (m10, m50, m300, fv, f30, f60, f300): return 0
    mm = lambda x: (x[0] + x[1]) / 2
    x = {"gap": (fv - mid) / mid * 1e4, "dF30": (fv - f30) / mid * 1e4, "dF60": (fv - f60) / mid * 1e4, "dF300": (fv - f300) / mid * 1e4,
         "r10": (mid - mm(m10)) / mid * 1e4, "r50": (mid - mm(m50)) / mid * 1e4, "r300": (mid - mm(m300)) / mid * 1e4}
    p = sum(w * (x[n] - mu) / sd for n, w, mu, sd in zip(ml["names"], ml["w"], ml["mu"], ml["sd"]) if sd > 0)
    return 1 if p >= 1.5 * ml["thr"] else (-1 if p <= -1.5 * ml["thr"] else 0)
R = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0])
for s, bk, p, q, side in F:
    a = S[bk].get(s - 1); f = [S[bk].get(s + h) for h in (20, 60, 120)]
    if not a or None in f: continue
    buy = side == 1; sg = 1 if buy else -1; mid = (a[0] + a[1]) / 2
    d = round(((a[0] - p) if buy else (p - a[1])) / 0.01)
    if d < 0 or d > 4: continue
    L = lean(bk, s - 1, mid); agree = "lean agrees" if L == sg else ("lean against" if L == -sg else "no lean")
    mo = [sg * ((x[0] + x[1]) / 2 - mid) / mid * 1e4 for x in f]; dd = [mo[i] - sg * DR[bk] * h for i, h in enumerate((20, 60, 120))]
    for key in ((d, "all"), (d, agree)):
        x = R[key]; v = p * q; x[0] += v; x[1] += v * mo[0]; x[2] += v * mo[1]; x[3] += v * mo[2]; x[4] += v * dd[1]; x[5] += v * dd[2]; x[6] += 1
mins = (HI - LO) / 60
print(f"$300 makers' fills (not ours), sim {LO}-{HI} ({mins:.0f} sim min): depth behind touch → $/sim min, markout raw +20/+60/+120 s, de-drifted +60/+120 s (bp)")
for d in range(5):
    for g in ("all", "lean agrees", "no lean", "lean against"):
        x = R[(d, g)]
        if x[0]: print(f"  depth {d} {g:12s}: n {x[6]:5d} ${x[0]/mins/1e3:6.1f}k/min | raw {x[1]/x[0]:+.2f} / {x[2]/x[0]:+.2f} / {x[3]/x[0]:+.2f} | de-drift {x[4]/x[0]:+.2f} / {x[5]/x[0]:+.2f}")
