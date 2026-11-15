"""Inventory pattern on $300 books (MEASURED, inventory from 0 at window start): per uid — mean |inventory| $ per book, mean holding time of a position
(seconds between sign flips / returns to ~flat), inventory turnover, and the alpha split: is P&L earned while the position is large or small, and does
inventory lean with the subsequent 60-s mid move (corr of inv_$ with next-60-s mid change)?  python invstudy.py tape lo hi uids..."""
import json, sys, statistics as st
from collections import defaultdict
tape, LO, HI = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
mids = defaultdict(dict); fills = defaultdict(list); seen = set()
for line in open(tape, errors="ignore"):
    i = line.find('"ts": ')
    if i < 0 or '"book": ' not in line: continue
    try: ts = int(line[i + 6:line.index(",", i)]); s = ts // 10**9
    except ValueError: continue
    if s < LO - 5 or s > HI + 65: continue
    try: r = json.loads(line)
    except ValueError: continue
    import os; L0, L1 = (int(x) for x in os.environ.get("BOOKS", "0-127").split("-"))
    if not (L0 <= r["book"] <= L1): continue
    if '"bid": ' in line and r.get("bid") and r.get("ask"): mids[r["book"]][s] = (r["bid"] + r["ask"]) / 2
    elif '"Ma"' in line:
        k = (r["book"], r.get("id"), ts)
        if k in seen or not (LO <= s < HI): continue
        seen.add(k)
        for u, sg in ((r.get("Ma"), 1 if r["s"] == 1 else -1), (r.get("Ta"), 1 if r["s"] == 0 else -1)):
            if u in US: fills[(u, r["book"])].append((s, sg * r["q"]))
for u in U:
    absinv, hold, xs, ys, turn = [], [], [], [], []
    for (uu, b), fs in fills.items():
        if uu != u: continue
        fs.sort(); md = mids[b]; inv = 0.0; j = 0; start = None; last_sign = 0; notional = 0.0
        for s in range(LO, HI):
            while j < len(fs) and fs[j][0] <= s:
                inv += fs[j][1]; notional += abs(fs[j][1]); j += 1
            m = md.get(s)
            if m is None: continue
            iv = inv * m; absinv.append(abs(iv))
            sign = (iv > 50) - (iv < -50)
            if sign != last_sign:
                if last_sign != 0 and start is not None: hold.append(s - start)
                start = s if sign else None; last_sign = sign
            if s % 10 == 0 and md.get(s + 60):
                xs.append(iv); ys.append((md[s + 60] - m) / m * 1e4)
        if fs: turn.append(notional * (md.get(LO) or md.get(LO + 1) or 300) / max(1.0, st.mean([abs(x) for x in [inv]]) + 1))
    if not absinv: print(f"{u}: no data"); continue
    mx = st.mean(xs); my = st.mean(ys); cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)
    corr = cov / (st.pstdev(xs) * st.pstdev(ys) + 1e-12)
    print(f"  {u}: mean |inv| ${st.mean(absinv):,.0f} per book (p90 ${sorted(absinv)[int(.9 * len(absinv))]:,.0f}) | position hold median {st.median(hold) if hold else 0:.0f} s"
          f" (n {len(hold)}) | corr(inventory $, next-60-s mid move) {corr:+.3f} | books {len(turn)}")
