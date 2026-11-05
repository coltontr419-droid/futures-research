"""What separates top makers from median ones, and would our predictor protect quotes? (decisions.md §1238)
Today's frozen x1 tape: every maker fill (Ma ≥ 0): half spread captured (fill vs prior mid), mid markout in the maker's favour at 5/20/60 s,
per-book side balance, size, books. Makers ranked by markout-based quality proxy; plus each fill's v1 forecast (nearest 5-s row of v2_D)."""
import json, sys
from collections import defaultdict
import numpy as np
T = sys.argv[1]; mid = defaultdict(dict); fills = defaultdict(list)
with open(T, "rb") as fh:
    for l in fh:
        if b'"bid"' in l:
            r = json.loads(l)
            if r.get("bid") and r.get("ask"): mid[r["book"]][r["ts"] // 1_000_000_000] = (r["bid"] + r["ask"]) / 2
        elif b'"Ma"' in l:
            r = json.loads(l)
            if (r.get("Ma") or -1) >= 0: fills[r["Ma"]].append((r["book"], r["ts"] // 1_000_000_000, r["p"], r["q"]))
def at(d, t, back=6):
    for k in range(t, t - back, -1):
        if k in d: return d[k]
D = np.load("/opt/mvtrx/v2_D.npz"); m = json.load(open("/opt/mvtrx/agents/rev_model.json"))
p = np.clip((D["X"] - np.array(m["mu"])) / np.array(m["sd"]), -6, 6) @ np.array(m["w"]) + m["b"]
fc = {(int(b), int(t)): float(x) for b, t, x in zip(D["book"], D["ts"], p)}
def forecast(b, t):
    for k in range(t - t % 5, t - t % 5 - 30, -5):
        v = fc.get((b, k))
        if v is not None: return v
stats = {}; allf = []
for u, fs in fills.items():
    if len(fs) < 150: continue
    hs, m5, m20, m60, sz, bal = [], [], [], [], [], defaultdict(lambda: [0.0, 0.0])
    for b, t, px, q in fs:
        m0, a5, a20, a60 = at(mid[b], t - 1), at(mid[b], t + 5), at(mid[b], t + 20), at(mid[b], t + 60)
        if None in (m0, a5, a20, a60): continue
        s = -1 if px >= m0 else 1                            # maker side: sold into a buyer (-1) or bought from a seller (+1)
        hs.append(-s * (px - m0) / m0 * 1e4); m5.append(s * (a5 - m0) / m0 * 1e4); m20.append(s * (a20 - m0) / m0 * 1e4); m60.append(s * (a60 - m0) / m0 * 1e4)
        sz.append(px * q); bal[b][0 if s > 0 else 1] += px * q
        f = forecast(b, t)
        if f is not None: allf.append((u, s, f, m20[-1], hs[-1]))
    if len(hs) < 100: continue
    bb = [2 * min(x) / sum(x) for x in bal.values() if sum(x) > 0]
    stats[u] = dict(n=len(hs), half=np.mean(hs), m5=np.mean(m5), m20=np.mean(m20), m60=np.mean(m60), size=np.median(sz), books=len(bal), balance=np.mean(bb),
                    keep20=(np.mean(hs) + np.mean(m20)) / max(np.mean(hs), 1e-9))
us = sorted(stats, key=lambda u: -stats[u]["keep20"]); q = len(us) // 4
def row(lab, grp):
    g = [stats[u] for u in grp]; f = lambda k: np.median([x[k] for x in g])
    print("%-22s n=%3d | fills %5.0f | half-spread %+.2f bp | markout 5s %+.2f 20s %+.2f 60s %+.2f | kept@20s %.2f | size $%5.0f | books %3.0f | balance %.2f" % (
        lab, len(g), f("n"), f("half"), f("m5"), f("m20"), f("m60"), f("keep20"), f("size"), f("books"), f("balance")))
print("makers with ≥ 100 scored fills:", len(us))
row("TOP quartile (kept)", us[:q]); row("MEDIAN half", us[q:3 * q]); row("BOTTOM quartile", us[3 * q:])
if 58 in stats: row("x3 (UID 58)", [58])
a = np.array([(s * f, m20, h) for u, s, f, m20, h in allf])               # forecast aligned with the maker's side: + = model expects price to move its way
print("\nALL maker fills with a forecast: %d | markout 20 s by model alignment:" % len(a))
for lab, sel in (("model AGAINST the maker (f·side < -2 bp)", a[:, 0] < -2), ("neutral (|f| ≤ 2)", np.abs(a[:, 0]) <= 2), ("model WITH the maker (> +2 bp)", a[:, 0] > 2)):
    print("  %-44s share %4.1f%% | markout 20 s %+.2f bp | kept@20s %.2f" % (lab, sel.mean() * 100, a[sel, 1].mean(), (a[sel, 2].mean() + a[sel, 1].mean()) / a[sel, 2].mean()))
