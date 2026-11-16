"""Taker profile per uid and class: trades (aggregated per book/sec/side), $, median $/trade, markout of the MID from just before the trade (20/60/120 s) and vs the trade price (cost)."""
import json, sys, collections, statistics as st
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); U = set(int(u) for u in sys.argv[4:])
S = collections.defaultdict(dict); T = collections.defaultdict(lambda: [0.0, 0.0, 0]); seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 5 or s > HI + 125: continue
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
        if r.get("Ta") in U and LO <= s < HI:
            x = T[(r["Ta"], bk, s, r["s"])]; x[0] += r["p"] * r["q"]; x[1] += r["q"]; x[2] += 1
cls = lambda b: "$300" if b < 128 else ("$30" if b < 192 else "4dec")
R = collections.defaultdict(list)
for (u, bk, s, side), (v, q, n) in T.items():
    a = S[bk].get(s - 1); m = [S[bk].get(s + h) for h in (20, 60, 120)]
    if not a or None in m: continue
    sg = 1 if side == 0 else -1          # taker side 0 = BUY (as in our tape: s = maker side? check sign below)
    m0 = (a[0] + a[1]) / 2; p = v / q
    R[(u, cls(bk))].append((v, [sg * ((x[0] + x[1]) / 2 - m0) / m0 * 1e4 for x in m], sg * (m0 - p) / m0 * 1e4, s, bk))
for (u, c), L in sorted(R.items()):
    V = sum(x[0] for x in L)
    mo = [sum(x[0] * x[1][i] for x in L) / V for i in range(3)]; cost = sum(x[0] * x[2] for x in L) / V
    print(f"  {u} {c:4s}: trades {len(L):4d} ${V/1e3:6.0f}k | $/trade med ${st.median(x[0] for x in L):,.0f} | books {len(set(x[4] for x in L)):3d} | mid move after +20 {mo[0]:+.2f} +60 {mo[1]:+.2f} +120 {mo[2]:+.2f} bp | price vs mid {cost:+.2f} bp")
