"""$30 books (128–191): how long-lived makers quote — fills/min, $/fill, depth vs pre-trade touch, buy share, per-book two-sidedness (min(buy$,sell$)/max), spread at fill, markout +2/+20 s (captured-like)."""
import json, sys, collections, statistics as st, numpy as np
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
S = collections.defaultdict(dict); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 5 or s > HI + 25: continue
    j = l.find(b'"book": ')
    if j < 0: continue
    bk = int(l[j + 8:l.index(b",", j)])
    if not 128 <= bk <= 191: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): S[bk][s] = (r["bid"], r["ask"])
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k)
        if r.get("Ma") in US and LO <= s < HI: F.append((s, bk, r["Ma"], r["p"], r["q"], r["s"], r.get("Mf", 0.0)))
mins = (HI - LO) / 60
for u in U:
    L = [f for f in F if f[2] == u]
    if not L: print(f"  {u}: no $30 fills"); continue
    per = collections.defaultdict(lambda: [0.0, 0.0]); dep = collections.Counter(); spr = []; m2 = []; m20 = []; v = []; buys = 0; fee = []
    for s, bk, _, p, q, side, mf in L:
        a = S[bk].get(s - 1); b2 = S[bk].get(s + 2); b20 = S[bk].get(s + 20)
        buy = side == 1; buys += buy; per[bk][0 if buy else 1] += p * q; v.append(p * q); fee.append(mf / (p * q) * 1e4 if p * q else 0)
        if a:
            d = round(((a[0] - p) if buy else (p - a[1])) / 0.01); dep[max(-1, min(d, 3))] += 1; spr.append(round((a[1] - a[0]) / 0.01))
            m0 = (a[0] + a[1]) / 2; sg = 1 if buy else -1
            if b2: m2.append(sg * ((b2[0] + b2[1]) / 2 - p) / m0 * 1e4)
            if b20: m20.append(sg * ((b20[0] + b20[1]) / 2 - p) / m0 * 1e4)
    two = [min(x) / max(x) if max(x) else 0 for x in per.values()]
    print(f"  {u}: fills {len(L)} ({len(L)/mins:.1f}/sim min) ${sum(v)/1e3:.0f}k | $/fill med ${st.median(v):,.0f} | books {len(per)} | buy share {buys/len(L):.0%} | per-book two-sided min/max median {st.median(two):.2f}"
          f" | depth {dict(sorted(dep.items()))} | spread at fill med {st.median(spr) if spr else 0} ticks | fill price vs mid later: +2 s {np.mean(m2):+.2f}, +20 s {np.mean(m20):+.2f} bp | maker fee med {st.median(fee):.2f} bp")
