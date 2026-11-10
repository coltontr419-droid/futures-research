"""Does x4's $300 inside quoting step inside its OWN best order? From x4's queue records (side, price, qty ahead, qty, id) + book snapshots.  python3 selfpenny.py <tape> <T0>"""
import json, sys, collections
tape, T0 = sys.argv[1], float(sys.argv[2]); SN = {}; n = collections.Counter(); runs = collections.Counter(); sp_alone = collections.Counter(); sp_all = collections.Counter()
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < T0: continue
    if b'"bids"' in l:
        r = json.loads(l)
        if r["book"] < 63 and r["bids"] and r["asks"]: SN[(r["book"], int(t))] = r
    elif b'"queue"' in l:
        r = json.loads(l); b = r["book"]
        if b >= 63: continue
        s = SN.get((b, int(t)))
        if not s: continue
        sprd = round((s["ask"] - s["bid"]) / 0.01); sp_all[min(sprd, 9)] += 1
        for side, best, top in ((0, s["bid"], s["bids"][0][1]), (1, s["ask"], s["asks"][0][1])):
            mine = sorted((q for q in r["queue"] if q[0] == side), key=lambda q: -q[1] if side == 0 else q[1])
            if not mine: continue
            n["sides"] += 1
            at_best = [q for q in mine if abs(q[1] - best) < 1e-9]
            if at_best and abs(at_best[0][3] - top) < 1e-6:
                n["alone at best"] += 1; sp_alone[min(sprd, 9)] += 1
                nxt = best - 0.01 if side == 0 else best + 0.01
                if any(abs(q[1] - nxt) < 1e-9 for q in mine): n["alone at best + own order 1 tick behind"] += 1
            # consecutive-tick run of our own orders starting at our best
            px = [q[1] for q in mine]; k = 1
            while k < len(px) and abs(abs(px[k] - px[k - 1]) - 0.01) < 1e-9: k += 1
            runs[min(k, 4)] += 1
print(dict(n)); print("our orders at consecutive ticks from our best (run length: count):", dict(sorted(runs.items())))
print("spread (ticks) in all $300 snapshots with our queue:", dict(sorted(sp_all.items())))
print("spread (ticks) when we are ALONE at the best:", dict(sorted(sp_alone.items())))
