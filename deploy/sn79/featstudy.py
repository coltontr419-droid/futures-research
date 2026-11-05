"""What makes a reversal entry good? (decisions.md §1230) For our V0 rule's entries and the top skill takers' real entries on the same 3 h slice:
features at entry (spread, top-5 depth imbalance with/against our side, how much of the 10-min move came in the last 60 s, move size, book
price level) vs the forward mid move in our direction over the hold (bp). Tercile tables show which filter raises the per-entry edge."""
import json, sys
from collections import defaultdict
import numpy as np
TOP = {114, 238, 120, 163, 42, 214, 191, 89, 113, 124, 243, 70, 8, 103, 159, 161, 170, 126, 150, 100}
MB = int(sys.argv[1]); snap = defaultdict(dict); tt = []
with open("/opt/mvtrx/live_tape_x1_size6.jsonl", "rb") as fh:
    fh.seek(0, 2); n = fh.tell(); fh.seek(max(0, n - MB * 1_000_000)); fh.readline()
    for l in fh:
        if b'"bid"' in l:
            r = json.loads(l)
            if r.get("bid") and r.get("ask"):
                bd = sum(q for _, q in r.get("bids", [])); ad = sum(q for _, q in r.get("asks", []))
                snap[r["book"]][r["ts"] // 1_000_000_000] = ((r["bid"] + r["ask"]) / 2, (r["ask"] - r["bid"]), (bd - ad) / (bd + ad) if bd + ad else 0.0)
        elif b'"Ta"' in l:
            r = json.loads(l)
            if r.get("Ta") in TOP: tt.append((r["book"], r["ts"] // 1_000_000_000, r["p"]))
S = {}
for b, d in snap.items():
    ts = np.array(sorted(d)); a = np.array([d[t] for t in ts]); S[b] = (ts, a[:, 0], a[:, 1], a[:, 2])
def feats(b, i, d, hold):
    ts, m, sp, im = S[b]
    j600 = np.searchsorted(ts, ts[i] - 600); j60 = np.searchsorted(ts, ts[i] - 60); k = np.searchsorted(ts, ts[i] + hold)
    if j600 >= i or k >= len(ts): return None
    mv = (m[i] - m[j600]) / m[j600] * 1e4; last = (m[i] - m[j60]) / m[j60] * 1e4
    return dict(fwd=d * (m[k] - m[i]) / m[i] * 1e4, spread=sp[i] / m[i] * 1e4, imb_with=d * im[i], move=abs(mv),
                recent=(last / mv) if abs(mv) > 1e-9 else 0.0, price=m[i])
ours = []
for b, (ts, m, sp, im) in S.items():
    idx = {t: i for i, t in enumerate(ts)}; last = -10 ** 9
    for i in range(len(ts)):
        j = idx.get(ts[i] - 600)
        if j is None or ts[i] - last < 3600: continue
        r = (m[i] - m[j]) / m[j] * 1e4
        if abs(r) < 12: continue
        f = feats(b, i, -np.sign(r), 2400)
        if f: ours.append(f); last = ts[i]
top = []
for b, t, p in tt:
    if b not in S: continue
    ts, m, _, _ = S[b]; i = np.searchsorted(ts, t) - 1
    if i < 1: continue
    d = 1 if p >= m[i] else -1; f = feats(b, i, d, 600)
    if f: top.append(f)
def table(name, rows):
    print(f"\n== {name}: {len(rows)} entries, forward move in our direction: mean {np.mean([r['fwd'] for r in rows]):+.2f} bp, hit {np.mean([r['fwd'] > 0 for r in rows]) * 100:.0f}%")
    for k in ("spread", "imb_with", "move", "recent", "price"):
        x = np.array([r[k] for r in rows]); y = np.array([r["fwd"] for r in rows]); q = np.quantile(x, [0, 1 / 3, 2 / 3, 1])
        cells = []
        for a in range(3):
            s = (x >= q[a]) & (x <= q[a + 1]); cells.append("T%d [%.2g..%.2g] %+.2f bp, hit %.0f%%, n %d" % (a + 1, q[a], q[a + 1], y[s].mean(), (y[s] > 0).mean() * 100, s.sum()))
        print("  %-9s " % k + " | ".join(cells))
table("OUR V0 rule (12 bp / 600 s, hold 2400 s)", ours)
table("TOP skill takers' real trades (fwd over 600 s)", top)
# compare where the top takers trade vs our rule
for k in ("spread", "imb_with", "move", "recent"):
    print("median %-9s ours %+.2f | top %+.2f" % (k, np.median([r[k] for r in ours]), np.median([r[k] for r in top])))
