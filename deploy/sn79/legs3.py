"""§1273 caps check for the copy arm: top takers' traded $ per book per 24 sim h, and their max |position| $ per book (tape span scaled)."""
import json, sys, collections, statistics as st
tape, uids = sys.argv[1], {int(u) for u in sys.argv[2].split(",")}
V = collections.defaultdict(float); I = collections.defaultdict(float); P = collections.defaultdict(float); seen = set(); t0 = t1 = None
for l in open(tape, "rb"):
    if b'"Ta": ' not in l: continue
    r = json.loads(l); k = (r["book"], r.get("id"))
    if k in seen: continue
    seen.add(k); t = r["ts"] / 1e9; t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
    if r.get("Ta") in uids:
        key = (r["Ta"], r["book"]); V[key] += r["q"] * r["p"]; I[key] += (1 if r["s"] == 0 else -1) * r["q"]; P[key] = max(P[key], abs(I[key]) * r["p"])
span = t1 - t0; print(f"tape span {span / 3600:.1f} sim h")
for u in sorted(uids):
    v = [V[k] * 86400 / span for k in V if k[0] == u]; p = [P[k] for k in P if k[0] == u]
    print(f"uid {u}: books {len(v)} | $/book/24h median ${st.median(v):,.0f} max ${max(v):,.0f} | max |position| per book median ${st.median(p):,.0f} max ${max(p):,.0f}")
