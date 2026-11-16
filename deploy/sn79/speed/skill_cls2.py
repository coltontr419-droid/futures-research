"""skill_val.py's exact validator alpha loop, for several uids at once, reported per asset class (0-127 / 128-191 / 192-255).
   python skill_cls.py <tape> <last sim min> uid1 uid2 ..."""
import json, sys
from collections import defaultdict
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_floored, hurdle_filter
tape, last = sys.argv[1], float(sys.argv[2]); U = [int(u) for u in sys.argv[3:]]; US = set(U)
ev, seen, tmax = defaultdict(list), set(), 0
for line in open(tape):
    i = line.find('"ts": ')
    if i < 0: continue
    ts = int(line[i + 6:line.index(",", i)])
    pass
    if '"p": ' in line and '"Ma"' in line:
        r = json.loads(line); k = (r["book"], r.get("id"), ts)
        if k in seen: continue
        seen.add(k); ev[r["book"]].append((ts, 1, r["p"], r["q"], r["s"], r.get("Ma"), r.get("Ta"))); tmax = max(tmax, ts)
    elif '"bid": ' in line:
        r = json.loads(line)
        if r.get("bid") and r.get("ask"): ev[r["book"]].append((ts, 0, (r["bid"] + r["ask"]) / 2))
t0 = tmax - last * 6e10
A = {u: {} for u in U}; N = {u: {} for u in U}
for b, es in ev.items():
    es.sort(key=lambda e: (e[0], e[1])); mid = None
    st = {u: [0.0, 0.0, 0.0, 0.0] for u in U}  # inv, mtm, isum, notl
    drift = 0.0; n = 0; prev = None
    for e in es:
        if e[0] < t0:
            if e[1] == 0: mid = e[2]
            continue
        if e[1] == 0: mid = e[2]; continue
        _, _, px, q, s, ma, ta = e; p = mid if mid is not None else px
        if prev is not None and p != prev:
            for u in U: st[u][1] += st[u][0] * (p - prev)
            drift += p - prev
        for u in U:
            d = 0.0
            if ma == u: d += q if s == 1 else -q
            if ta == u: d += q if s == 0 else -q
            if d: st[u][3] += abs(d) * px
            st[u][0] += d; st[u][2] += st[u][0]
        n += 1; prev = p
    for u in U:
        inv, mtm, isum, notl = st[u]
        if notl > 0 and n: A[u][b] = mtm - isum / n * drift; N[u][b] = notl
CL = [("$300 0-127", range(0, 128), 20), ("$30 128-191", range(128, 192), 10), ("4dec 192-255", range(192, 256), 10)]
print(f"window: last {last:.0f} sim min (sim {t0/1e9:.0f}-{tmax/1e9:.0f} s)")
for name, rg, bar in CL:
    print(f"== {name} (skill bar {bar} books)")
    for u in U:
        a = {b: A[u][b] for b in rg if b in A[u]}; nt = {b: N[u][b] for b in a}
        if not a: print(f"  uid {u:3d}: no fills"); continue
        k = hurdle_filter({u: a}, {u: nt}, 2.3)[u]
        kp = sum(v > 0 for v in k.values()); kap = kappa_floored(list(k.values()), 0.0, 4)
        tot_n = sum(nt.values()); sa = sum(a.values())
        print(f"  uid {u:3d}: books {len(a):3d} | notional ${tot_n/1e3:6.0f}k (${tot_n/len(a)/1e3:4.1f}k/book) | Σα {sa:+8.1f} = {1e4*sa/tot_n:+5.2f} bp | "
              f"kept {len(k):3d} (+{kp} −{len(k)-kp}) | kappa {kap:+.2f} | {'ELIGIBLE' if kap > 0 and len(k) >= bar else '-'}")
