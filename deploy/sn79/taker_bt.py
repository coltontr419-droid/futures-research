"""SN79 taker replay (decisions.md §1211 addendum 5): would TAKING on the live order-flow predictor make money? Out of sample (model30_of
was fitted on earlier tapes). Per book-second the live model's 30 s prediction is recomputed from the tape (lean_scan.py features); when
|pred| > X ticks and the book had no trade of ours in the last COOL s, cross the spread one state LATER (the next second's best ask / bid,
our live delay) for SIZE units capped at the top level's size; mark at the mid 30 s after. Costs: the taker fee measured from the tape
(median Tf / notional) on entry; "round trip" also pays the fee again plus half the spread to exit. Halves of the tape, books positive.

    python taker_bt.py <model.json> <tape.jsonl> [size units]
"""
import json
import sys
from collections import defaultdict

import numpy as np

TICK, H, COOL = 0.01, 30, 30
model, path = json.load(open(sys.argv[1])), sys.argv[2]
SIZE = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
EVERY = int(sys.argv[4]) if len(sys.argv) > 4 else 1        # keep books with id % EVERY == 0 (memory: depth per book-second)
mids, depth, of, fl, fees = defaultdict(dict), defaultdict(dict), defaultdict(lambda: defaultdict(lambda: [0.0] * 6)), defaultdict(lambda: defaultdict(float)), []
for line in open(path):
    r = json.loads(line); s = r["ts"] // 1_000_000_000
    if r["book"] % EVERY:
        continue
    if "of" in r:
        o = of[r["book"]][s]
        for i, k in enumerate(("nb", "na", "nb2", "na2", "cb", "ca")):
            o[i] += r["of"].get(k, 0.0)
    elif "p" in r:
        fl[r["book"]][s] += r["q"] * (1 if r["s"] == 0 else -1)
        if r.get("Tf") and r["q"] > 0 and len(fees) < 200000:
            fees.append(r["Tf"] / (r["q"] * r["p"]))
    elif r.get("bids") and r.get("asks"):
        mids[r["book"]][s] = (r["bid"] + r["ask"]) / 2; depth[r["book"]][s] = (tuple(map(tuple, r["bids"][:5])), tuple(map(tuple, r["asks"][:5])))
fee = float(np.median(fees)) if fees else 0.0         # signed: Tf < 0 is a taker REBATE (debeta.py: a negative fee adds); de-beta skill ignores fees
ratio = lambda x, y: (x - y) / (x + y) if x + y > 0 else 0.0
names, mu, sd, w = model["names"], np.array(model["mu"]), np.array(model["sd"]), np.array(model["w"])
trades = {x: [] for x in (2.0, 3.0, 4.0, 5.0)}
for b, ms in mids.items():
    secs = sorted(ms); t0, t1 = secs[0], secs[-1]; last = {x: -10 ** 9 for x in trades}
    for s in secs:
        if s - 120 not in ms or s + 1 not in ms or s + 1 + H not in ms:
            continue
        bids, asks = depth[b][s]; mid = ms[s]
        imb = lambda k: ratio(sum(x[1] for x in bids[:k]), sum(x[1] for x in asks[:k]))
        micro = (bids[0][0] * asks[0][1] + asks[0][0] * bids[0][1]) / (bids[0][1] + asks[0][1]) - mid
        o5 = [sum(of[b].get(s - j, [0.0] * 6)[i] for j in range(5)) for i in range(6)]
        f = {"flow5": sum(fl[b].get(s - j, 0.0) for j in range(5)), "ret5": mid - ms.get(s - 5, mid), "ret30": mid - ms.get(s - 30, mid),
             "ret120": mid - ms[s - 120], "imb1": imb(1), "imb5": imb(5), "micro": micro,
             "of_new": ratio(o5[0], o5[1]), "of_near": ratio(o5[2], o5[3]), "of_cancel": ratio(o5[5], o5[4])}
        p = float(np.sum(w * (np.array([f[n] for n in names]) - mu) / np.where(sd > 0, sd, 1.0))) / TICK
        nb, na = depth[b][s + 1]
        for x in trades:
            if abs(p) <= x or s - last[x] < COOL:
                continue
            side = 1 if p > 0 else -1
            px, top = (na[0][0], na[0][1]) if side > 0 else (nb[0][0], nb[0][1])
            q = min(SIZE, top); later = ms[s + 1 + H]; spread = na[0][0] - nb[0][0]
            gross = side * (later - px) / TICK
            entry = gross - fee * px / TICK
            rt = entry - fee * later / TICK - spread / 2 / TICK
            trades[x].append((b, s, (s - t0) / max(t1 - t0, 1), q, gross, entry, rt)); last[x] = s
print(f"taker fee (median Tf / notional) {fee * 1e4:.2f} bp ≈ {fee * 300 / TICK:.2f} ticks at price 300 | size {SIZE} units, cooldown {COOL} s")
for x, T in trades.items():
    if not T:
        continue
    A = np.array([t[2:] for t in T])
    tot = lambda col, m=slice(None): float(np.sum(A[m, 1] * A[m, col]))
    h1 = A[:, 0] < 0.5
    perbook, gbook = defaultdict(float), defaultdict(float)
    for t in T:
        perbook[t[0]] += t[3] * t[5]; gbook[t[0]] += t[3] * t[4]
    print(f"|pred| > {x:3.1f} ticks: {len(T):6d} trades | per-trade gross {A[:, 2].mean():+.2f}, after entry fee {A[:, 3].mean():+.2f}, round trip "
          f"{A[:, 4].mean():+.2f} | after-fee halves {A[h1, 3].mean():+.2f} / {A[~h1, 3].mean():+.2f} | books positive after fee "
          f"{sum(v > 0 for v in perbook.values())} of {len(perbook)} | total after fee {tot(3):+.0f} tick·units")
    print(f"      GROSS (what de-beta skill sees): halves {A[h1, 2].mean():+.2f} / {A[~h1, 2].mean():+.2f} | books positive {sum(v > 0 for v in gbook.values())} "
          f"of {len(gbook)} | total {tot(2):+.0f} tick·units | t {A[:, 2].mean() / (A[:, 2].std(ddof=1) / np.sqrt(len(A))):.1f}")
