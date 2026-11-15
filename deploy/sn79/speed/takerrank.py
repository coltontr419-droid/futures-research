import json, sys, collections
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); pay = {int(k): v for k, v in json.load(open("/opt/mvtrx/speed/pay_all.json")).items()}
V = collections.defaultdict(lambda: [0.0, 0.0]); seen = set()
for l in open(tape, "rb"):
    if b'"Ta"' not in l: continue
    i = l.find(b'"ts": ')
    try: ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    except ValueError: continue
    if not (LO <= s < HI): continue
    r = json.loads(l); k = (r["book"], r.get("id"), ts)
    if k in seen: continue
    seen.add(k); usd = r["p"] * r["q"]
    if r.get("Ma") is not None and 0 <= r["Ma"] < 256: V[r["Ma"]][0] += usd
    if r.get("Ta") is not None and 0 <= r["Ta"] < 256: V[r["Ta"]][1] += usd
rank = sorted(pay, key=lambda u: -pay[u]); pos = {u: i + 1 for i, u in enumerate(rank)}
takers = sorted([u for u, v in V.items() if v[1] > 0.5 * (v[0] + v[1])], key=lambda u: -pay.get(u, 0))
print(f"miners mostly TAKING (> 50% of their $ as taker): {len(takers)} of {len(V)} active")
for u in takers[:15]: print(f"  uid {u:3d}: pay ${pay.get(u, 0):5.0f}/mo (rank {pos.get(u)}) | taker ${V[u][1] / 1e3:6.0f}k maker ${V[u][0] / 1e3:6.0f}k")
mk = sorted([pay.get(u, 0) for u, v in V.items() if v[1] <= 0.5 * (v[0] + v[1])]); tk = sorted([pay.get(u, 0) for u in takers])
print(f"median pay: makers ${mk[len(mk) // 2]:.0f} (n {len(mk)}) | takers ${tk[len(tk) // 2] if tk else 0:.0f} (n {len(tk)})")
