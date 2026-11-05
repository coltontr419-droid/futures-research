"""Does making hurt the model's skill on the same UID? (decisions.md §1235) Over the old x1's making period (UID 213 maker fills on the x1 tape)
= the predictor's unseen test slice: per-book alpha (P&L − mean inventory × drift, bp of the book's notional), the 2.3 bp hurdle and the validator's
kappa_of_alpha, for MODEL alone, MAKING alone, BOTH on the same books, and SPLIT (making only on books the model leaves alone)."""
import json, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import kappa_of_alpha
MB = int(sys.argv[1]); mid = defaultdict(dict); mk = defaultdict(list)
with open("/opt/mvtrx/live_tape_x1_size6.jsonl", "rb") as fh:
    fh.seek(0, 2); n = fh.tell(); fh.seek(max(0, n - MB * 1_000_000)); fh.readline()
    for l in fh:
        if b'"bid"' in l:
            r = json.loads(l)
            if r.get("bid") and r.get("ask"): mid[r["book"]][r["ts"] // 1_000_000_000] = (r["bid"] + r["ask"]) / 2
        elif b'"Ma": 213' in l:
            r = json.loads(l); mk[r["book"]].append((r["ts"] // 1_000_000_000, r["p"], r["q"]))
te = np.load("/opt/mvtrx/pred_test.npz"); m = json.load(open("/opt/mvtrx/agents/rev_model.json"))
p = np.clip((te["X"] - np.array(m["mu"])) / np.array(m["sd"]), -6, 6) @ np.array(m["w"]) + m["b"]
ents = defaultdict(list); last = {}
for i in np.argsort(te["ts"], kind="stable"):
    b, t = int(te["book"][i]), int(te["ts"][i])
    if abs(p[i]) >= m["th_top2pct"] and t - last.get(b, -10 ** 9) >= 3600:
        last[b] = t; ents[b].append((t, 1.0 if p[i] > 0 else -1.0))
def series(b):
    d = mid[b]; ts = np.array(sorted(d)); return ts, np.array([d[t] for t in ts])
def path_making(b, ts, mm):
    inv = np.zeros(len(ts)); notional = 0.0
    for t, px, q in sorted(mk.get(b, [])):
        i = np.searchsorted(ts, t); m0 = mm[max(i - 1, 0)]
        inv[i:] += -q if px >= m0 else q; notional += px * q        # maker sells into a buy-taker, buys from a sell-taker
    return inv, notional
def path_model(b, ts, mm):
    inv = np.zeros(len(ts)); notional = 0.0
    for t, d in ents.get(b, []):
        i = np.searchsorted(ts, t); k = np.searchsorted(ts, t + 600); q = 1000.0 / mm[min(i, len(mm) - 1)]
        inv[i:k] += d * q; notional += 2000.0
    return inv, notional
def alpha(inv, mm):
    dm = np.diff(mm); return float(np.sum(inv[:-1] * dm) - np.mean(inv[:-1]) * np.sum(dm))
rows = {"MODEL alone": [], "MAKING alone": [], "BOTH, same books": [], "SPLIT (making off model books)": []}
model_books = set(ents)
for b in mid:
    if len(mid[b]) < 1000: continue
    ts, mm = series(b); im, nm = path_making(b, ts, mm); io, no = path_model(b, ts, mm)
    if no: rows["MODEL alone"].append(alpha(io, mm) / no * 1e4)
    if nm: rows["MAKING alone"].append(alpha(im, mm) / nm * 1e4)
    if no or nm: rows["BOTH, same books"].append(alpha(im + io, mm) / (nm + no) * 1e4)
    if b in model_books and no: rows["SPLIT (making off model books)"].append(alpha(io, mm) / no * 1e4)
    elif nm: rows["SPLIT (making off model books)"].append(alpha(im, mm) / nm * 1e4)
print("old-x1 making fills: %d on %d books | model entries: %d on %d books" % (sum(len(v) for v in mk.values()), len(mk), sum(len(v) for v in ents.values()), len(ents)))
print("%-32s books  pass%%  fail%%  kept  pos/neg   median bp  kappa" % "")
for k, v in rows.items():
    a = np.array(v); kept = [float(x) for x in a if abs(x) >= 2.3]
    print("%-32s %5d  %4.0f   %4.0f   %4d  %3d/%-3d   %+6.2f   %+.2f" % (k, len(a), np.mean(a > 2.3) * 100, np.mean(a < -2.3) * 100, len(kept),
          sum(x > 0 for x in kept), sum(x < 0 for x in kept), np.median(a), kappa_of_alpha(kept) if len(kept) >= 4 else 0.0))
