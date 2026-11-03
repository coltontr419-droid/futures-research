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

TICK, COOL = 0.01, 0
model, path = json.load(open(sys.argv[1])), sys.argv[2]
SIZE = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
EVERY = 1
BOOKS = set(map(int, open(sys.argv[4]).read().split())) if len(sys.argv) > 4 else None   # restrict to these books
mids, depth, of, fl, fees = defaultdict(dict), defaultdict(dict), defaultdict(lambda: defaultdict(lambda: [0.0] * 6)), defaultdict(lambda: defaultdict(float)), []
for line in open(path):
    r = json.loads(line); s = r["ts"] // 1_000_000_000
    if BOOKS is not None and r["book"] not in BOOKS:
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

sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_floored, kappa_of_alpha
"""Skill sleeve replay (decisions.md §1211 add. 20): enter |pred| > X at the next second, hold H s, exit; validator-style per-book alpha
= Σ side·q·(mid_exit − mid_entry) − mean inventory × drift; notional = q·(entry fill + exit fill); hurdle 2.3 bp of notional; kappa over
kept books (floor 0, min 4). Halves of the tape (by entry time) scored separately."""
def run(X, H, half):
    A, N, INV = defaultdict(float), defaultdict(float), defaultdict(float); T = {}
    for b, ms in mids.items():
        secs = sorted(ms); t0, t1 = secs[0], secs[-1]; T[b] = (t1 - t0); busy = -1
        for s in secs:
            fr = (s - t0) / max(t1 - t0, 1)
            if (half == 1 and fr >= 0.5) or (half == 2 and fr < 0.5): continue
            if s <= busy or s - 120 not in ms or s + 1 not in ms or s + 1 + H not in ms: continue
            bids, asks = depth[b][s]; mid = ms[s]
            imb = lambda k: ratio(sum(x[1] for x in bids[:k]), sum(x[1] for x in asks[:k]))
            micro = (bids[0][0] * asks[0][1] + asks[0][0] * bids[0][1]) / (bids[0][1] + asks[0][1]) - mid
            o5 = [sum(of[b].get(s - j, [0.0] * 6)[i] for j in range(5)) for i in range(6)]
            f = {"flow5": sum(fl[b].get(s - j, 0.0) for j in range(5)), "ret5": mid - ms.get(s - 5, mid), "ret30": mid - ms.get(s - 30, mid),
                 "ret120": mid - ms[s - 120], "imb1": imb(1), "imb5": imb(5), "micro": micro,
                 "of_new": ratio(o5[0], o5[1]), "of_near": ratio(o5[2], o5[3]), "of_cancel": ratio(o5[5], o5[4])}
            p = float(np.sum(w * (np.array([f[n] for n in names]) - mu) / np.where(sd > 0, sd, 1.0))) / TICK
            if abs(p) <= X: continue
            side = 1 if p > 0 else -1; nb, na = depth[b][s + 1]; xb, xa = depth[b][s + 1 + H]
            q = min(SIZE, (na if side > 0 else nb)[0][1])
            ein = (na if side > 0 else nb)[0][0]; eout = (xb if side > 0 else xa)[0][0]
            A[b] += side * q * (ms[s + 1 + H] - ms[s + 1]); N[b] += q * (ein + eout); INV[b] += side * q * H
            busy = s + 1 + H
    alpha = {}
    for b in A:
        drift = ms_end[b] - ms_start[b]; alpha[b] = A[b] - INV[b] / max(T[b], 1) * drift
    kept = [alpha[b] for b in alpha if N[b] > 0 and abs(alpha[b]) >= 2.3e-4 * N[b]]
    bp = sorted(1e4 * alpha[b] / N[b] for b in alpha if N[b] > 0)
    return len(alpha), len(kept), sum(k > 0 for k in kept), kappa_floored(kept, 0.0, 4), (bp[len(bp) // 2] if bp else 0.0), sum(N.values())
ms_start = {b: ms[min(ms)] for b, ms in mids.items()}; ms_end = {b: ms[max(ms)] for b, ms in mids.items()}
print(f"books {len(mids)} | size {SIZE}")
for X in (2.0, 4.0, 6.0):
    for H in (30, 60, 120):
        r1 = run(X, H, 1); r2 = run(X, H, 2)
        print(f"|pred|>{X:.0f} hold {H:3d}s | H1: books {r1[0]:3d} kept {r1[1]:3d} (+{r1[2]}) kappa {r1[3]:+.2f} α/N med {r1[4]:+.2f}bp N {r1[5]:,.0f} | H2: kept {r2[1]:3d} (+{r2[2]}) kappa {r2[3]:+.2f} α/N med {r2[4]:+.2f}bp", flush=True)
