"""Sub-second timing of $300 maker fills (fraction of the sim second, ns → 0.0–1.0) per uid, in 10 buckets, + the same for all fills (baseline)."""
import json, sys, collections
tape, LO, HI = sys.argv[1], int(sys.argv[2]) * 10**9, int(sys.argv[3]) * 10**9; U = [int(u) for u in sys.argv[4:]]
H = collections.defaultdict(collections.Counter); seen = set()
for l in open(tape, "rb"):
    if b'"Ma"' not in l: continue
    i = l.find(b'"ts": ')
    try: ts = int(l[i + 6:l.index(b",", i)])
    except ValueError: continue
    if not (LO <= ts < HI): continue
    r = json.loads(l)
    if r["book"] >= 128: continue
    k = (r["book"], r.get("id"), ts)
    if k in seen: continue
    seen.add(k); b = int((ts % 10**9) / 1e8)
    H["ALL"][b] += 1
    if r.get("Ma") in U: H[r["Ma"]][b] += 1
for u in ["ALL"] + U:
    c = H[u]; n = sum(c.values())
    print(f"  {str(u):>4}: n {n:6d} | " + " ".join(f"{c[b] / n:4.0%}" for b in range(10)) + "   (0.0–0.1 s … 0.9–1.0 s within the sim second)")
