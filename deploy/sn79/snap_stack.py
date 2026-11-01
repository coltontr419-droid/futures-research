"""If snap removes our lone-price fills, what do the flow-pull rules add on the rest? (decisions.md §1207). Per tape: our fills classified
shared / alone from the latest depth snapshot before the fill (shared = the fill price is a top-5 level holding more than our fill size);
then on shared fills only, the near-touch flow rule (window W, cooldown C, threshold THR) scored on the second half."""
import bisect, json, sys
from collections import defaultdict
import numpy as np
me = int(sys.argv[1])
def run(path):
    depth = defaultdict(list); mids = defaultdict(list); of = defaultdict(dict); fills = []
    for line in open(path):
        r = json.loads(line); s = r["ts"] // 1_000_000_000
        if "of" in r:
            o = of[r["book"]].setdefault(s, [0.0, 0.0]); o[0] += r["of"].get("nb2", 0.0); o[1] += r["of"].get("na2", 0.0)
        elif "p" in r:
            if r["Ma"] == me: fills.append(r)
        elif r.get("bids") and r.get("asks"):
            depth[r["book"]].append((r["ts"], r["bids"], r["asks"])); mids[r["book"]].append((r["ts"] / 1e9, (r["bid"] + r["ask"]) / 2))
    rows = []
    for t in fills:
        b = t["book"]; dl = depth[b]; j = bisect.bisect_left(dl, (t["ts"],)) - 1; ml = mids[b]; i = bisect.bisect_left(ml, (t["ts"] / 1e9 + 30,))
        if j < 0 or i >= len(ml): continue
        maker = 1 if t["s"] == 1 else -1; lv = dl[j][1] if maker == 1 else dl[j][2]
        shared = any(abs(p - t["p"]) < 1e-9 and q > t["q"] + 1e-9 for p, q in lv)
        s = t["ts"] // 1_000_000_000
        def near(end, w):
            nb = sum(of[b].get(end - k, [0, 0])[0] for k in range(w)); na = sum(of[b].get(end - k, [0, 0])[1] for k in range(w))
            return (nb - na) / (nb + na) if nb + na > 0 else 0.0
        sig = {(w, c): max(-maker * near(s - 1 - k, w) for k in range(c + 1)) for w in (5, 10) for c in (0, 3)}
        rows.append((shared, maker * (ml[i][1] - t["p"]) / 0.01, sig))
    return rows
allr = []
for p in sys.argv[2:]:
    r = run(p); allr.append(r)
    sh = np.array([x[0] for x in r]); mo = np.array([x[1] for x in r])
    print(f"{p.split('/')[-1]}: {len(r)} fills | shared {sh.mean():.0%} at {mo[sh].mean():+.2f} | alone {(~sh).mean():.0%} at {mo[~sh].mean():+.2f} | all {mo.mean():+.2f}")
print("on SHARED fills only (what snap leaves), second half of each tape, pooled:")
for key in ((5, 0), (10, 0), (10, 3)):
    for thr in (None, 0.3, 0.5):
        kept = n = tot = 0
        for r in allr:
            h = [x for x in r[len(r) // 2:] if x[0]]; mo = np.array([x[1] for x in h])
            k = np.ones(len(h), bool) if thr is None else np.array([x[2][key] <= thr for x in h])
            kept += mo[k].sum(); n += k.sum(); tot += len(h)
        if thr is None and key != (5, 0): continue
        print(f"   {'no flow rule' if thr is None else f'window {key[0]}s cooldown {key[1]}s thr {thr}':32}: {kept / n:+.2f} per fill ({n / tot:.0%} of shared fills kept)")
