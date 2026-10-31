"""Does order flow carry what the bots know? (decisions.md §1206) From a live QuoteAgent tape with "of" lines (per book per update: new bid /
ask size, near-touch new size within 2 ticks, cancelled size per side): rank IC of order-flow imbalance features with the next 5/30 s mid
move, beside the 5 s taker flow we already use; and the same features just before bot fills on our quotes vs before background fills,
signed in the taker's direction."""
import bisect, json, statistics as st, sys
from collections import defaultdict
import numpy as np
me = int(sys.argv[2]); mids = defaultdict(dict); of = defaultdict(dict); tflow = defaultdict(lambda: defaultdict(float)); fills = []
for line in open(sys.argv[1]):
    r = json.loads(line); s = r["ts"] // 1_000_000_000
    if "of" in r:
        o = of[r["book"]].setdefault(s, defaultdict(float))
        for k, v in r["of"].items(): o[k] += v
    elif "p" in r:
        tflow[r["book"]][s] += r["q"] * (1 if r["s"] == 0 else -1)
        if r["Ma"] == me: fills.append(r)
    elif r.get("bid") and r.get("ask"):
        mids[r["book"]][s] = (r["bid"] + r["ask"]) / 2
def feats(b, s, w=5):
    g = lambda k: sum(of[b].get(s - j, {}).get(k, 0.0) for j in range(w))
    nb, na, nb2, na2, cb, ca = (g(k) for k in ("nb", "na", "nb2", "na2", "cb", "ca"))
    tot = lambda x, y: (x - y) / (x + y) if x + y > 0 else 0.0
    return {"new imbalance": tot(nb, na), "near-touch new imbalance": tot(nb2, na2), "cancel imbalance (ask - bid)": tot(ca, cb),
            "net (new - cancel) imbalance": tot(nb - cb, na - ca), "taker flow 5 s": sum(tflow[b].get(s - j, 0.0) for j in range(w))}
X = defaultdict(list); Y = {5: [], 30: []}
for b in mids:
    for s in sorted(mids[b]):
        if s - 5 not in mids[b]: continue
        f = feats(b, s)
        for h in (5, 30):
            Y[h].append(mids[b][s + h] - mids[b][s] if s + h in mids[b] else np.nan)
        for k, v in f.items(): X[k].append(v)
def ic(x, y):
    x, y = np.array(x, float), np.array(y, float); ok = np.isfinite(y) & np.isfinite(x)
    return np.corrcoef(np.argsort(np.argsort(x[ok])), np.argsort(np.argsort(y[ok])))[0, 1] if ok.sum() > 200 else float("nan")
print(f"book-seconds {len(Y[5])}; rank IC with the next move:")
for k in X: print(f"   {k:30} 5 s {ic(X[k], Y[5]):+.3f}   30 s {ic(X[k], Y[30]):+.3f}")
pre = defaultdict(lambda: defaultdict(list))
for t in fills:
    s = t["ts"] // 1_000_000_000; f = feats(t["book"], s); d = 1 if t["s"] == 0 else -1     # taker bought -> +1
    kind = "bot" if t["Ta"] is not None and t["Ta"] >= 0 else "background"
    for k, v in f.items(): pre[kind][k].append(d * v)
print("feature just before our fills, signed in the taker's direction (bot vs background):")
for k in X:
    b, g = pre["bot"][k], pre["background"][k]
    if b and g: print(f"   {k:30} bot {st.mean(b):+.3f} (n {len(b)})   background {st.mean(g):+.3f} (n {len(g)})")
