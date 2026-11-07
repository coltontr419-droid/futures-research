"""§1275: how the long-lived maker fleet quotes the $300 books (ids 0-62) vs the calm ones, from their fills. Per group of UIDs and book group:
fill distance from the mid (bp and in half-spreads), fill $ size, spread at fill, maker's mid move after 30/120/300 s (+ = good for the maker),
capture vs a print-centred later mid, fills per book per sim h, two-sided share.   python m300copy.py <tape> <uids> [since sim s]"""
import json, sys, collections, statistics as st, bisect
tape, U = sys.argv[1], {int(u) for u in sys.argv[2].split(",")}; LO = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0   # optional: only fills at sim s ≥ LO
M = collections.defaultdict(lambda: ([], [], [])); F = []; seen = set(); t0 = t1 = None
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000: continue
    if b'"bid": ' in l[:80]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r.get("bid") and r.get("ask"): m = M[r["book"]]; m[0].append(t); m[1].append((r["bid"] + r["ask"]) / 2); m[2].append(r["ask"] - r["bid"])
    elif b'"Ta": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"))
        if k in seen: continue
        seen.add(k); t0 = t if t0 is None else t0; t1 = t
        if r.get("Ma") in U and t >= LO: F.append((r["Ma"], r["book"], t, r["s"], r["q"], r["p"]))
def at(b, t):
    a = M[b]; i = bisect.bisect_right(a[0], t) - 1
    return (a[1][i], a[2][i]) if i >= 0 else (None, None)
span = (t1 - t0) / 3600
R = collections.defaultdict(lambda: collections.defaultdict(list)); SIDE = collections.defaultdict(lambda: [0.0, 0.0])
for u, b, t, s, q, p in F:
    g = ("$300" if b < 63 else "calm" if b < 102 else "4-dec"); m0, sp = at(b, t - 0.001)
    if not m0: continue
    sg = 1 if s == 0 else -1          # s == 0: the resting order was the SELL?  (taker bought) -> maker sold -> maker short: sg for maker = -1
    mk = -sg                          # maker's position change: +1 bought, -1 sold
    d = R[(u in U and "fleet", g)]
    d["dist_bp"].append(abs(p - m0) / m0 * 1e4); d["dist_hs"].append(abs(p - m0) / (sp / 2) if sp else 0); d["usd"].append(q * p); d["spread_bp"].append(sp / m0 * 1e4)
    d["edge_bp"].append(mk * (m0 - p) / m0 * 1e4)
    for h in (30, 120, 300):
        m1, _ = at(b, t + h)
        if m1: d[f"mv{h}"].append(mk * (m1 - m0) / m0 * 1e4)
    SIDE[(u, b)][0 if mk > 0 else 1] += q * p
    d["books"].append(b)
print(f"tape span {span:.2f} sim h | fleet fills {len(F)}")
for (who, g), d in sorted(R.items()):
    nb = len(set(d["books"])); two = [k for k in SIDE if (k[1] < 63) == (g == "$300") and min(SIDE[k]) > 0.25 * max(SIDE[k])]
    print(f"{g:6} fills {len(d['usd']):6d} | books {nb:3d} | fills/book/simh {len(d['usd']) / max(nb, 1) / span / max(len(U), 1):5.1f} per uid | size median ${st.median(d['usd']):,.0f}"
          f" | spread {st.median(d['spread_bp']):.1f} bp | fill vs mid {st.median(d['dist_bp']):.1f} bp = {st.median(d['dist_hs']):.2f} half-spreads | edge at fill {st.mean(d['edge_bp']):+.2f} bp"
          f" | mid after 30/120/300 s {st.mean(d['mv30']):+.2f} / {st.mean(d['mv120']):+.2f} / {st.mean(d['mv300']):+.2f} bp | net @120 s {st.mean(d['edge_bp']) + st.mean(d['mv120']):+.2f} bp")
