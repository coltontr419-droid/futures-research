"""$300 books: taker position management for given uids — per-book inventory ($) path from ALL their fills (taker + maker), max |position| per book, |position| at each taker trade,
how positions shrink (opposite taker trades vs opposite maker fills vs never in window), time between taker trades on the same book, same-side repeats."""
import json, sys, collections, statistics as st, numpy as np
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
E = collections.defaultdict(list); seen = set()
for l in open(tape, "rb"):
    if b'"Ta"' not in l: continue
    i = l.find(b'"ts": '); ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO or s >= HI: continue
    r = json.loads(l); bk = r["book"]
    if bk >= 128: continue
    k = (bk, r.get("id"), ts)
    if k in seen: continue
    seen.add(k); v = r["p"] * r["q"]
    if r.get("Ta") in US: E[r["Ta"]].append((ts, bk, (1 if r["s"] == 0 else -1) * v, "T"))
    if r.get("Ma") in US: E[r["Ma"]].append((ts, bk, (1 if r["s"] == 1 else -1) * v, "M"))
for u in U:
    ev = sorted(E[u]); inv = collections.defaultdict(float); mx = collections.defaultdict(float); at_trade = []; shrink = collections.Counter(); gaps = []; last = {}; same = 0; tot_t = 0
    lastside = {}
    for ts, bk, sv, kind in ev:
        before = inv[bk]; inv[bk] += sv; mx[bk] = max(mx[bk], abs(inv[bk]))
        if abs(inv[bk]) < abs(before) - 1e-9: shrink[kind] += 1
        if kind == "T":
            tot_t += 1; at_trade.append(abs(inv[bk]))
            s = ts // 10**9
            if bk in last: gaps.append(s - last[bk])
            if lastside.get(bk) == (sv > 0): same += 1
            last[bk] = s; lastside[bk] = sv > 0
    if not tot_t: print(f"  {u}: none"); continue
    M = np.array(list(mx.values())); A = np.array(at_trade); end = np.array([abs(v) for v in inv.values()])
    print(f"  {u}: taker trades {tot_t} on {len(last)} books | max |position| per book median ${np.median(M):,.0f} p90 ${np.percentile(M, 90):,.0f} max ${M.max():,.0f} | |position| after a taker trade median ${np.median(A):,.0f}"
          f" p90 ${np.percentile(A, 90):,.0f} | shrinking events: by taker {shrink['T']}, by maker fill {shrink['M']} | gap between taker trades on a book median {st.median(gaps) if gaps else 0:.0f} s"
          f" | same side as the last trade on that book {same / max(1, tot_t - len(last)):.0%} | open |position| at window end median ${np.median(end):,.0f}")
