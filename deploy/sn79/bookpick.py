"""§1277: which books do long-lived takers trade, and why? Per UID: books by group ($300 0-62 / calm 63-101 / 4-dec 102-127), and for every book the
book's median spread (bp), 5-min |move| (bp), print count — traded vs untraded.   python bookpick.py <tape> <uids>"""
import json, sys, collections, statistics as st, bisect
tape, U = sys.argv[1], [int(u) for u in sys.argv[2].split(",")]; HI = float(sys.argv[3]) if len(sys.argv) > 3 else 90000   # 1e9 for the pre-reset tape
SP = collections.defaultdict(list); MID = collections.defaultdict(list); PR = collections.Counter(); T = collections.defaultdict(set); V = collections.defaultdict(float); seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= HI: continue
    if b'"bid": ' in l[:80]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r.get("bid") and r.get("ask"): m = (r["bid"] + r["ask"]) / 2; SP[r["book"]].append((r["ask"] - r["bid"]) / m * 1e4); MID[r["book"]].append((t, m))
    elif b'"Ta": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"))
        if k in seen: continue
        seen.add(k); PR[r["book"]] += 1
        if r.get("Ta") in U: T[r["Ta"]].add(r["book"]); V[(r["Ta"], r["book"])] += r["q"] * r["p"]
def mv5(b):
    a = MID[b]; ts = [x[0] for x in a]; out = []
    for k in range(0, len(a), 20):
        j = bisect.bisect_left(ts, a[k][0] + 300)
        if j < len(a): out.append(abs(a[j][1] - a[k][1]) / a[k][1] * 1e4)
    return st.median(out) if out else 0
B = sorted(SP); f = {b: (st.median(SP[b]), mv5(b), PR[b]) for b in B}
g = lambda b: "$300" if b < 63 else "calm" if b < 102 else "4-dec"
for u in U:
    tr = T[u]; print(f"== uid {u}: books {len(tr)} | by group " + ", ".join(f"{gg} {sum(1 for b in tr if g(b) == gg)}/{sum(1 for b in B if g(b) == gg)}" for gg in ("$300", "calm", "4-dec")))
    for nm, S in (("traded", [b for b in B if b in tr]), ("not traded", [b for b in B if b not in tr])):
        if S: print(f"   {nm:10} n {len(S):3d} | spread median {st.median(f[b][0] for b in S):5.2f} bp | 5-min |move| median {st.median(f[b][1] for b in S):5.1f} bp | prints median {st.median(f[b][2] for b in S):5.0f}")
    top = sorted(((V[(u, b)], b) for b in tr), reverse=True)[:8]; print("   top books by $: " + " ".join(f"{b}({g(b)})" for _, b in top))
print("overlap 94∩186:", len(T[94] & T[186]) if 94 in T and 186 in T else "-")
