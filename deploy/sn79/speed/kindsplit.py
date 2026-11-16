"""$300 fills split by depth kind (inside/touch/behind) for each uid: n, $ share, median $/fill, 20-s markout; + 60-s markout."""
import json, sys, collections, statistics
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
S = collections.defaultdict(dict); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 5 or s > HI + 65: continue
    j = l.find(b'"book": ')
    if j < 0: continue
    bk = int(l[j + 8:l.index(b",", j)])
    if bk >= 128: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): S[bk][s] = (r["bid"], r["ask"])
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k)
        if r.get("Ma") in US and LO <= s < HI: F.append((s, bk, r["Ma"], r["p"], r["q"], r["s"]))
R = collections.defaultdict(list)
for s, bk, u, p, q, side in F:
    a = S[bk].get(s - 1); b = S[bk].get(s + 20); c = S[bk].get(s + 60)
    if not (a and b and c): continue
    buy = side == 1; sg = 1 if buy else -1; m0 = (a[0] + a[1]) / 2
    d = round(((a[0] - p) if buy else (p - a[1])) / 0.01); kind = "inside" if d < 0 else ("touch" if d == 0 else "behind")
    mo20 = sg * ((b[0] + b[1]) / 2 - m0) / m0 * 1e4; mo60 = sg * ((c[0] + c[1]) / 2 - m0) / m0 * 1e4
    R[(u, kind)].append((p * q, mo20, mo60, d, 1 if 63 <= bk <= 101 else 0))
for u in U:
    tot = sum(x[0] for k in ("inside", "touch", "behind") for x in R[(u, k)])
    for k in ("inside", "touch", "behind"):
        L = R[(u, k)]
        if not L: print(f"  {u} {k:6s} none"); continue
        v = sum(x[0] for x in L)
        print(f"  {u} {k:6s} n{len(L):4d} ${v/1e3:6.0f}k {v/tot:4.0%} | $/fill med ${statistics.median(x[0] for x in L):,.0f} | mo20 {sum(x[0]*x[1] for x in L)/v:+.2f} mo60 {sum(x[0]*x[2] for x in L)/v:+.2f} bp | depth med {statistics.median(x[3] for x in L)} | p90 ${sorted(x[0] for x in L)[int(len(L)*0.9)]:,.0f} max ${max(x[0] for x in L):,.0f} | vol/calm n {sum(1 for x in L if x[4]==0)}/{sum(1 for x in L if x[4]==1)}")
