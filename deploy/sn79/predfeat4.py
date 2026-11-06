"""Feature/target table (decisions.md §1249; predfeat.py + targets at 300/900/1800 s and the mid): every 5 sim s per book from a tape slice.
    python predfeat4.py <MB> <MB back from end> <out.npz> [tape]"""
import json, sys
from collections import defaultdict
import numpy as np
MB, OFF, OUT = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]; TAPE = sys.argv[4] if len(sys.argv) > 4 else "/opt/mvtrx/live_tape_x1_size6.jsonl"
TOP = {114, 238, 120, 163, 42, 214, 191, 89, 113, 124, 243, 70, 8, 103, 159, 161, 170, 126, 150, 100}
mid, fund, imb, spr, of = (defaultdict(dict) for _ in range(5)); trades = defaultdict(list)
with open(TAPE, "rb") as fh:
    fh.seek(0, 2); n = fh.tell(); end = n - OFF * 1_000_000; fh.seek(max(0, end - MB * 1_000_000)); fh.readline()
    while fh.tell() < end:
        l = fh.readline()
        if not l: break
        r = json.loads(l); b = r.get("book"); t = r["ts"] // 1_000_000_000
        if "bid" in r and r.get("bid") and r.get("ask"):
            m = (r["bid"] + r["ask"]) / 2; mid[b][t] = m; spr[b][t] = (r["ask"] - r["bid"]) / m * 1e4
            bd = sum(q for _, q in r.get("bids", [])); ad = sum(q for _, q in r.get("asks", [])); imb[b][t] = (bd - ad) / (bd + ad) if bd + ad else 0.0
            if r.get("fund"): fund[b][t] = r["fund"]
        elif "of" in r:
            o = r["of"]; of[b][t] = (o.get("nb", 0) - o.get("na", 0)) - (o.get("cb", 0) - o.get("ca", 0))
        elif "p" in r and r.get("Ta") not in TOP:
            trades[b].append((t, r["p"], r["q"]))
def ffill(d):
    ks = sorted(d); a = np.full(ks[-1] - ks[0] + 1, np.nan); a[np.array(ks) - ks[0]] = [d[k] for k in ks]
    for i in range(1, len(a)):
        if np.isnan(a[i]): a[i] = a[i - 1]
    return ks[0], a
X, Y60, Y600, BK, TS = [], [], [], [], []; Y300, Y900, Y1800, MID = [], [], [], []
names = ["dmid1", "dmid5", "dmid30", "dmid60", "dmid300", "dfund1", "dfund10", "dfund60", "gap", "gapchg10", "imb", "spread", "flow10", "book10", "big5"]
for b in mid:
    if len(mid[b]) < 2000 or not fund.get(b): continue
    t0, M = ffill(mid[b]); tf, F = ffill(fund[b]); _, I = ffill(imb[b]); _, S = ffill(spr[b])
    T = len(M); fl = np.zeros(T); bk = np.zeros(T); bg = np.zeros(T)
    qs = [q for _, _, q in trades[b]]; big = np.percentile(qs, 95) if qs else 1e9
    for t, p, q in trades[b]:
        i = t - t0
        if 1 <= i < T:
            s = 1 if p >= M[i - 1] else -1; fl[i] += s * q
            if q >= big: bg[i] += s
    for t, v in of[b].items():
        i = t - t0
        if 0 <= i < T: bk[i] += v
    cfl, cbk, cbg = np.concatenate([[0], np.cumsum(fl)]), np.concatenate([[0], np.cumsum(bk)]), np.concatenate([[0], np.cumsum(bg)])
    fidx = lambda i: i + t0 - tf
    for i in range(300, T - 1800, 5):
        j = fidx(i)
        if j < 60 or j >= len(F) or np.isnan(F[j]) or np.isnan(F[j - 60]) or np.isnan(M[i - 300]): continue
        m = M[i]; bp = lambda a, z: (a - z) / m * 1e4
        g = bp(F[j], m); g10 = g - bp(F[j - 10], M[i - 10])
        X.append([bp(m, M[i - 1]), bp(m, M[i - 5]), bp(m, M[i - 30]), bp(m, M[i - 60]), bp(m, M[i - 300]), bp(F[j], F[j - 1]), bp(F[j], F[j - 10]),
                  bp(F[j], F[j - 60]), g, g10, I[i], S[i], (cfl[i] - cfl[i - 10]) / max(np.mean(np.abs(fl)) * 10, 1e-9),
                  (cbk[i] - cbk[i - 10]) / max(np.mean(np.abs(bk)) * 10, 1e-9), cbg[i] - cbg[i - 5]])
        Y60.append(bp(M[i + 60], m)); Y600.append(bp(M[i + 600], m)); BK.append(b); TS.append(i + t0)
        Y300.append(bp(M[i + 300], m)); Y900.append(bp(M[i + 900], m)); Y1800.append(bp(M[i + 1800], m)); MID.append(m)
X = np.nan_to_num(np.array(X, float)); np.savez_compressed(OUT, X=X, y60=np.array(Y60), y600=np.array(Y600), book=np.array(BK), ts=np.array(TS), names=np.array(names), y300=np.array(Y300), y900=np.array(Y900), y1800=np.array(Y1800), mid=np.array(MID))
print("rows", len(X), "books", len(set(BK)), "->", OUT)
