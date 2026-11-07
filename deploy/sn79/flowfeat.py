"""New candidate entry features (decisions.md §1266), joined to a predfeat5 table built on the same tape slice: signed taker flow over 30 / 120 s from the top skill UIDs, other miners and background agents
(normalised by the book's mean |flow| per second × window), and the market-wide 5-min move (mean dmid300 across books) plus the book's own move net of it.
    python flowfeat.py <tape> <MB> <OFF MB> <in.npz> <out.npz>"""
import json, sys, collections, numpy as np
tape, MB, OFF, inp, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
SKILL = {103, 122, 8, 181, 197, 120, 195, 191, 203}
F = {c: collections.defaultdict(lambda: collections.defaultdict(float)) for c in ("top", "miner", "bg")}
with open(tape, "rb") as fh:
    fh.seek(0, 2); end = fh.tell() - OFF * 1_000_000; fh.seek(max(0, end - MB * 1_000_000)); fh.readline()
    while fh.tell() < end:
        l = fh.readline()
        if not l: break
        if b'"p"' not in l: continue
        r = json.loads(l); ta = r.get("Ta"); c = "top" if ta in SKILL else ("bg" if ta is None or ta < 0 else "miner")
        F[c][r["book"]][r["ts"] // 1_000_000_000] += (1 if r["s"] == 0 else -1) * r["q"] * r["p"]
D = dict(np.load(inp)); B, T = D["book"], D["ts"]; names = list(D["names"]); X = D["X"]; extra = []; en = []
for c in ("top", "miner", "bg"):
    for w in (30, 120):
        col = np.zeros(len(T))
        for b in np.unique(B):
            m = np.where(B == b)[0]; d = F[c].get(int(b), {})
            if not d: continue
            ks = np.array(sorted(d)); vs = np.array([d[k] for k in ks]); cs = np.concatenate([[0.0], np.cumsum(vs)]); scale = max(np.mean(np.abs(vs)) * w * len(vs) / max(ks[-1] - ks[0], 1), 1e-9)
            hi = np.searchsorted(ks, T[m], side="right"); lo = np.searchsorted(ks, T[m] - w, side="right"); col[m] = (cs[hi] - cs[lo]) / scale
        extra.append(col); en.append(f"{c}flow{w}")
j = names.index("dmid300"); bucket = T // 5; mkt = collections.defaultdict(list)
for i, k in enumerate(bucket): mkt[k].append(X[i, j])
mm = {k: np.mean(v) for k, v in mkt.items()}; mcol = np.array([mm[k] for k in bucket]); extra.append(mcol); en.append("mkt300"); extra.append(X[:, j] - mcol); en.append("idio300")
D["X"] = np.c_[X, np.array(extra).T]; D["names"] = np.array(names + en); np.savez_compressed(out, **D)
print("rows", len(T), "features", len(D["names"]), "| nonzero share:", {n: round(float(np.mean(e != 0)), 2) for n, e in zip(en, extra)})
