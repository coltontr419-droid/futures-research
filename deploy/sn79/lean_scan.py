"""Lean scan (decisions.md §1207): recompute the live model's 30 s prediction per book-second from a tape (same features as fit_orderflow.py /
QuoteAgent._predict), then for every maker fill (ours and other miners') take the prediction of the second before the fill, signed so +
means the fill was on the side the model favoured (we bought and it predicted a rise). Markouts by signed prediction, ours vs field; and
a one-sided rule for us — drop the side the prediction opposes once |pred| > X ticks — scored on the second half of our fills.

    python lean_scan.py <our uid> <model.json> <tape.jsonl> [more tapes]
"""
import bisect
import json
import sys
from collections import defaultdict

import numpy as np

TICK, H = 0.01, 30


def preds(path, model):
    mids, depth, of, fl, fills = defaultdict(dict), defaultdict(dict), defaultdict(lambda: defaultdict(lambda: [0.0] * 6)), defaultdict(lambda: defaultdict(float)), []
    midl = defaultdict(list)
    for line in open(path):
        r = json.loads(line); s = r["ts"] // 1_000_000_000
        if "of" in r:
            o = of[r["book"]][s]
            for i, k in enumerate(("nb", "na", "nb2", "na2", "cb", "ca")):
                o[i] += r["of"].get(k, 0.0)
        elif "p" in r:
            fl[r["book"]][s] += r["q"] * (1 if r["s"] == 0 else -1)
            if r.get("Ma") is not None and r["Ma"] >= 0:
                fills.append(r)
        elif r.get("bids") and r.get("asks"):
            mids[r["book"]][s] = (r["bid"] + r["ask"]) / 2; depth[r["book"]][s] = (r["bids"], r["asks"])
            midl[r["book"]].append((r["ts"] / 1e9, (r["bid"] + r["ask"]) / 2))
    ratio = lambda x, y: (x - y) / (x + y) if x + y > 0 else 0.0
    names, mu, sd, w = model["names"], np.array(model["mu"]), np.array(model["sd"]), np.array(model["w"])
    P = {}
    for b, ms in mids.items():
        for s in ms:
            if s - 120 not in ms:
                continue
            bids, asks = depth[b][s]; mid = ms[s]
            imb = lambda k: ratio(sum(x[1] for x in bids[:k]), sum(x[1] for x in asks[:k]))
            micro = (bids[0][0] * asks[0][1] + asks[0][0] * bids[0][1]) / (bids[0][1] + asks[0][1]) - mid
            o5 = [sum(of[b].get(s - j, [0.0] * 6)[i] for j in range(5)) for i in range(6)]
            f = {"flow5": sum(fl[b].get(s - j, 0.0) for j in range(5)), "ret5": mid - ms.get(s - 5, mid), "ret30": mid - ms.get(s - 30, mid),
                 "ret120": mid - ms[s - 120], "imb1": imb(1), "imb5": imb(5), "micro": micro,
                 "of_new": ratio(o5[0], o5[1]), "of_near": ratio(o5[2], o5[3]), "of_cancel": ratio(o5[5], o5[4])}
            x = np.array([f[n] for n in names])
            P[(b, s)] = float(np.sum(w * (x - mu) / np.where(sd > 0, sd, 1.0))) / TICK      # ticks
    out = []
    for t in fills:
        b, s = t["book"], t["ts"] // 1_000_000_000; p = P.get((b, s - 1))
        ml = midl[b]; i = bisect.bisect_left(ml, (t["ts"] / 1e9 + H,))
        if p is None or i >= len(ml):
            continue
        maker = 1 if t["s"] == 1 else -1
        out.append((t["Ma"], maker * p, maker * (ml[i][1] - t["p"]) / TICK, t["Ta"] is not None and t["Ta"] >= 0))
    return out


def main():
    me, model = int(sys.argv[1]), json.load(open(sys.argv[2]))
    ours, field = [], []
    for p in sys.argv[3:]:
        rows = preds(p, model); o = [r for r in rows if r[0] == me]; ours.append(o); field += [r for r in rows if r[0] != me]
        print(f"{p}: our fills {len(o)}, field fills {len(rows) - len(o)}")
    allours = [r for o in ours for r in o]
    for who, R in (("ours", allours), ("field", field)):
        sp = np.array([r[1] for r in R]); mo = np.array([r[2] for r in R])
        print(f"== {who}: share of fills on the favoured side (signed pred > 0) {np.mean(sp > 0):.0%}; signed pred mean {sp.mean():+.2f} ticks")
        for lo, hi in ((-99, -2), (-2, -1), (-1, -0.5), (-0.5, 0), (0, 0.5), (0.5, 1), (1, 2), (2, 99)):
            m = (sp > lo) & (sp <= hi)
            if m.sum() >= 30:
                print(f"   signed pred ({lo:+},{hi:+}]: {m.mean():5.1%} of fills, markout {mo[m].mean():+.2f}")
    print("one-sided rule for us (drop the opposed side when |pred| > X), second half of each tape:")
    for x in (0.25, 0.5, 0.75, 1.0, 1.5):
        kept = n = tot = 0; base = 0
        for o in ours:
            h = o[len(o) // 2:]; sp = np.array([r[1] for r in h]); mo = np.array([r[2] for r in h]); k = sp >= -x
            kept += mo[k].sum(); n += k.sum(); tot += len(h); base += mo.sum()
        print(f"   X {x:4}: kept {kept / n:+.2f} per fill ({n / tot:.0%} kept), kept total {kept:+.0f} (no rule {base:+.0f} = {base / tot:+.2f} per fill)")


if __name__ == "__main__":
    main()
