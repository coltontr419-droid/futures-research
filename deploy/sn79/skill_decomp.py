"""Where does the top skill miners' alpha come from? (decisions.md §1244) skill_val.py's exact alpha loop, with each book's mark-to-market
split into the first mid change after one of the uid's own prints ("own impact": the book moving because they just took liquidity) and every
other mid change ("rest"); plus the true P&L that charges fill prices (cash + inventory at the last mid). Same window rules as skill_val.py.
    python skill_decomp.py <tape> <uid> <last sim min>"""
import json, sys
from collections import defaultdict
tape, me, last = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
ev, seen, tmax = defaultdict(list), set(), 0
for line in open(tape):
    r = json.loads(line)
    if "p" in r:
        k = (r["book"], r.get("id"), r["ts"])
        if k in seen: continue
        seen.add(k); ev[r["book"]].append((r["ts"], 1, r)); tmax = max(tmax, r["ts"])
    elif r.get("bid") and r.get("ask"):
        ev[r["book"]].append((r["ts"], 0, (r["bid"] + r["ask"]) / 2))
t0 = tmax - last * 6e10
tot = defaultdict(float)
for b, es in ev.items():
    es.sort(key=lambda e: (e[0], e[1])); mid = None; inv = 0.0; prev = None; own_pending = False
    mtm = own = isum = drift = cash = notl = 0.0; n = 0
    for ts, kind, x in es:
        if ts < t0:
            if kind == 0: mid = x
            continue
        if kind == 0: mid = x; continue
        r = x; p = mid if mid is not None else r["p"]
        if prev is not None and p != prev:
            mtm += inv * (p - prev); drift += p - prev
            if own_pending: own += inv * (p - prev); own_pending = False
        d = 0.0
        if r.get("Ma") == me: d += r["q"] if r["s"] == 1 else -r["q"]
        if r.get("Ta") == me: d += r["q"] if r["s"] == 0 else -r["q"]
        if d: notl += abs(d) * r["p"]; cash -= d * r["p"]; own_pending = True
        inv += d; isum += inv; n += 1; prev = p
    if notl > 0 and n:
        tot["alpha"] += mtm - isum / n * drift; tot["own"] += own; tot["rest"] += mtm - own; tot["drift_adj"] += -isum / n * drift
        tot["true_pnl"] += cash + inv * (prev or 0); tot["notional"] += notl
N = tot["notional"]
print(f"uid {me}: notional {N:,.0f} | alpha {tot['alpha']:+.1f} ({1e4 * tot['alpha'] / N:+.2f} bp) = own impact {tot['own']:+.1f} "
      f"({1e4 * tot['own'] / N:+.2f} bp) + rest {tot['rest']:+.1f} ({1e4 * tot['rest'] / N:+.2f} bp) + drift adj {tot['drift_adj']:+.1f} | "
      f"true P&L at fill prices {tot['true_pnl']:+.1f} ({1e4 * tot['true_pnl'] / N:+.2f} bp)")
