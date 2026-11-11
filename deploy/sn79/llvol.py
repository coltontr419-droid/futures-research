"""§1380: per-book cumulative maker+taker notional on the whole tape (sim 34,154 →) and per sim-hour rate, x3 vs top makers — are they above 500k/book?"""
import json, sys, collections
U = [64, 132, 3, 46, 17, 193, 21, 216]
cum = collections.defaultdict(lambda: collections.defaultdict(float)); hr = collections.defaultdict(lambda: collections.defaultdict(float)); T0 = None; T1 = 0
for l in open(sys.argv[1]):
    if '"Ma"' not in l: continue
    i = l.find('"ts": '); t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t >= 90000: continue
    r = json.loads(l); x = r["p"] * r["q"]
    T0 = t if T0 is None else T0; T1 = t
    for u in (r["Ma"], r["Ta"]):
        if u in U: cum[u][r["book"]] += x; hr[u][int((t - 34154) // 3600)] += x
print(f"tape sim {T0:.0f}-{T1:.0f} ({(T1 - T0) / 3600:.1f} sim h)")
for u in U:
    v = sorted(cum[u].values()); n = len(v)
    h = [hr[u][k] / 128 / 1e3 for k in sorted(hr[u])]
    print(f"UID {u:3d}: per book on tape median ${v[n//2]/1e3:.0f}k p90 ${v[int(.9*(n-1))]/1e3:.0f}k max ${v[-1]/1e3:.0f}k (> $500k: {sum(x > 500000 for x in v)}) | per-book $k per sim hour: {' '.join(f'{x:.0f}' for x in h)}")
