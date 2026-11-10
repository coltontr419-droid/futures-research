"""§1376: why did fleet UID 216's live making fall today? Per ~1-wall-h sim bin (782 s): fills, notional and captured (Σ_book 2·min(buy,sell)) by book group,
for 216, x3 (64) and the rest of the long-lived fleet (median per UID). Also per-book cumulative notional for 216 on this tape (cap check).
   python3 why216.py <tape>"""
import sys, json, collections, statistics
F = [7,31,40,52,59,87,102,111,133,134,147,156,210,216,241,252,255]
U = set(F + [64]); B = 782.0; T0 = 34154
grp = lambda b: "$300" if b < 63 else ("calm" if b < 102 else "4dec")
st = collections.defaultdict(lambda: [0, 0.0, collections.defaultdict(lambda: [0.0, 0.0])])  # (bin,uid,grp) -> n, notional, book->[buy,sell]
cum = collections.defaultdict(float)
for l in open(sys.argv[1]):
    if '"Ma"' not in l: continue
    r = json.loads(l); u = r["Ma"]
    if u not in U: continue
    t = r["ts"] / 1e9
    if t >= 90000: continue
    k = (int((t - T0) // B), u, grp(r["book"])); v = r["p"] * r["q"]
    s = st[k]; s[0] += 1; s[1] += v; s[2][r["book"]][r["s"]] += v
    if u == 216: cum[r["book"]] += v
bins = sorted({k[0] for k in st})
print("bin  sim-start | grp  | 216: fills notional captured | x3: fills notional captured | fleet-median(excl 216): fills notional captured")
for b in bins:
    for g in ("$300", "calm", "4dec"):
        def row(u):
            s = st.get((b, u, g))
            if not s: return (0, 0, 0)
            return (s[0], s[1], sum(2 * min(x) for x in s[2].values()))
        fl = [row(u) for u in F if u != 216]
        med = tuple(statistics.median(x[i] for x in fl) for i in range(3))
        a, c = row(216), row(64)
        print(f"{b:3d} {T0 + b * B:7.0f} | {g:4s} | {a[0]:5d} {a[1]/1e3:7.1f}k {a[2]/1e3:6.1f}k | {c[0]:5d} {c[1]/1e3:7.1f}k {c[2]/1e3:6.1f}k | {med[0]:5.0f} {med[1]/1e3:7.1f}k {med[2]/1e3:6.1f}k")
top = sorted(cum.items(), key=lambda x: -x[1])[:8]
print("216 cumulative notional on this tape, top books:", [(b, round(v / 1e3)) for b, v in top], "| books traded", len(cum))
