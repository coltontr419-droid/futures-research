"""Which of x3's fills lose? (decisions.md §1242) Every x3 maker fill (Ma = 58) on x1's tape since the skew fix, with the book at the fill:
spread (ticks and bp), top-of-book size on our side vs the other side, 60-s realized volatility, the v1 forecast in our direction, fill size
and price level; outcome = the maker's markout at 20 s (bp, + = kept). Tercile tables show which conditions carry the losses."""
import json, sys
from collections import defaultdict
import numpy as np
T, SINCE = sys.argv[1], float(sys.argv[2]) * 6e10
mid, spr, top = defaultdict(dict), defaultdict(dict), defaultdict(dict); fills = []
with open(T, "rb") as fh:
    for l in fh:
        if b'"bid"' in l:
            r = json.loads(l)
            if r.get("bid") and r.get("ask"):
                t = r["ts"] // 1_000_000_000; m = (r["bid"] + r["ask"]) / 2; mid[r["book"]][t] = m; spr[r["book"]][t] = (r["ask"] - r["bid"]) / m * 1e4
                top[r["book"]][t] = (r["bids"][0][1] if r.get("bids") else 0.0, r["asks"][0][1] if r.get("asks") else 0.0)
        elif b'"Ma": 58,' in l:
            r = json.loads(l)
            if r["ts"] >= SINCE: fills.append((r["book"], r["ts"] // 1_000_000_000, r["p"], r["q"]))
def at(d, t):
    for k in range(t, t - 6, -1):
        if k in d: return d[k]
D = np.load("/opt/mvtrx/v2_D.npz"); mm = json.load(open("/opt/mvtrx/agents/rev_model.json"))
p = np.clip((D["X"] - np.array(mm["mu"])) / np.array(mm["sd"]), -6, 6) @ np.array(mm["w"]) + mm["b"]
fc = {(int(b), int(t)): float(x) for b, t, x in zip(D["book"], D["ts"], p)}
rows = []
for b, t, px, q in fills:
    m0, m20 = at(mid[b], t - 1), at(mid[b], t + 20)
    if m0 is None or m20 is None: continue
    s = -1 if px >= m0 else 1                                   # our side: -1 we sold, +1 we bought
    path = [at(mid[b], k) for k in range(t - 60, t, 5)]; path = [x for x in path if x]
    vol = float(np.std(np.diff(np.log(path))) * 1e4) if len(path) > 3 else np.nan
    tb = at(top[b], t - 1) or (0, 0); ours, other = (tb[0], tb[1]) if s > 0 else (tb[1], tb[0])
    f = None
    for k in range(t - t % 5, t - t % 5 - 30, -5):
        f = fc.get((b, k))
        if f is not None: break
    rows.append(dict(mk=s * (m20 - m0) / m0 * 1e4, half=-s * (px - m0) / m0 * 1e4, spread=at(spr[b], t - 1) or np.nan, vol=vol,
                     depth_ratio=(ours / other) if other else np.nan, fc=(s * f) if f is not None else np.nan, usd=px * q, price=m0))
print("x3 fills since the skew fix with context: %d | mean half-spread %+.2f bp, mean markout 20 s %+.2f bp, kept %.0f%%" % (
    len(rows), np.mean([r["half"] for r in rows]), np.mean([r["mk"] for r in rows]),
    (np.mean([r["half"] for r in rows]) + np.mean([r["mk"] for r in rows])) / np.mean([r["half"] for r in rows]) * 100))
for k, lab in (("spread", "spread at fill (bp)"), ("vol", "60-s volatility (bp/5s)"), ("depth_ratio", "our-side / other-side top size"),
               ("fc", "model forecast in our favour (bp)"), ("usd", "fill size ($)"), ("price", "book price level")):
    x = np.array([r[k] for r in rows], float); y = np.array([r["mk"] for r in rows]); h = np.array([r["half"] for r in rows]); ok = ~np.isnan(x)
    q3 = np.quantile(x[ok], [0, 1 / 3, 2 / 3, 1]); cells = []
    for a in range(3):
        sel = ok & (x >= q3[a]) & (x <= q3[a + 1])
        cells.append("T%d [%.3g..%.3g] mk %+.2f, half %+.2f, kept %3.0f%% (n %d)" % (a + 1, q3[a], q3[a + 1], y[sel].mean(), h[sel].mean(), (h[sel].mean() + y[sel].mean()) / h[sel].mean() * 100, sel.sum()))
    print("  %-34s " % lab + " | ".join(cells))
