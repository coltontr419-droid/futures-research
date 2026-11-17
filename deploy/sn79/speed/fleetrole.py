"""Per uid and class: maker / taker fills (n, $, median $/fill), buy share; depth of maker fills vs pre-trade touch; for a fleet: share of a member's fills that have ANOTHER member filling
the same book + side within 2 s (overlap)."""
import json, sys, collections, statistics as st
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); groups = [list(map(int, g.split(","))) for g in sys.argv[4:]]
US = set(u for g in groups for u in g); grp = {u: i for i, g in enumerate(groups) for u in g}
S = collections.defaultdict(dict); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 3 or s >= HI: continue
    j = l.find(b'"book": ')
    if j < 0: continue
    bk = int(l[j + 8:l.index(b",", j)])
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): S[bk][s] = (r["bid"], r["ask"])
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k)
        if not (LO <= s < HI): continue
        v = r["p"] * r["q"]
        if r.get("Ma") in US: F.append((s, bk, r["Ma"], "M", 1 if r["s"] == 1 else -1, r["p"], v))
        if r.get("Ta") in US: F.append((s, bk, r["Ta"], "T", 1 if r["s"] == 0 else -1, r["p"], v))
cls = lambda b: "$300" if b < 128 else ("$30" if b < 192 else "4dec")
idx = collections.defaultdict(list)
for f in F: idx[(f[1], f[4])].append((f[0], f[2]))
mins = (HI - LO) / 60
for g in groups:
    for u in g:
        out = []
        for c in ("$300", "$30", "4dec"):
            for role in ("M", "T"):
                L = [f for f in F if f[2] == u and f[3] == role and cls(f[1]) == c]
                if not L: continue
                dep = collections.Counter()
                if role == "M":
                    for s, bk, _, _, sg, p, v in L:
                        a = S[bk].get(s - 1)
                        if a: dep[max(-1, min(3, round(((a[0] - p) if sg > 0 else (p - a[1])) / (0.01 if bk < 192 else 0.0001))))] += 1
                ov = sum(1 for s, bk, _, _, sg, p, v in L if any(uu != u and grp.get(uu) == grp[u] and abs(ss - s) <= 2 for ss, uu in idx[(bk, sg)])) / len(L)
                out.append(f"{c} {'maker' if role == 'M' else 'TAKER'} n{len(L)} ${sum(f[6] for f in L)/1e3:.0f}k ${st.median(f[6] for f in L):,.0f}/fill buy {sum(1 for f in L if f[4] > 0)/len(L):.0%}"
                           + (f" depth {dict(sorted(dep.items()))}" if dep else "") + f" fleet-overlap {ov:.0%}")
        print(f"  {u}: " + " || ".join(out))
