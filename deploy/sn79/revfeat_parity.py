"""Parity check (decisions.md §1233): replay the last N MB of x1's tape through revfeat.RevFeatures second by second and compare its
features / forecast with predfeat.py's rows for the same (book, second) in pred_test.npz (built from the same tape end)."""
import json, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/opt/mvtrx")
from revfeat import RevFeatures
MB = int(sys.argv[1]); rf = RevFeatures("/opt/mvtrx/agents/rev_model.json")
te = np.load("/opt/mvtrx/pred_test.npz"); want = {(int(b), int(t)): i for i, (b, t) in enumerate(zip(te["book"], te["ts"]))}
pend_tr, pend_of = defaultdict(list), defaultdict(float); got = []
with open("/opt/mvtrx/live_tape_x1_size6.jsonl", "rb") as fh:
    fh.seek(0, 2); n = fh.tell(); fh.seek(max(0, n - MB * 1_000_000)); fh.readline()
    for l in fh:
        r = json.loads(l); b = r.get("book"); t = r["ts"] // 1_000_000_000
        if "p" in r:
            pend_tr[b].append((t, r["p"], r["q"], r.get("Ta")))
        elif "of" in r:
            o = r["of"]; pend_of[(b, t)] += (o.get("nb", 0) - o.get("na", 0)) - (o.get("cb", 0) - o.get("ca", 0))
        elif "bid" in r and r.get("bid") and r.get("ask"):
            m = (r["bid"] + r["ask"]) / 2; bd = sum(q for _, q in r.get("bids", [])); ad = sum(q for _, q in r.get("asks", []))
            rf.update(b, t, m, r.get("fund"), (bd - ad) / (bd + ad) if bd + ad else 0.0, (r["ask"] - r["bid"]) / m * 1e4,
                      pend_tr.pop(b, ()), pend_of.pop((b, t), 0.0))
            i = want.get((b, t))
            if i is not None:
                x = rf.features(b, t)
                if x is not None: got.append((i, x, rf.predict(b, t)))
print("matched rows:", len(got))
Xo0 = te["X"][[g[0] for g in got]]; Xl0 = np.array([g[1] for g in got])
for k, nm in ((12, "flow10"), (13, "book10")): print("  scale %s: offline sd %.3f, live sd %.3f" % (nm, Xo0[:, k].std(), Xl0[:, k].std()))
names = list(te["names"]); Xo = te["X"][[g[0] for g in got]]; Xl = np.array([g[1] for g in got])
for k, nm in enumerate(names):
    a, c = Xo[:, k], Xl[:, k]
    cor = np.corrcoef(a, c)[0, 1] if a.std() > 0 and c.std() > 0 else float("nan")
    print("  %-9s corr %+.3f | median offline %+.3f live %+.3f" % (nm, cor, np.median(a), np.median(c)))
m = json.load(open("/opt/mvtrx/agents/rev_model.json")); mu, sd, w = np.array(m["mu"]), np.array(m["sd"]), np.array(m["w"])
po = np.clip((Xo - mu) / sd, -6, 6) @ w + m["b"]; pl = np.array([g[2] for g in got])
print("forecast corr offline vs live %+.3f | entries (|forecast| >= th) offline %d live %d, same direction & both: %d" % (
    np.corrcoef(po, pl)[0, 1], (np.abs(po) >= m["th_top2pct"]).sum(), (np.abs(pl) >= m["th_top2pct"]).sum(),
    ((np.abs(po) >= m["th_top2pct"]) & (np.abs(pl) >= m["th_top2pct"]) & (np.sign(po) == np.sign(pl))).sum()))
