"""§1373: P11 risk if x3 stops quoting $300 books — x3's counterparty mix (background vs miner takers, top-2 miner takers' share) on all books vs
calm + 4-dec only, and the same for fleet UID 216.  python3 p11check.py <tape> <T0> <T1> <uid> ..."""
import json, sys, collections
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]
cp = {u: {"all": collections.Counter(), "nov": collections.Counter()} for u in U}
for l in open(tape, "rb"):
    if b'"Mi"' not in l: continue
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < T0 or t > T1: continue
    r = json.loads(l)
    if r["Ma"] not in cp or r["Ma"] == r["Ta"]: continue
    k = "bg" if r["Ta"] < 0 else r["Ta"]; v = r["p"] * r["q"]
    cp[r["Ma"]]["all"][k] += v
    if r["book"] >= 63: cp[r["Ma"]]["nov"][k] += v
for u in U:
    for scope, lab in (("all", "all books"), ("nov", "calm + 4-dec only (no $300)")):
        c = cp[u][scope]; tot = sum(c.values())
        if not tot: continue
        miners = sorted(((v, k) for k, v in c.items() if k != "bg"), reverse=True)
        top2 = sum(v for v, k in miners[:2])
        print(f"UID {u} {lab:30s}: ${tot:,.0f} | background {c['bg'] / tot:.0%} | miner takers {len(miners)} | top-2 miner takers {top2 / tot:.1%} of $ ({[k for v, k in miners[:2]]})")
