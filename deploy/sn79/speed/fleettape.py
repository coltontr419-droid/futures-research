"""Fleet coordination on the tape: per uid maker/taker $ and books per class, $/fill, buy share; pairwise book overlap; same-book fills within 5 s (same / opposite side);
how many fleet uids fill the same book in the same 60 s; price level agreement (same price, same second)."""
import json, sys, collections, statistics as st, itertools
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); FL = set(json.load(open("/opt/mvtrx/speed/fleet_uids.json")))
F = []; seen = set()
for l in open(tape, "rb"):
    if b'"Ta"' not in l: continue
    i = l.find(b'"ts": '); ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO or s >= HI: continue
    r = json.loads(l); k = (r["book"], r.get("id"), ts)
    if k in seen: continue
    seen.add(k)
    for role, key in (("M", "Ma"), ("T", "Ta")):
        u = r.get(key)
        if u in FL:
            side = (1 - r["s"]) if role == "M" else r["s"]   # side the uid traded: 0 buy
            if role == "M": side = 0 if r["s"] == 1 else 1
            F.append((s, r["book"], u, role, side, r["p"], r["p"] * r["q"]))
cls = lambda b: "$300" if b < 128 else ("$30" if b < 192 else "4dec")
U = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, set(), [], 0, 0]))
for s, bk, u, role, side, p, v in F:
    x = U[u][(cls(bk), role)]; x[0] += v; x[1].add(bk); x[2].append(v); x[3] += 1; x[4] += (side == 0)
print(f"fleet fills {len(F)} in sim {LO}-{HI} ({(HI-LO)/60:.0f} sim min)")
print("uid | class role: $k books med$/fill buy% ...")
for u in sorted(U):
    print(f" {u:3d} | " + " | ".join(f"{c} {r} ${x[0]/1e3:.0f}k b{len(x[1])} ${st.median(x[2]):,.0f} {x[4]/x[3]:.0%}b" for (c, r), x in sorted(U[u].items())))
# pairwise $300 maker book overlap
B = {u: U[u][("$300", "M")][1] for u in U if U[u][("$300", "M")][0] > 0}
J = [len(B[a] & B[b]) / len(B[a] | B[b]) for a, b in itertools.combinations(B, 2) if B[a] | B[b]]
print(f"$300 maker book sets: {len(B)} uids, books each median {st.median(len(v) for v in B.values()) if B else 0}, pairwise Jaccard median {st.median(J) if J else 0:.2f} (1 = same books)")
# co-timing on the same book
byb = collections.defaultdict(list)
for s, bk, u, role, side, p, v in F:
    if role == "M": byb[bk].append((s, u, side, p))
same = opp = tot = 0; samep = 0
for bk, L in byb.items():
    L.sort()
    for i, (s, u, sd, p) in enumerate(L):
        tot += 1; hit = None
        for s2, u2, sd2, p2 in L[i + 1:]:
            if s2 - s > 5: break
            if u2 != u: hit = (sd2 == sd, p2 == p); break
        if hit:
            if hit[0]: same += 1; samep += hit[1]
            else: opp += 1
print(f"maker fills followed within 5 s by ANOTHER fleet uid on the same book: same side {same / max(tot,1):.1%} (same price {samep / max(tot,1):.1%}), opposite side {opp / max(tot,1):.1%} of {tot}")
W = collections.defaultdict(set)
for s, bk, u, role, side, p, v in F:
    if role == "M" and bk < 128: W[(bk, s // 60)].add(u)
c = collections.Counter(len(v) for v in W.values())
print("$300 book-minutes with fleet maker fills, by number of distinct fleet uids: " + ", ".join(f"{k}: {c[k]}" for k in sorted(c)))
