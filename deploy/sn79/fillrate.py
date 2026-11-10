"""§1299: maker fills and $ per sim minute per UID in time windows (current sim). python fillrate.py <tape> <name=uid,uid> ... -- <t0> <t1> <t2> ...
Prints, for each consecutive window [t_i, t_i+1), fills/min and $/min per UID (group average) and by book group."""
import json, sys, collections
args = sys.argv[1:]; k = args.index("--"); G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in args[1:k]}; T = [float(x) for x in args[k + 1:]]
who = {u: g for g, us in G.items() for u in us}; seen = set()
N = collections.defaultdict(float); V = collections.defaultdict(float); tmax = 0
for l in open(args[0], "rb"):
    if b'"Ma": ' not in l: continue
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < T[0]: continue
    r = json.loads(l); kk = (r["book"], r.get("id"), r["ts"])
    if kk in seen: continue
    seen.add(kk); tmax = max(tmax, t)
    g = who.get(r.get("Ma"))
    if g is None: continue
    w = max(j for j in range(len(T)) if t >= T[j]); bg = "$300" if r["book"] < 63 else "calm" if r["book"] < 102 else "4dec"
    for key in ((g, w, "all"), (g, w, bg)): N[key] += 1; V[key] += r["q"] * r["p"]
edges = T + [tmax]
for w in range(len(T)):
    mins = (edges[w + 1] - edges[w]) / 60
    if mins <= 0: continue
    print(f"window {w}: sim s {edges[w]:.0f} → {edges[w + 1]:.0f} ({mins:.0f} sim min)")
    for g in G:
        n = len(G[g]); f = lambda b: f"{N[(g, w, b)] / mins / n:5.1f} fills ${V[(g, w, b)] / mins / n / 1e3:5.1f}k"
        print(f"   {g:6} per UID per sim min: all {f('all')} | $300 {f('$300')} | calm {f('calm')} | 4dec {f('4dec')}")
