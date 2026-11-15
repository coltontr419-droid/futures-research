"""MEASURED: $300 inside/touch fills by the TAKER's total trade size that second (sum over all makers of trades with the same book, sec, taker id, taker side)."""
import json, sys, collections
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
S = collections.defaultdict(dict); F = []; seen = set(); TK = collections.defaultdict(float)
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 5 or s > HI + 25: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if bk >= 128: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): S[bk][s] = (r["bid"], r["ask"])
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k); key = (bk, s, r.get("Ta"), r["s"]); TK[key] += r["p"] * r["q"]
        if r.get("Ma") in US and LO <= s < HI: F.append((s, bk, r["Ma"], r["p"], r["q"], r["s"], key))
B = [(0, 1000), (1000, 3000), (3000, 10000), (10000, 10 ** 12)]
lab = lambda v: next(f"${lo // 1000}-{hi // 1000 if hi < 10**12 else '+'}k" for lo, hi in B if lo <= v < hi)
R = collections.defaultdict(lambda: [0.0, 0.0, 0]); TOT = collections.defaultdict(float)
for s, bk, u, p, q, side, key in F:
    a = S[bk].get(s - 1); b = S[bk].get(s + 20)
    if not (a and b): continue
    buy = side == 1; sg = 1 if buy else -1; m0 = (a[0] + a[1]) / 2
    d = round(((a[0] - p) if buy else (p - a[1])) / 0.01); kind = "inside" if d < 0 else ("touch" if d == 0 else "behind")
    mo = sg * ((b[0] + b[1]) / 2 - m0) / m0 * 1e4; bb = lab(TK[key])
    for kk in (kind, "all"):
        x = R[(u, kk, bb)]; x[0] += p * q; x[1] += p * q * mo; x[2] += 1; TOT[(u, kk)] += p * q
for kind in ("inside", "touch", "all"):
    print(f"== $300 {kind.upper()} fills by TAKER trade size that second (share of $, n, 20-s markout bp)")
    for u in U:
        print(f"  {u}: " + " | ".join(f"{bb} {R[(u, kind, bb)][0] / max(TOT[(u, kind)], 1e-9):3.0%} n{R[(u, kind, bb)][2]} {R[(u, kind, bb)][1] / R[(u, kind, bb)][0]:+.2f}" for bb in [lab(lo) for lo, hi in B] if R[(u, kind, bb)][0]))
