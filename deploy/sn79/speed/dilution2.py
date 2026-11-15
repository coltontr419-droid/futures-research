"""Volume dilution check (validator alpha loop of skill_ab.py over one window): per $300 book, alpha, our filled notional, bp = alpha/notional.
Is our problem dilution (positive alpha too small for our big notional) or sign (alpha itself negative)?  python dilution.py tape lo hi uids..."""
import json, sys, statistics as st
from collections import defaultdict
sys.path.insert(0, "/opt/mvtrx/repo")
tape, LO, HI = sys.argv[1], int(sys.argv[2]) * 10 ** 9, int(sys.argv[3]) * 10 ** 9; U = [int(u) for u in sys.argv[4:]]
ev, seen = defaultdict(list), set()
for line in open(tape, errors="ignore"):
    i = line.find('"ts": ')
    if i < 0 or '"book": ' not in line: continue
    try: ts = int(line[i + 6:line.index(",", i)])
    except ValueError: continue
    if ts < LO - 60 * 10 ** 9 or ts >= HI: continue
    try: r = json.loads(line)
    except ValueError: continue
    import os; L0, L1 = (int(x) for x in os.environ.get("BOOKS", "0-127").split("-"))
    if not (L0 <= r["book"] <= L1): continue
    if '"Ma"' in line:
        k = (r["book"], r.get("id"), ts)
        if k in seen: continue
        seen.add(k); ev[r["book"]].append((ts, 1, r["p"], r["q"], r["s"], r.get("Ma"), r.get("Ta")))
    elif '"bid": ' in line and r.get("bid") and r.get("ask"):
        ev[r["book"]].append((ts, 0, (r["bid"] + r["ask"]) / 2))
A = {u: {} for u in U}; N = {u: {} for u in U}
for b, es in ev.items():
    es.sort(key=lambda e: (e[0], e[1])); mid = None; stt = {u: [0.0, 0.0, 0.0, 0.0] for u in U}; drift = 0.0; n = 0; prev = None
    for e in es:
        if e[0] < LO:
            if e[1] == 0: mid = e[2]
            continue
        if e[1] == 0: mid = e[2]; continue
        _, _, px, q, s, ma, ta = e; p = mid if mid is not None else px
        if prev is not None and p != prev:
            for u in U: stt[u][1] += stt[u][0] * (p - prev)
            drift += p - prev
        for u in U:
            d = 0.0
            if ma == u: d += q if s == 1 else -q
            if ta == u: d += q if s == 0 else -q
            if d: stt[u][3] += abs(d) * px
            stt[u][0] += d; stt[u][2] += stt[u][0]
        n += 1; prev = p
    for u in U:
        inv, mtm, isum, notl = stt[u]
        if notl > 0 and n: A[u][b] = mtm - isum / n * drift; N[u][b] = notl
print(f"window sim {LO // 10**9}-{HI // 10**9}: books $BOOKS, validator alpha (mark = mid, drift stripped)")
for u in U:
    bps = sorted(1e4 * A[u][b] / N[u][b] for b in A[u]); nts = [N[u][b] for b in A[u]]
    if not bps: continue
    q = lambda p: bps[int(p * (len(bps) - 1))]
    pos = sum(x > 0 for x in bps); kp = sum(x >= 2.3 for x in bps); kn = sum(x <= -2.3 for x in bps)
    print(f"  {u}: books {len(bps)} | notional/book median ${st.median(nts) / 1e3:.0f}k | bp/book p10 {q(.1):+.2f} p25 {q(.25):+.2f} median {q(.5):+.2f} p75 {q(.75):+.2f} p90 {q(.9):+.2f}"
          f" | positive {pos / len(bps):.0%} | kept +{kp} −{kn} (|bp| ≥ 2.3)")
    for k in (2, 5, 10):
        kp2 = sum(x * k >= 2.3 for x in bps); kn2 = sum(x * k <= -2.3 for x in bps)
        print(f"      if the SAME alpha came on 1/{k} of the notional: kept +{kp2} −{kn2}")
